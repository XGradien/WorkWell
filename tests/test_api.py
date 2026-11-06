"""API contract tests — the full user-visible path over HTTP."""

from __future__ import annotations

import time

SIM = "calm"


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["mode"] == "stopped"


def test_state_shape(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    snap = r.json()
    for key in ("mode", "scenario", "uptime_s", "generated_at", "channels", "wellness"):
        assert key in snap
    assert set(snap["channels"]) == {"greenery", "noise", "air", "mood", "presence"}


def test_simulation_start_requires_body_field(client):
    """Regression: the request model must be a JSON body, not a query param
    (the closure-scope pydantic model bug made this a 422 query error)."""
    r = client.post("/api/simulation/start")
    assert r.status_code in (400, 422)  # missing body -> rejected, not started
    assert client.get("/api/health").json()["mode"] == "stopped"


def test_simulation_start_unknown_scenario(client):
    r = client.post("/api/simulation/start", json={"scenario": "vibes"})
    assert r.status_code == 400


def test_demo_path_end_to_end(client):
    """The acceptance test for the original bug: start the demo and verify
    every channel flows AND the wellness score reacts to the scenario."""
    r = client.post("/api/simulation/start", json={"scenario": "calm"})
    assert r.status_code == 200
    time.sleep(1.2)

    snap = client.get("/api/state").json()
    assert snap["mode"] == "simulation"
    assert snap["scenario"] == "calm"
    for ch in ("greenery", "noise", "air", "mood", "presence"):
        data = snap["channels"][ch]
        assert data.get("value") is not None, f"{ch} never reached the live feed"
        assert data.get("source") == "simulation"
    assert snap["channels"]["mood"].get("names"), "mood mix missing from live feed"

    wellness = client.get("/api/wellness", params={"minutes": 5}).json()
    assert wellness["score"] is not None
    assert wellness["score"] > 70, f"calm room should score high, got {wellness['score']}"

    # switch to stress: the score must come down
    client.post("/api/simulation/stop")
    client.post("/api/simulation/start", json={"scenario": "stress"})
    time.sleep(1.2)
    stressed = client.get("/api/wellness", params={"minutes": 1}).json()
    assert stressed["score"] < wellness["score"] - 20


def test_wellness_validation(client):
    assert client.get("/api/wellness", params={"minutes": 0}).status_code == 400
    assert client.get("/api/wellness", params={"minutes": 999999}).status_code == 400


def test_series_endpoint(client):
    client.post("/api/simulation/start", json={"scenario": "focus"})
    time.sleep(1.2)
    client.post("/api/simulation/stop")

    r = client.get("/api/analytics/series", params={"channel": "greenery", "minutes": 5, "bucket": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["channel"] == "greenery"
    assert len(body["points"]) >= 1
    for p in body["points"]:
        assert set(p) == {"ts", "avg", "min", "max", "n"}
        assert p["min"] <= p["avg"] <= p["max"]

    assert client.get("/api/analytics/series", params={"channel": "bogus"}).status_code == 400


def test_scenario_listing(client):
    r = client.get("/api/simulation/scenarios")
    assert r.status_code == 200
    names = [s["name"] for s in r.json()["scenarios"]]
    assert {"calm", "focus", "meeting", "stress", "dynamic"} == set(names)


def test_recommendations_and_patterns_endpoints(client):
    client.post("/api/simulation/start", json={"scenario": "stress"})
    time.sleep(1.2)
    client.post("/api/simulation/stop")

    recs = client.get("/api/wellness/recommendations", params={"minutes": 2}).json()
    assert recs["count"] == len(recs["recommendations"])
    assert all({"id", "channel", "priority", "title", "detail"} <= set(r) for r in recs["recommendations"])

    pats = client.get("/api/wellness/patterns", params={"days": 7}).json()
    assert "patterns" in pats and "count" in pats


def test_control_stop_stops_everything(client):
    client.post("/api/simulation/start", json={"scenario": "dynamic"})
    assert client.get("/api/health").json()["mode"] == "simulation"
    r = client.post("/api/control/stop")
    assert r.status_code == 200
    assert client.get("/api/health").json()["mode"] == "stopped"


def test_live_start_without_hardware_returns_409(client):
    """No sensors on the test machine -> clean 409 with guidance, not 500."""
    for ch in client.app.state.manager.channels.values():
        ch._available = False
    r = client.post("/api/control/start")
    assert r.status_code == 409
    assert "simulation" in r.json()["detail"]


def test_websocket_streams_state(client):
    client.post("/api/simulation/start", json={"scenario": "calm"})
    with client.websocket_connect("/ws/live") as ws:
        msg = ws.receive_json()
        assert msg["mode"] == "simulation"
        assert "channels" in msg
    client.post("/api/simulation/stop")
