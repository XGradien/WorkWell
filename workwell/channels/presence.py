"""Presence channel: number of faces in front of the camera (Haar)."""

from __future__ import annotations

import logging
from typing import Any

from .base import Channel

logger = logging.getLogger(__name__)


class PresenceChannel(Channel):
    name = "presence"
    unit = "faces"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.camera_index = int(self.cfg.get("camera_index", 0))
        self._cap = None
        self._cascade = None
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
        except Exception:
            return False

    def start(self) -> bool:
        if self._cap is not None:
            return True
        try:
            import cv2

            if not self.check_available():
                return False

            cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                return False
            ok, _ = cap.read()
            if not ok:
                cap.release()
                return False
            self._cascade = cascade
            self._cap = cap
            return True
        except Exception as exc:
            logger.debug("presence start failed: %s", exc)
            return False

    def read(self) -> dict[str, Any]:
        if self._cap is None or self._cascade is None:
            raise RuntimeError("presence channel not started")
        # Local import: cv2 is an optional dependency (sensors extra). It is
        # guaranteed available here because start() imported it successfully.
        import cv2

        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("failed to capture frame")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        faces = self._cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
        )
        count = len(faces)
        return {"value": float(count), "label": "occupied" if count > 0 else "empty"}

    def stop(self) -> bool:
        if self._cap is not None and self._owns_cap:
            self._cap.release()
        self._cap = None
        self._cascade = None
        return True
