"""Config: defaults, yaml, env overrides, validation."""

from __future__ import annotations

import pytest

from workwell.config import Config


def test_defaults_sane():
    cfg = Config.with_overrides({})
    assert cfg.get("server.port") == 8000
    assert cfg.get("channels.greenery.resolution") == [320, 240]
    assert cfg.get("channels.mood.enabled") is False
    assert cfg.get("wellness.weights")["air"] == 0.2


def test_override_merges_recursively():
    cfg = Config.with_overrides({"server": {"port": 9000}})
    assert cfg.get("server.port") == 9000
    assert cfg.get("server.host") == "127.0.0.1"  # untouched sibling survives


def test_get_missing_returns_default():
    cfg = Config.with_overrides({})
    assert cfg.get("nope.nada", "fallback") == "fallback"


def test_env_override(monkeypatch):
    monkeypatch.setenv("WORKWELL_SERVER_PORT", "9123")
    cfg = Config.load()
    assert cfg.get("server.port") == 9123


def test_env_override_nested_bool(monkeypatch):
    monkeypatch.setenv("WORKWELL_CHANNELS_MOOD_ENABLED", "true")
    cfg = Config.load()
    assert cfg.get("channels.mood.enabled") is True


def test_invalid_weights_rejected():
    with pytest.raises(RuntimeError):
        Config.with_overrides({"wellness": {"weights": {"greenery": -0.5}}})


def test_invalid_port_rejected():
    with pytest.raises(RuntimeError):
        Config.with_overrides({"server": {"port": 0}})


def test_bad_interval_rejected():
    with pytest.raises(RuntimeError):
        Config.with_overrides({"channels": {"noise": {"interval": 0}}})


def test_yaml_load(tmp_path, monkeypatch):
    cfgdir = tmp_path / "cfg"
    cfgdir.mkdir()
    (cfgdir / "workwell.yaml").write_text("server:\n  port: 7777\n")
    monkeypatch.setenv("WORKWELL_CONFIG_DIR", str(cfgdir))
    cfg = Config.load()
    assert cfg.get("server.port") == 7777
    # defaults still present around the override
    assert "greenery" in cfg.get("channels")
