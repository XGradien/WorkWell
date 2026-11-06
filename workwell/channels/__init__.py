"""WorkWell sensor channels.

Each channel owns its hardware (if any) and produces readings in a
shared shape:

    {"value": float, "label": str | None}   (+ "names" for mood)

Channels are stateful: ``start()`` opens the hardware once, ``read()``
is cheap, ``stop()`` releases it. ``available()`` must never open the
device (v1 re-instantiated the camera on every health check).
"""

from .air import AirChannel
from .base import Channel
from .greenery import GreeneryChannel
from .mood import MoodChannel
from .noise import NoiseChannel
from .presence import PresenceChannel

__all__ = [
    "AirChannel",
    "Channel",
    "GreeneryChannel",
    "MoodChannel",
    "NoiseChannel",
    "PresenceChannel",
]
