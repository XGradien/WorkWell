"""Greenery channel: camera frame -> percentage of green pixels (HSV)."""

from __future__ import annotations

import logging
from typing import Any

from .base import Channel

logger = logging.getLogger(__name__)


class GreeneryChannel(Channel):
    name = "greenery"
    unit = "%"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.camera_index = int(self.cfg.get("camera_index", 0))
        self.resolution = tuple(self.cfg.get("resolution", [320, 240]))
        self.hue_lo, self.hue_hi = self.cfg.get("green_hue_range", [35, 85])
        self.sat_min = int(self.cfg.get("saturation_min", 40))
        self.val_min = int(self.cfg.get("value_min", 40))
        self._cap = None
        self._owns_cap = True

    def attach(self, cap) -> None:
        """Share an already-opened camera (it's a single physical device)."""
        self._cap = cap
        self._owns_cap = False

    def check_available(self) -> bool:
        try:
            import cv2

            cap = cv2.VideoCapture(self.camera_index)
            ok = cap.isOpened()
            cap.release()
            return bool(ok)
        except Exception as exc:  # cv2 missing or camera busy
            logger.debug("greenery availability check failed: %s", exc)
            return False

    def start(self) -> bool:
        if self._cap is not None:
            return True
        try:
            if not self.check_available():
                return False
            import cv2

            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                return False
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            ok, _ = cap.read()
            if not ok:
                cap.release()
                return False
            self._cap = cap
            return True
        except Exception as exc:
            logger.debug("greenery start failed: %s", exc)
            return False

    def read(self) -> dict[str, Any]:
        import cv2
        import numpy as np

        if self._cap is None or not self._cap.isOpened():
            raise RuntimeError("camera not started")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("failed to capture frame")

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.array([self.hue_lo, self.sat_min, self.val_min], dtype=np.uint8)
        upper = np.array([self.hue_hi, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        pct = float(np.count_nonzero(mask) / mask.size * 100.0)
        return {"value": round(pct, 2), "label": None}

    def stop(self) -> bool:
        if self._cap is not None and self._owns_cap:
            self._cap.release()
        self._cap = None
        return True
