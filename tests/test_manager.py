"""Manager: mode control, persistence of simulation ticks, state shape."""

from __future__ import annotations

import time

from workwell.manager import MODE_SIMULATION, MODE_STOPPED, Manager


def test_initial_state_shape(manager: Manager):
    snap = manager.state()
    assert snap["mode"] == MODE_STOPPED
    assert snap["scenario"] is None
    assert snap["uptime_s"] is None
    assert set(snap["channels"]) == {"greenery", "noise", "air", "mood", "presence"}
    for ch in snap["channels"].values():
        assert "enabled" in ch and "available" in ch and "error_count" in ch


def test_simulation_writes_all_channels(store, manager: Manager):
    result = manager.start_simulation("calm")
    assert result["ok"]
    time.sleep(0.5)
    manager.stop_all()

    for channel in ("greenery", "noise", "air", "mood", "presence"):
        latest = store.latest(channel)
        assert latest is not None, f"{channel} never persisted"
        assert latest["source"] == "simulation"
    # mood sub-rows persisted too
    assert store.latest("mood", name="happy") is not None


def test_live_to_stop_idempotent(manager: Manager):
    manager.stop_all()
    manager.stop_all()  # double stop must not raise
    assert manager.state()["mode"] == MODE_STOPPED


def test_start_live_fails_cleanly_without_hardware(store, cfg):
    """With no hardware anything, live start must fail with a clear error,
    not crash (this is the no-sensor PC path)."""
    manager = Manager(store, cfg)
    for ch in manager.channels.values():
        ch._available = False  # force 'no hardware' without touching devices
    result = manager.start_live()
    assert result["ok"] is False
    assert "simulation" in result["error"]
    assert manager.state()["mode"] == MODE_STOPPED


def test_switch_simulation_scenario(manager: Manager):
    """Clicking a second scenario while one is running must SWITCH, not refuse."""
    assert manager.start_simulation("focus")["ok"]
    result = manager.start_simulation("stress")
    assert result["ok"], f"scenario switch rejected: {result}"
    assert manager.state()["mode"] == MODE_SIMULATION
    assert manager.state()["scenario"] == "stress"
    manager.stop_all()


def test_state_reflects_mode_and_scenario(manager: Manager):
    manager.start_simulation("meeting")
    snap = manager.state()
    assert snap["mode"] == MODE_SIMULATION
    assert snap["scenario"] == "meeting"
    assert snap["uptime_s"] is not None
    manager.stop_all()


def test_latest_cache_updated(manager: Manager):
    manager.start_simulation("calm")
    time.sleep(0.4)
    snap = manager.state()
    g = snap["channels"]["greenery"]
    assert g.get("value") is not None
    assert g.get("source") == "simulation"
    assert "ts" in g
    manager.stop_all()
