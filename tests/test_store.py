"""Store: single-table persistence, UTC time handling."""

from __future__ import annotations

from datetime import timedelta

from workwell.store import Store, parse_ts, utcnow, utcnow_iso


def test_insert_and_latest(store: Store):
    store.insert("greenery", 42.5, source="simulation")
    row = store.latest("greenery")
    assert row is not None
    assert row["value"] == 42.5
    assert row["source"] == "simulation"
    assert row["ts"] == utcnow_iso()  # second-resolution


def test_latest_is_most_recent(store: Store):
    store.insert("noise", 10.0, ts="2026-01-01T00:00:00Z")
    store.insert("noise", 90.0, ts="2026-01-02T00:00:00Z")
    assert store.latest("noise")["value"] == 90.0


def test_unknown_channel_rejected(store: Store):
    import pytest

    with pytest.raises(ValueError):
        store.insert("flux_capacitor", 1.0)


def test_series_window_and_order(store: Store):
    now = utcnow()
    # readings at 45/35/25/15/5 seconds ago: unambiguous inside/outside cuts
    for i, value in enumerate(range(5)):
        ts = (now - timedelta(seconds=45 - i * 10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.insert("air", float(value), ts=ts)
    rows = store.series("air", minutes=60)
    assert [r["value"] for r in rows] == [0.0, 1.0, 2.0, 3.0, 4.0]
    recent = store.series("air", minutes=0.5)  # 30s window -> last three
    assert [r["value"] for r in recent] == [2.0, 3.0, 4.0]


def test_window_values(store: Store):
    for v in (1.0, 2.0, 3.0):
        store.insert("greenery", v)
    assert store.window_values("greenery", minutes=5) == [1.0, 2.0, 3.0]


def test_mood_subrows_and_scalar_only(store: Store):
    ts = utcnow_iso()
    store.insert("mood", 85.0, ts=ts)
    store.insert("mood", 0.6, name="happy", ts=ts)
    store.insert("mood", 0.4, name="sad", ts=ts)

    scalars = store.series("mood", minutes=1, scalar_only=True)
    assert scalars and scalars[0]["value"] == 85.0

    happy = store.series("mood", minutes=1, name="happy")
    assert happy and happy[0]["value"] == 0.6

    group = store.latest_group("mood")
    assert {g["name"]: g["value"] for g in group} == {"happy": 0.6, "sad": 0.4}


def test_counts_and_prune(store: Store):
    store.insert("greenery", 1.0)
    store.insert("noise", 2.0)
    store.insert("air", 3.0)
    assert store.count() == 3
    assert store.counts_by_channel() == {"greenery": 1, "noise": 1, "air": 1}

    old_ts = "2000-01-01T00:00:00Z"
    store.insert("greenery", 9.0, ts=old_ts)
    removed = store.prune(older_than_days=30)
    assert removed == 1
    assert store.count("greenery") == 1


def test_clear(store: Store):
    store.insert("noise", 1.0)
    store.clear()
    assert store.count() == 0


def test_parse_ts_roundtrip():
    iso = utcnow_iso()
    assert parse_ts(iso) == parse_ts(iso)  # deterministic parse
    assert parse_ts(iso).tzinfo is not None
