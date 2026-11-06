"""WorkWell wellness engine.

Turns the recent window of sensor data into:

* a 0-100 wellness score built from every channel that has data
  (greenery, noise, air, mood) — v1 ignored air and mood entirely,
* a plain-English explanation naming the weakest channel,
* actionable recommendations,
* longer-range patterns (hourly noise profile, greenery trend,
  recurring air-quality dips).

Scoring is piecewise-linear over anchor points per channel — readable,
testable, and tunable in config.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .store import Store, parse_ts, utcnow, utcnow_iso

# (value, score) anchors, sorted by value. Linear interpolation between,
# clamped at the ends. Chosen so "typical decent room" lands ~80-90.
_ANCHORS: dict[str, list[tuple[float, float]]] = {
    # greenery %: 0% is stark, 15-35% is the sweet spot, overgrown is fine but
    # not magical
    "greenery": [(0, 10), (10, 45), (20, 75), (35, 100), (70, 90), (100, 70)],
    # noise (0-100 normalized dBn): quiet is great, loud is bad
    "noise": [(0, 95), (25, 100), (45, 90), (60, 65), (75, 40), (90, 15), (100, 5)],
    # air ppm
    "air": [(0, 100), (60, 100), (100, 80), (150, 55), (200, 30), (300, 0)],
    # mood: already a 0-100 positive-mood number, so identity mapping
    "mood": [(0, 0), (100, 100)],
}

RATING_BANDS = ((85, "excellent"), (70, "good"), (50, "fair"), (0, "poor"))


def score_value(channel: str, value: float) -> float:
    """Map one raw reading on a channel to a 0-100 component score."""
    anchors = _ANCHORS[channel]
    if value <= anchors[0][0]:
        return float(anchors[0][1])
    if value >= anchors[-1][0]:
        return float(anchors[-1][1])
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x0 <= value <= x1:
            if x1 == x0:
                return y0
            t = (value - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return float(anchors[-1][1])  # pragma: no cover


def rating_for(score: float) -> str:
    for threshold, label in RATING_BANDS:
        if score >= threshold:
            return label
    return "poor"


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _trend(values: Sequence[float]) -> float:
    """Slope of a first-half vs second-half comparison, per sample."""
    if len(values) < 4:
        return 0.0
    half = len(values) // 2
    return _mean(values[half:]) - _mean(values[:half])


def _span_hours(rows: Sequence[dict[str, Any]]) -> float:
    """Real time span covered by a row set (first -> last ts)."""
    if len(rows) < 2:
        return 0.0
    try:
        t0 = parse_ts(rows[0]["ts"])
        t1 = parse_ts(rows[-1]["ts"])
        return max(0.0, (t1 - t0).total_seconds() / 3600.0)
    except (KeyError, TypeError, ValueError):
        return 0.0


def _fmt_span(hours: float) -> str:
    if hours >= 48:
        return f"{hours / 24.0:.0f} days"
    if hours >= 2:
        return f"{hours:.0f}h"
    return f"{max(1, int(hours * 60))}m"


class WellnessEngine:
    def __init__(self, store: Store, weights: dict[str, float] | None = None):
        self.store = store
        self.weights = weights or {"greenery": 0.3, "noise": 0.3, "air": 0.2, "mood": 0.2}

    # --- score -------------------------------------------------------------

    def score(self, minutes: int = 30) -> dict[str, Any]:
        """Wellness score over the last N minutes.

        Components missing data are dropped and the remaining weights
        renormalized; the response says exactly which channels were used.
        """
        components: dict[str, dict[str, Any]] = {}
        for channel in ("greenery", "noise", "air", "mood"):
            # mood stores a scalar score plus per-emotion sub-rows; score the scalar
            values = self.store.window_values(channel, minutes, scalar_only=(channel == "mood"))
            if not values:
                continue
            latest = values[-1]
            # mood: score the recent average, not the last tick
            basis = _mean(values[-5:]) if channel == "mood" and len(values) > 1 else latest
            components[channel] = {
                "score": round(score_value(channel, basis), 1),
                "latest": round(latest, 2),
                "samples": len(values),
            }

        if not components:
            return {
                "score": None,
                "rating": None,
                "components": {},
                "weakest": None,
                "message": "No sensor data yet. Start live monitoring or a simulation to see your wellness score.",
                "window_minutes": minutes,
                "computed_at": utcnow_iso(),
            }

        total_w = sum(self.weights[c] for c in components)
        overall = sum(components[c]["score"] * self.weights[c] for c in components) / total_w

        weakest = min(components.items(), key=lambda kv: kv[1]["score"])[0]
        return {
            "score": round(overall, 1),
            "rating": rating_for(overall),
            "components": components,
            "weakest": weakest,
            "message": self._message(overall, weakest, components),
            "window_minutes": minutes,
            "computed_at": utcnow_iso(),
        }

    @staticmethod
    def _message(overall: float, weakest: str, components: dict[str, dict[str, Any]]) -> str:
        if overall >= 85:
            return "Your space is in great shape. Keep it up."
        if overall >= 70:
            return f"Solid overall — the thing pulling you down is {weakest}."
        if overall >= 50:
            return f"Decent, but {weakest} is working against you."
        return f"Your environment is costing you focus. Start with {weakest}."

    # --- recommendations ----------------------------------------------------

    def recommendations(self, minutes: int = 60) -> dict[str, Any]:
        score_payload = self.score(minutes)
        recs: list[dict[str, Any]] = []
        components = score_payload.get("components", {})
        now = utcnow()

        for channel, comp in components.items():
            if comp["score"] >= 75:
                continue
            recs.extend(self._channel_recs(channel, comp, now))

        total_samples = sum(c["samples"] for c in components.values())
        if total_samples < 15:
            recs.append({
                "id": "collect-more",
                "channel": "system",
                "priority": "low",
                "title": "Collect a bit more data",
                "detail": "Run monitoring (or a simulation) for a few more minutes so the score has enough samples to trust.",
            })

        recs.sort(key=lambda r: {"high": 0, "medium": 1, "low": 2}[r["priority"]])
        return {
            "recommendations": recs,
            "count": len(recs),
            "window_minutes": minutes,
            "generated_at": utcnow_iso(),
        }

    def _channel_recs(self, channel: str, comp: dict[str, Any], now) -> list[dict[str, Any]]:
        latest = comp["latest"]
        base = {"channel": channel, "id": f"{channel}-{now.timestamp()}", "priority": "medium"}
        if channel == "greenery":
            if latest < 10:
                return [{**base, "priority": "high", "title": "Bring in some green",
                         "detail": f"Only {latest:.0f}% of the frame is green. A pothos on the desk, or repositioning near a window, moves this fast."}]
            return [{**base, "title": "Nudge the greenery up",
                     "detail": f"Greenery is at {latest:.0f}%. Adding one more plant or moving closer to a window gets into the 20-35% sweet spot."}]
        if channel == "noise":
            if latest > 75:
                return [{**base, "priority": "high", "title": "The room is loud",
                         "detail": f"Noise is at {latest:.0f} on the 0-100 scale. Noise-cancelling headphones or moving the session to a quieter spot helps immediately."}]
            return [{**base, "title": "Trim the background noise",
                     "detail": f"Noise sits at {latest:.0f}. Identify the loudest source (HVAC, street, keyboard) and dampen it with soft surfaces or a schedule around it."}]
        if channel == "air":
            if latest > 150:
                return [{**base, "priority": "high", "title": "Air quality is poor",
                         "detail": f"Pollutant reading is {latest:.0f} ppm. Open a window or ventilate for 10 minutes — CO2 levels usually drop quickly."}]
            return [{**base, "title": "Freshen the air",
                     "detail": f"Air reads {latest:.0f} ppm. Short ventilation breaks keep the room in the 'good' band."}]
        if channel == "mood":
            return [{**base, "title": "Check in with yourself",
                     "detail": f"Mood score is {latest:.0f}/100 lately. A 5-minute break away from the screen is the cheapest reset."}]
        return []

    # --- patterns -------------------------------------------------------------

    def patterns(self, days: int = 7) -> dict[str, Any]:
        """Longer-range observations across N days.

        Each pattern only fires when the data actually spans the period the
        claim needs — a 3-minute session must not be presented as a
        "noisiest hour of the week".
        """
        patterns: list[dict[str, Any]] = []

        # 1. noisiest hour of day (needs a full day of coverage)
        noise_rows = self.store.series("noise", minutes=days * 1440)
        noise_span = _span_hours(noise_rows)
        if len(noise_rows) >= 20 and noise_span >= 24:
            by_hour: dict[int, list[float]] = {}
            for row in noise_rows:
                hour = int(row["ts"][11:13])
                by_hour.setdefault(hour, []).append(row["value"])
            full_hours = {h: vs for h, vs in by_hour.items() if len(vs) >= 3}
            if full_hours:
                noisiest_hour, values = max(full_hours.items(), key=lambda kv: _mean(kv[1]))
                quietest_hour, _ = min(full_hours.items(), key=lambda kv: _mean(kv[1]))
                patterns.append({
                    "type": "time_of_day",
                    "title": f"Noisiest around {noisiest_hour:02d}:00",
                    "detail": (f"Across the last {_fmt_span(noise_span)}, average noise peaks at "
                               f"{noisiest_hour:02d}:00 ({_mean(values):.0f}/100) and is quietest near "
                               f"{quietest_hour:02d}:00. Schedule deep work in the quiet window."),
                })

        # 2. greenery trend (needs several hours of coverage)
        green_rows = self.store.series("greenery", minutes=days * 1440)
        green_span = _span_hours(green_rows)
        if len(green_rows) >= 20 and green_span >= 6:
            values = [r["value"] for r in green_rows]
            slope = _trend(values)
            if abs(slope) >= 3:
                direction = "rising" if slope > 0 else "falling"
                patterns.append({
                    "type": "trend",
                    "title": f"Greenery is {direction}",
                    "detail": (f"Greenery has been {direction} by about {abs(slope):.0f} points over the last "
                               f"{_fmt_span(green_span)} "
                               f"({_mean(values[: len(values) // 2]):.0f}% -> "
                               f"{_mean(values[len(values) // 2:]):.0f}%)."),
                })

        # 3. recurring poor air (needs a full day of coverage)
        air_rows = self.store.series("air", minutes=days * 1440)
        air_span = _span_hours(air_rows)
        if len(air_rows) >= 10 and air_span >= 24:
            poor = [r for r in air_rows if r["value"] > 150]
            if len(poor) / len(air_rows) > 0.3:
                patterns.append({
                    "type": "recurring",
                    "title": "Air quality is often poor",
                    "detail": (f"{len(poor)}/{len(air_rows)} readings over the last {_fmt_span(air_span)} "
                               "were above 150 ppm. A standing ventilation habit "
                               "(or checking what spikes it) would help."),
                })

        return {"patterns": patterns, "count": len(patterns), "days": days, "generated_at": utcnow_iso()}
