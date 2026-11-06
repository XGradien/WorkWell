"""Simulator: scenarios drive all channels coherently."""

from __future__ import annotations

import pytest

from workwell.simulator import SCENARIOS, Simulator

SIM_CHANNELS = ("greenery", "noise", "air", "mood", "presence")


def test_scenarios_registered():
    assert set(SCENARIOS) == {"calm", "focus", "meeting", "stress", "dynamic"}
    for s in SCENARIOS.values():
        assert s.title and s.description


def test_start_rejects_unknown():
    sim = Simulator()
    assert sim.start("vibes") is False
    assert sim.active is False


def test_tick_shape():
    sim = Simulator()
    assert sim.start("calm")
    tick = sim.tick()
    for ch in SIM_CHANNELS:
        assert ch in tick, f"missing channel {ch}"
        assert "value" in tick[ch]
    assert set(tick["mood"]["names"]) == {"angry", "disgust", "fear", "happy", "sad", "surprised", "neutral"}


def test_mood_probabilities_sum_to_one():
    sim = Simulator()
    sim.start("stress")
    for _ in range(10):
        tick = sim.tick()
        total = sum(tick["mood"]["names"].values())
        assert abs(total - 1.0) < 0.01


def test_calm_vs_stress_separation():
    """The calm scenario must actually be calmer than stress — that's the
    point of the demo (the v1 bug was that the scenario had no visible effect)."""
    def run(scenario, ticks=40):
        sim = Simulator()
        sim.start(scenario)
        values = {ch: [] for ch in ("greenery", "noise", "air")}
        for _ in range(ticks):
            t = sim.tick()
            for ch in values:
                values[ch].append(t[ch]["value"])
        return {ch: sum(v) / len(v) for ch, v in values.items()}

    calm, stress = run("calm"), run("stress")
    assert calm["greenery"] > stress["greenery"] + 15
    assert stress["noise"] > calm["noise"] + 20
    assert stress["air"] > calm["air"] + 40


def test_values_bounded():
    sim = Simulator()
    sim.start("stress")
    for _ in range(200):
        t = sim.tick()
        assert 0 <= t["greenery"]["value"] <= 100
        assert 0 <= t["noise"]["value"] <= 100
        assert t["air"]["value"] >= 0
        assert 0 <= t["presence"]["value"]


def test_mean_reverting_not_white_noise():
    """Successive ticks should be correlated, not independent white noise."""
    sim = Simulator()
    sim.start("calm")
    vals = [sim.tick()["greenery"]["value"] for _ in range(60)]
    diffs = [abs(b - a) for a, b in zip(vals, vals[1:])]
    assert sum(diffs) / len(diffs) < 8  # small step-to-step change


def test_dynamic_oscillates():
    sim = Simulator()
    sim.start("dynamic")
    greens = [sim.tick()["greenery"]["value"] for _ in range(200)]
    assert max(greens) - min(greens) > 20  # actually moves across the range


def test_stop_resets():
    sim = Simulator()
    sim.start("calm")
    sim.stop()
    assert sim.active is False
    with pytest.raises(RuntimeError):
        sim.tick()


def test_air_labels_match_value():
    from workwell.channels.air import classify_ppm

    sim = Simulator()
    sim.start("stress")
    for _ in range(30):
        t = sim.tick()
        assert t["air"]["label"] == classify_ppm(t["air"]["value"])
