"""Wellness engine: scoring, recommendations, patterns — all self-seeded."""

from __future__ import annotations

from workwell.store import Store
from workwell.wellness import WellnessEngine, rating_for, score_value


def test_score_value_anchors():
    assert score_value("greenery", 0) == 10
    assert score_value("greenery", 35) == 100
    assert score_value("noise", 25) == 100
    assert score_value("air", 0) == 100
    assert score_value("air", 300) == 0
    assert score_value("mood", 50) == 50
    # monotonic in the sensible ranges
    assert score_value("greenery", 5) < score_value("greenery", 30)
    assert score_value("noise", 80) < score_value("noise", 30)
    assert score_value("air", 200) < score_value("air", 80)


def test_rating_bands():
    assert rating_for(90) == "excellent"
    assert rating_for(75) == "good"
    assert rating_for(60) == "fair"
    assert rating_for(30) == "poor"


def test_score_no_data(store: Store):
    engine = WellnessEngine(store)
    result = engine.score(30)
    assert result["score"] is None
    assert result["rating"] is None
    assert "No sensor data" in result["message"]


def _seed(store: Store, channel: str, values, start_offset_minutes: float = 0.0):
    """Seed ``values`` one minute apart, ending in the recent past so they
    fall inside the engine's look-back window (never fixed past dates)."""
    from datetime import timedelta

    from workwell.store import utcnow

    base = utcnow() - timedelta(minutes=len(values) + start_offset_minutes)
    for i, v in enumerate(values):
        ts = (base + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.insert(channel, v, ts=ts)


def test_stress_scores_below_calm(store: Store):
    """Same window, two rooms: the stressful room must score lower."""
    engine = WellnessEngine(store)

    _seed(store, "greenery", [60, 62, 58, 61, 59])
    _seed(store, "noise", [25, 27, 24, 26, 25])
    _seed(store, "air", [40, 42, 38, 41, 39])
    _seed(store, "mood", [85, 87, 84, 86, 85])
    calm_score = engine.score(60)["score"]

    store.clear()
    _seed(store, "greenery", [8, 10, 7, 9, 8])
    _seed(store, "noise", [82, 84, 80, 83, 85])
    _seed(store, "air", [170, 165, 175, 168, 172])
    _seed(store, "mood", [25, 30, 22, 28, 26])
    stress_score = engine.score(60)["score"]

    assert calm_score > 85
    assert stress_score < 50
    assert stress_score < calm_score - 30


def test_missing_channel_renormalizes(store: Store):
    engine = WellnessEngine(store)
    _seed(store, "greenery", [30, 31, 29])
    _seed(store, "noise", [30, 31, 29])
    # no air, no mood
    result = engine.score(60)
    assert result["score"] is not None
    assert set(result["components"]) == {"greenery", "noise"}
    assert 0 <= result["score"] <= 100


def test_recommendations_flag_bad_channel(store: Store):
    engine = WellnessEngine(store)
    _seed(store, "noise", [85, 86, 84, 87])
    recs = engine.recommendations(60)
    titles = [r["title"] for r in recs["recommendations"]]
    assert any("loud" in t.lower() for t in titles)
    high = [r for r in recs["recommendations"] if r["priority"] == "high"]
    assert high  # loud room is a high-priority issue


def test_patterns_detect_noisy_hour_and_trend(store: Store):
    from datetime import timedelta

    from workwell.store import utcnow

    engine = WellnessEngine(store)
    base = utcnow() - timedelta(days=3)

    def fmt(offset: timedelta) -> str:
        return (base + offset).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 3 days of noise: one loud hour (80s) and one quiet hour (30s) each day
    for d in range(3):
        for i in range(10):
            ts_loud = fmt(timedelta(days=d, hours=9, minutes=5 * i))
            ts_quiet = fmt(timedelta(days=d, hours=10, minutes=5 * i))
            store.insert("noise", 80 + (i % 5), ts=ts_loud)
            store.insert("noise", 30 + (i % 5), ts=ts_quiet)
    # 30 greenery readings over ~7h, falling 50 -> 21 (slope ~ -15)
    for i in range(30):
        store.insert("greenery", 50 - i, ts=fmt(timedelta(minutes=15 * i)))

    pats = engine.patterns(7)
    types = {p["type"] for p in pats["patterns"]}
    assert "time_of_day" in types
    assert "trend" in types
    trend = next(p for p in pats["patterns"] if p["type"] == "trend")
    assert "falling" in trend["title"]
    # the claim must match the real data span, not the query window
    assert "7 days" not in trend["detail"]


def test_patterns_suppressed_without_enough_history(store: Store):
    """A 30-minute session must not be reported as a weekly pattern."""
    engine = WellnessEngine(store)
    _seed(store, "noise", [80 + (i % 5) for i in range(20)])
    _seed(store, "greenery", [50 - i for i in range(30)])
    pats = engine.patterns(7)
    assert pats["count"] == 0


def test_weights_respected(store: Store):
    heavy = WellnessEngine(store, weights={"greenery": 0.7, "noise": 0.1, "air": 0.1, "mood": 0.1})
    _seed(store, "greenery", [10, 10, 10])  # bad greenery
    _seed(store, "noise", [25, 25, 25])  # good noise
    result = heavy.score(60)
    assert result["components"]["greenery"]["score"] < 50
    assert result["score"] < 60
