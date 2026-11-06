"""WorkWell configuration.

One YAML file (``config/workwell.yaml`` next to the package, or the
directory pointed to by ``WORKWELL_CONFIG_DIR``) plus environment
overrides. Unlike v1, every value loaded here is actually consumed by
the sensors, the store and the wellness engine.

Resolution order (highest wins):
    environment variable  >  yaml file  >  built-in defaults
"""

from __future__ import annotations

import copy
import os
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 8000, "web_dist": None},
    "storage": {"path": "data/workwell.db", "prune_days": 30},
    "channels": {
        "greenery": {
            "enabled": True,
            "interval": 4.0,
            "camera_index": 0,
            "resolution": [320, 240],  # small on purpose: fast + cool
            "green_hue_range": [35, 85],
            "saturation_min": 40,
            "value_min": 40,
        },
        "noise": {
            "enabled": True,
            "interval": 2.0,
            "capture_duration": 0.5,
            "sample_rate": 16000,  # enough for a noise level, cheap
        },
        "air": {
            "enabled": True,
            "interval": 15.0,
            "backend": "auto",  # auto | serial | i2c | spi | mock
            "serial_port": "/dev/ttyUSB0",
            "sample_count": 10,
        },
        "mood": {
            "enabled": False,  # needs the [ml] extra (DeepFace/TF)
            "interval": 10.0,
            "camera_index": 0,
            "confidence_threshold": 0.4,
        },
        "presence": {
            "enabled": True,
            "interval": 8.0,
            "camera_index": 0,
        },
    },
    "simulation": {"interval": 2.0, "default_scenario": "calm"},
    "wellness": {
        "window_minutes": 30,
        "weights": {"greenery": 0.3, "noise": 0.3, "air": 0.2, "mood": 0.2},
    },
}

# ENV overrides: WORKWELL_<SECTION>_<KEY> e.g. WORKWELL_SERVER_PORT=9000
_ENV_PREFIX = "WORKWELL_"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _apply_env(cfg: dict) -> dict:
    for key, raw in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        parts = key[len(_ENV_PREFIX):].lower().split("_")
        if len(parts) < 2:
            continue
        section, leaf = parts[0], parts[-1]
        if section not in cfg:
            continue
        node = cfg[section]
        if not isinstance(node, dict):
            continue
        value = _parse_scalar(raw)
        if len(parts) == 2:
            if leaf in node or _coerces(node.get(leaf), value):
                node[leaf] = value
        else:
            # e.g. WORKWELL_CHANNELS_NOISE_INTERVAL=1 -> channels.noise.interval
            target = node
            for mid in parts[1:-1]:
                if not isinstance(target.get(mid), dict):
                    target[mid] = {}
                target = target[mid]
            if leaf in target or _coerces(target.get(leaf), value):
                target[leaf] = value
    return cfg


def _coerces(existing: Any, new: Any) -> bool:
    """Allow env override only when the type family matches."""
    if isinstance(existing, bool):
        return isinstance(new, bool)
    if isinstance(existing, (int, float)) and not isinstance(existing, bool):
        return isinstance(new, (int, float))
    if isinstance(existing, list):
        return isinstance(new, list)
    return True


def _parse_scalar(raw: str) -> Any:
    low = raw.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [_parse_scalar(p.strip()) for p in inner.split(",")]
        return raw


def _find_config_dir() -> str:
    env_dir = os.getenv("WORKWELL_CONFIG_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    package_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.path.dirname(package_dir), "config"),  # <root>/config
        package_dir,
    ]
    for cand in candidates:
        if os.path.isfile(os.path.join(cand, "workwell.yaml")):
            return cand
    return candidates[0]


class Config:
    """Loaded, validated configuration. Access via ``cfg.get('a.b.c')``."""

    def __init__(self, data: dict[str, Any]):
        self.data = data

    @classmethod
    def with_overrides(cls, extra: dict[str, Any]) -> Config:
        """Defaults merged with ``extra`` (no file, no env). For tests/scripts."""
        data = _deep_merge(DEFAULTS, extra or {})
        cfg = cls(data)
        cfg.validate()
        return cfg

    @classmethod
    def load(cls, config_dir: str | None = None) -> Config:
        directory = config_dir or _find_config_dir()
        loaded: dict[str, Any] = {}
        path = os.path.join(directory, "workwell.yaml")
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    loaded = yaml.safe_load(fh) or {}
            except yaml.YAMLError as exc:
                raise RuntimeError(f"invalid YAML in {path}: {exc}") from exc
        data = _deep_merge(DEFAULTS, loaded)
        _apply_env(data)
        cfg = cls(data)
        cfg.validate()
        return cfg

    def get(self, key: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return copy.deepcopy(node)

    def section(self, name: str) -> dict[str, Any]:
        value = self.data.get(name, {})
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def validate(self) -> None:
        weights = self.get("wellness.weights", {})
        if set(weights) != {"greenery", "noise", "air", "mood"}:
            raise RuntimeError("wellness.weights must define greenery, noise, air, mood")
        for chan, weight in weights.items():
            if not 0 <= float(weight) <= 1:
                raise RuntimeError(f"wellness.weights.{chan} must be between 0 and 1")
        total = sum(float(w) for w in weights.values())
        if not 0.2 <= total <= 2.0:
            raise RuntimeError("wellness.weights total must be between 0.2 and 2.0")
        for chan, interval in self.get("channels", {}).items():
            if isinstance(interval, dict) and float(interval.get("interval", 1)) <= 0:
                raise RuntimeError(f"channels.{chan}.interval must be > 0")
        port = int(self.get("server.port", 0))
        if not 1 <= port <= 65535:
            raise RuntimeError("server.port must be 1-65535")


# Global instance, built at import time (same as v1's config, but this
# one is actually read by every component).
config = Config.load()
