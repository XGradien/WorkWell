"""Channel base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Channel(ABC):
    """One sensor channel (greenery, noise, air, mood, presence)."""

    #: store channel key, must match store.CHANNELS
    name: str = ""
    unit: str = ""

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg or {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self._available: bool | None = None

    @abstractmethod
    def check_available(self) -> bool:
        """Return True if the hardware for this channel is usable.

        Must be cheap and side-effect free (no opening the device), and
        should cache its result.
        """

    def available(self) -> bool:
        if self._available is None:
            try:
                self._available = self.check_available()
            except Exception:
                self._available = False
        return self.enabled and self._available

    @abstractmethod
    def start(self) -> bool:
        """Open hardware. Returns False (not raises) when unavailable."""

    @abstractmethod
    def read(self) -> dict[str, Any]:
        """One real reading: {"value": float, "label": str | None}."""

    @abstractmethod
    def stop(self) -> bool:
        """Release hardware."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = {True: "available", False: "unavailable", None: "unchecked"}[self._available]
        return f"<{type(self).__name__} {self.name} {state}>"
