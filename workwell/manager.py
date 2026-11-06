"""WorkWell collector manager.

One background loop drives everything:

* LIVE mode — polls each enabled channel on its own interval, using real
  hardware where available; camera channels share a single capture device.
* SIMULATION mode — ticks the scenario simulator and writes every channel
  (greenery, noise, air, mood, presence) with source="simulation".

Both paths persist through the same Store and update the same in-memory
``latest`` cache, so REST and WebSocket clients always read one truth.
This single write path is what fixes v1's frozen-sensor demo bug.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .channels import (
    AirChannel,
    GreeneryChannel,
    MoodChannel,
    NoiseChannel,
    PresenceChannel,
)
from .simulator import Simulator
from .store import CHANNELS, Store, utcnow_iso

logger = logging.getLogger(__name__)

MODE_STOPPED = "stopped"
MODE_LIVE = "live"
MODE_SIMULATION = "simulation"

CAMERA_CHANNELS = ("greenery", "presence", "mood")


class Manager:
    def __init__(self, store: Store, config):
        self.store = store
        self.cfg = config
        self.channels: dict[str, Any] = self._build_channels()
        self.simulator = Simulator()

        self.mode = MODE_STOPPED
        self.scenario: str | None = None
        self.started_at: str | None = None
        self._start_time: float | None = None

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.latest: dict[str, dict[str, Any]] = {}
        self.errors: dict[str, int] = {c: 0 for c in CHANNELS}

        self.sim_interval = float(self.cfg.get("simulation.interval", 2.0))

    # --- construction ------------------------------------------------------

    def _build_channels(self) -> dict[str, Any]:
        return {
            "greenery": GreeneryChannel(self.cfg.get("channels.greenery", {})),
            "noise": NoiseChannel(self.cfg.get("channels.noise", {})),
            "air": AirChannel(self.cfg.get("channels.air", {})),
            "mood": MoodChannel(self.cfg.get("channels.mood", {})),
            "presence": PresenceChannel(self.cfg.get("channels.presence", {})),
        }

    # --- control -------------------------------------------------------------

    def start_live(self) -> dict[str, Any]:
        """Start real-hardware collection for whatever is available."""
        with self._lock:
            if self.mode != MODE_STOPPED:
                return self._control_error("already running")
            started: dict[str, bool] = {}
            camera_owner: Any | None = None
            for name in CAMERA_CHANNELS:
                ch = self.channels[name]
                if not ch.available():
                    started[name] = False
                    continue
                if camera_owner is None:
                    ok = ch.start()
                    if ok:
                        camera_owner = ch
                else:
                    ch.attach(camera_owner._cap)
                    ok = True
                started[name] = ok
            for name in ("noise", "air"):
                ch = self.channels[name]
                started[name] = ch.start() if ch.available() else False

            if not any(started.values()):
                self._stop_channels()
                return self._control_error("no sensors available — use simulation mode")

            self.mode = MODE_LIVE
            self.scenario = None
            self._start_time = time.time()
            self.started_at = utcnow_iso()
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._polling_loop, daemon=True, name="workwell-live")
            self._thread.start()
            logger.info("live collection started: %s", started)
            return {"ok": True, "started": started, "mode": MODE_LIVE}

    def start_simulation(self, scenario: str = "calm") -> dict[str, Any]:
        with self._lock:
            # Live mode: tear hardware down first.
            if self.mode == MODE_LIVE:
                self._stop_channels()
                self.mode = MODE_STOPPED
            thread = None
            if self.mode == MODE_SIMULATION:
                # Scenario switch: stop the running loop and restart with the
                # new one — clicking "calm" while "stress" runs must switch,
                # not refuse.
                self._stop_event.set()
                thread = self._thread
                self.mode = MODE_STOPPED
                self._thread = None
            if self.mode != MODE_STOPPED:
                return self._control_error("already running")
        if thread is not None:
            thread.join(timeout=5)
        with self._lock:
            self.simulator.stop()
            self._stop_channels()
            if not self.simulator.start(scenario):
                return self._control_error(f"unknown scenario: {scenario}")
            self.mode = MODE_SIMULATION
            self.scenario = scenario
            self._start_time = time.time()
            self.started_at = utcnow_iso()
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._simulation_loop, daemon=True, name="workwell-sim"
            )
            self._thread.start()
            logger.info("simulation started: %s", scenario)
            return {"ok": True, "scenario": scenario, "mode": MODE_SIMULATION}

    def stop_all(self) -> dict[str, Any]:
        with self._lock:
            if self.mode == MODE_STOPPED:
                return {"ok": True, "mode": MODE_STOPPED}
            self._stop_event.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        with self._lock:
            self.simulator.stop()
            self._stop_channels()
            self.mode = MODE_STOPPED
            self.scenario = None
            self._start_time = None
            self.started_at = None
            self._thread = None
        logger.info("collection stopped")
        return {"ok": True, "mode": MODE_STOPPED}

    @staticmethod
    def _control_error(message: str) -> dict[str, Any]:
        return {"ok": False, "error": message}

    def _stop_channels(self) -> None:
        for ch in self.channels.values():
            try:
                ch.stop()
            except Exception:
                pass

    # --- loops ----------------------------------------------------------------

    def _polling_loop(self) -> None:
        next_run: dict[str, float] = {
            name: time.time()
            for name, ch in self.channels.items()
            if ch.enabled and ch.available()
        }
        intervals = {name: float(self.cfg.get(f"channels.{name}.interval", 5.0)) for name in self.channels}
        while not self._stop_event.is_set():
            now_t = time.time()
            for name, ch in self.channels.items():
                if name not in next_run or now_t < next_run[name]:
                    continue
                next_run[name] = now_t + intervals[name]
                try:
                    reading = ch.read()
                except Exception as exc:
                    self.errors[name] += 1
                    logger.debug("channel %s read failed: %s", name, exc)
                    continue
                self._record(name, reading, source="live")
            self._stop_event.wait(0.2)

    def _simulation_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                tick = self.simulator.tick()
            except Exception as exc:
                logger.error("simulator tick failed: %s", exc)
                self._stop_event.wait(1.0)
                continue
            for name, reading in tick.items():
                self._record(name, reading, source="simulation")
            self._stop_event.wait(self.sim_interval)

    def _record(self, channel: str, reading: dict[str, Any], source: str) -> None:
        value = float(reading.get("value", 0.0))
        label = reading.get("label")
        ts = utcnow_iso()
        self.store.insert(channel, value, label=label, source=source, ts=ts)
        names = reading.get("names")
        if names:  # mood sub-rows
            for emo, prob in names.items():
                self.store.insert(channel, float(prob), name=emo, source=source, ts=ts)
        with self._lock:
            self.latest[channel] = {
                "value": value,
                "label": label,
                "names": names,
                "source": source,
                "ts": ts,
            }

    # --- state ------------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        """Full snapshot for /api/state and the WebSocket stream."""
        from . import __version__

        channels_out: dict[str, Any] = {}
        for name, ch in self.channels.items():
            entry: dict[str, Any] = {
                "enabled": ch.enabled,
                "available": ch.available(),
                "error_count": self.errors[name],
            }
            latest = self.latest.get(name)
            if latest:
                entry.update(latest)
            channels_out[name] = entry
        return {
            "version": __version__,
            "mode": self.mode,
            "scenario": self.scenario,
            "started_at": self.started_at,
            "uptime_s": round(time.time() - self._start_time, 1) if self._start_time and self.mode != MODE_STOPPED else None,
            "generated_at": utcnow_iso(),
            "channels": channels_out,
        }
