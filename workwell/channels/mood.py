"""Mood channel: facial expression probabilities.

Heavy on purpose to be off by default — DeepFace pulls in TensorFlow
(which is what melted the Raspberry Pi in the original project). This
channel is only usable when the ``[ml]`` extra is installed; otherwise
``check_available`` returns False cheaply and the dashboard shows the
channel as unavailable (or simulated in demo mode).
"""

from __future__ import annotations

import logging
from typing import Any

from .base import Channel

logger = logging.getLogger(__name__)

EMOTIONS = ("angry", "disgust", "fear", "happy", "sad", "surprised", "neutral")


class MoodChannel(Channel):
    name = "mood"
    unit = ""

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.camera_index = int(self.cfg.get("camera_index", 0))
        self.threshold = float(self.cfg.get("confidence_threshold", 0.4))
        self._cap = None
        self._owns_cap = True
        self._deepface = None

    def attach(self, cap) -> None:
        """Share an already-opened camera (it's a single physical device)."""
        self._cap = cap
        self._owns_cap = False

    def check_available(self) -> bool:
        try:
            from deepface import DeepFace  # noqa: F401
        except ImportError:
            return False
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
            from deepface import DeepFace

            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                return False
            ok, _ = cap.read()
            if not ok:
                cap.release()
                return False
            self._deepface = DeepFace
            self._cap = cap
            return True
        except Exception as exc:
            logger.debug("mood start failed: %s", exc)
            return False

    def read(self) -> dict[str, Any]:
        import cv2

        if self._cap is None:
            raise RuntimeError("mood channel not started")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("failed to capture frame")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._deepface.analyze(
            img_path=rgb,
            actions=["emotion"],
            enforce_detection=False,
            detector_backend="opencv",
            silent=True,
        )
        if isinstance(result, list):
            if not result:
                return self._no_face()
            result = result[0]
        emotions = {k: float(v) / 100.0 for k, v in result.get("emotion", {}).items()}
        for emo in EMOTIONS:
            emotions.setdefault(emo, 0.0)
        return {"value": self._dominant_score(emotions), "label": None, "names": emotions}

    @staticmethod
    def _dominant_score(emotions: dict[str, float]) -> float:
        """A single 0-100 'positive mood' number, for the store."""
        score = (
            emotions.get("happy", 0.0) * 1.0
            + emotions.get("neutral", 0.0) * 0.8
            + emotions.get("surprised", 0.0) * 0.6
            + emotions.get("sad", 0.0) * 0.35
            + emotions.get("disgust", 0.0) * 0.2
            + emotions.get("fear", 0.0) * 0.25
            + emotions.get("angry", 0.0) * 0.05
        )
        return round(score * 100.0, 2)

    @staticmethod
    def _no_face() -> dict[str, Any]:
        names = {emo: 0.0 for emo in EMOTIONS}
        names["neutral"] = 1.0
        return {"value": 80.0, "label": None, "names": names}

    def stop(self) -> bool:
        if self._cap is not None and self._owns_cap:
            self._cap.release()
        self._cap = None
        self._deepface = None
        return True
