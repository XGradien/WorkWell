"""Scenario simulator for WorkWell.

Generates a coherent "room state" per tick: greenery, noise, air and
mood move together (a stressful room is noisy AND has poor air AND a
bad mood) and follow a mean-reverting random walk, so charts look like
a real room rather than white noise.

This is also the fallback engine for machines with no sensors at all —
the original project's demo depended on exactly this, and v1 had the
pipeline bug where simulated values never reached the live feed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .store import MOOD_NAMES


@dataclass
class ChannelSpec:
    """One channel's simulation behaviour inside a scenario."""

    target: float  # mean-reversion target
    band: float  # allowed drift around the target (absolute)
    jitter: float  # per-tick noise (absolute)


@dataclass
class Scenario:
    name: str
    title: str
    description: str
    channels: dict[str, ChannelSpec]
    mood_mix: dict[str, float]  # target probabilities, sums to 1


def _spec(target: float, band: float, jitter: float) -> ChannelSpec:
    return ChannelSpec(target=target, band=band, jitter=jitter)


SCENARIOS: dict[str, Scenario] = {
    "calm": Scenario(
        name="calm",
        title="Calm room",
        description="Plenty of plants, a quiet space, fresh air, relaxed occupant.",
        channels={
            "greenery": _spec(65, 8, 2.5),
            "noise": _spec(28, 6, 2.0),
            "air": _spec(38, 10, 2.5),
        },
        mood_mix={"happy": 0.55, "neutral": 0.30, "surprised": 0.05, "sad": 0.05, "angry": 0.02, "fear": 0.02, "disgust": 0.01},
    ),
    "focus": Scenario(
        name="focus",
        title="Deep work",
        description="A plain desk, quiet focus, decent air, neutral mood.",
        channels={
            "greenery": _spec(22, 6, 2.0),
            "noise": _spec(34, 5, 1.5),
            "air": _spec(62, 12, 3.0),
        },
        mood_mix={"neutral": 0.62, "happy": 0.18, "surprised": 0.04, "sad": 0.08, "angry": 0.04, "fear": 0.03, "disgust": 0.01},
    ),
    "meeting": Scenario(
        name="meeting",
        title="Busy meeting",
        description="People talking, HVAC struggling, some mood swings.",
        channels={
            "greenery": _spec(15, 5, 1.5),
            "noise": _spec(58, 8, 3.0),
            "air": _spec(95, 15, 4.0),
        },
        mood_mix={"happy": 0.30, "neutral": 0.35, "surprised": 0.10, "sad": 0.10, "angry": 0.10, "fear": 0.03, "disgust": 0.02},
    ),
    "stress": Scenario(
        name="stress",
        title="Stressful room",
        description="No green, loud, stuffy air, tense occupant.",
        channels={
            "greenery": _spec(10, 4, 1.5),
            "noise": _spec(80, 8, 3.5),
            "air": _spec(165, 20, 5.0),
        },
        mood_mix={"angry": 0.30, "sad": 0.28, "fear": 0.14, "neutral": 0.16, "disgust": 0.07, "surprised": 0.03, "happy": 0.02},
    ),
    "dynamic": Scenario(
        name="dynamic",
        title="Day in the room",
        description="Oscillates between calm and stressful over ~2 minute cycles.",
        channels={},  # derived at runtime from calm/stress by phase
        mood_mix={},  # blended at runtime
    ),
}

SIMULATED_CHANNELS = ("greenery", "noise", "air")
SIM_MIN, SIM_MAX = 0.0, 100.0
AIR_MAX_PPM = 300.0


class Simulator:
    """Stateful scenario generator. Call ``tick()`` for one full room state."""

    def __init__(self):
        self.active = False
        self.scenario: Scenario | None = None
        self._values: dict[str, float] = {}
        self._mood: dict[str, float] = {}
        self._phase = 0.0
        self._rand = random.Random(20261106)

    # --- control ---------------------------------------------------------

    def start(self, scenario_name: str = "calm") -> bool:
        scenario = SCENARIOS.get(scenario_name)
        if scenario is None:
            return False
        self.scenario = scenario
        self.active = True
        self._phase = 0.0
        # seed each channel near its target so the first tick is already in range
        for name, spec in scenario.channels.items():
            self._values[name] = self._rand.uniform(spec.target - spec.band / 2, spec.target + spec.band / 2)
        self._mood = dict(scenario.mood_mix)
        if scenario.name == "dynamic":
            self._apply_dynamic(0.0)
        return True

    def stop(self) -> None:
        self.active = False
        self.scenario = None
        self._values.clear()
        self._mood.clear()

    @staticmethod
    def available_scenarios() -> list[dict[str, str]]:
        return [
            {"name": s.name, "title": s.title, "description": s.description}
            for s in SCENARIOS.values()
        ]

    # --- generation ------------------------------------------------------

    def tick(self) -> dict[str, dict[str, object]]:
        """Advance one step and return the full simulated room state.

        Shape: {"greenery": {"value":..., "label":...}, "noise": {...},
                "air": {...}, "mood": {"value":..., "names": {...}},
                "presence": {"value":..., "label":...}}
        """
        if not self.active or self.scenario is None:
            raise RuntimeError("simulator is not running")

        if self.scenario.name == "dynamic":
            self._phase += 1.0
            self._apply_dynamic(self._phase)

        out: dict[str, dict[str, object]] = {}
        for name in SIMULATED_CHANNELS:
            spec = self._spec_for(name)
            value = self._revert(name, spec)
            out[name] = self._format(name, value)
        out["mood"] = self._format_mood()
        out["presence"] = self._format_presence()
        return out

    # --- internals ---------------------------------------------------------

    def _spec_for(self, name: str) -> ChannelSpec:
        if self.scenario and name in self.scenario.channels:
            return self.scenario.channels[name]
        # dynamic scenario keeps a live spec set in _apply_dynamic
        fallback = getattr(self, f"_dyn_{name}", None)
        if fallback is not None:
            return fallback
        raise KeyError(name)

    def _revert(self, name: str, spec: ChannelSpec) -> float:
        value = self._values.get(name, spec.target)
        value += 0.25 * (spec.target - value) + self._rand.gauss(0, spec.jitter)
        # keep loosely inside the band
        lo = max(SIM_MIN, spec.target - spec.band)
        hi = min(SIM_MAX if name != "air" else AIR_MAX_PPM, spec.target + spec.band)
        value = min(max(value, lo), hi)
        self._values[name] = value
        return value

    def _apply_dynamic(self, phase_steps: float) -> None:
        """Blend calm <-> stress along a slow sine (full cycle ~150 ticks)."""
        wave = (1.0 + math.sin(2 * math.pi * phase_steps / 150.0)) / 2.0  # 0..1, 1=calm
        calm, stress = SCENARIOS["calm"], SCENARIOS["stress"]
        for name in SIMULATED_CHANNELS:
            c, s = calm.channels[name], stress.channels[name]
            setattr(self, f"_dyn_{name}", ChannelSpec(
                target=s.target + (c.target - s.target) * wave,
                band=max(s.band, c.band),
                jitter=max(s.jitter, c.jitter),
            ))
            if name not in self._values:
                self._values[name] = getattr(self, f"_dyn_{name}").target
        mix: dict[str, float] = {}
        for emo in MOOD_NAMES:
            c = calm.mood_mix.get(emo, 0.0)
            s = stress.mood_mix.get(emo, 0.0)
            mix[emo] = s + (c - s) * wave
        self._mood_target = mix

    def _format(self, name: str, value: float) -> dict[str, object]:
        if name == "greenery":
            return {"value": round(float(value), 2), "label": None}
        if name == "noise":
            from .channels.noise import classify

            return {"value": round(float(value), 2), "label": classify(value)}
        if name == "air":
            from .channels.air import classify_ppm

            return {"value": round(float(value), 2), "label": classify_ppm(value)}
        raise KeyError(name)

    def _format_mood(self) -> dict[str, object]:
        # ease current probabilities toward the scenario's target mix
        target = getattr(self, "_mood_target", None) or (self.scenario.mood_mix if self.scenario else {})
        for emo in MOOD_NAMES:
            cur = self._mood.get(emo, target.get(emo, 0.0))
            next_val = cur + 0.2 * (target.get(emo, 0.0) - cur) + self._rand.gauss(0, 0.02)
            self._mood[emo] = max(0.0, min(1.0, next_val))
        total = sum(self._mood.values()) or 1.0
        names = {emo: round(v / total, 3) for emo, v in self._mood.items()}
        # single positive-mood number for the store (same formula as MoodChannel)
        score = (
            names.get("happy", 0) * 1.0
            + names.get("neutral", 0) * 0.8
            + names.get("surprised", 0) * 0.6
            + names.get("sad", 0) * 0.35
            + names.get("disgust", 0) * 0.2
            + names.get("fear", 0) * 0.25
            + names.get("angry", 0) * 0.05
        )
        return {"value": round(score * 100.0, 2), "label": None, "names": names}

    def _format_presence(self) -> dict[str, object]:
        # occupied during all scenarios except a sleepy stretch of dynamic
        if self.scenario and self.scenario.name == "dynamic":
            wave = math.sin(2 * math.pi * self._phase / 150.0)
            occupied = wave > -0.6
        else:
            occupied = True
        count = 2 if (self.scenario and self.scenario.name == "meeting") else 1
        return {
            "value": float(count if occupied else 0),
            "label": "occupied" if occupied else "empty",
        }
