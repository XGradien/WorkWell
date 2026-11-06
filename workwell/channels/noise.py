"""Noise channel: microphone RMS -> 0-100 normalized level + class."""

from __future__ import annotations

import logging
from typing import Any

from .base import Channel

logger = logging.getLogger(__name__)

# Classification thresholds on the normalized 0-100 scale
def classify(level: float) -> str:
    if level < 30:
        return "quiet"
    if level < 50:
        return "normal"
    if level < 70:
        return "moderate"
    if level < 85:
        return "noisy"
    return "very noisy"


class NoiseChannel(Channel):
    name = "noise"
    unit = "dBn"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.capture_duration = float(self.cfg.get("capture_duration", 0.5))
        self.sample_rate = int(self.cfg.get("sample_rate", 16000))
        self.db_reference = float(self.cfg.get("db_reference", -60.0))

    def check_available(self) -> bool:
        try:
            import sounddevice as sd

            return sd.query_devices(kind="input") is not None
        except Exception:
            return False

    def start(self) -> bool:
        if not self.check_available():
            return False
        try:
            import numpy as np
            import sounddevice as sd

            probe = sd.rec(
                int(0.05 * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()
            _ = np.sqrt(np.mean(probe**2))
            return True
        except Exception as exc:
            logger.debug("noise start failed: %s", exc)
            return False

    def read(self) -> dict[str, Any]:
        import numpy as np
        import sounddevice as sd

        recording = sd.rec(
            int(self.capture_duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        samples = recording.flatten()
        rms = float(np.sqrt(np.mean(samples**2)))
        raw_db = 20.0 * np.log10(rms + 1e-10)
        level = max(0.0, min(100.0, (raw_db - self.db_reference) * 100.0 / abs(self.db_reference)))
        return {"value": round(level, 2), "label": classify(level)}

    def stop(self) -> bool:
        return True
