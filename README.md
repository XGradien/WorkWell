# WorkWell

**Local, privacy-first workspace wellness monitoring.** WorkWell watches the
physical side of your workspace — how much green there is, how loud it is, the
air, and (optionally) your mood — and folds it into a single live wellness
score with plain-English recommendations.

Everything runs on your machine. No cloud, no accounts, no telemetry.

---

## Why this project exists

WorkWell began as **CV-Mindcare**, a final-year student project: a Raspberry
Pi with a camera, a mic and an air sensor that was supposed to score how
healthy your workspace is. The hardware worked, but the software it ran on was
a first-draft mess — three parallel data paths that disagreed with each other,
and in the faculty demo two of the three sensors sat at a frozen zero while
the wellness score stayed cheerfully at 97. The Pi itself overheated running
the full perception stack.

v2 is a ground-up rebuild around one rule: **one data pipeline.** Every value
— real sensor or simulation — flows through the same store, the same
wellness engine, the same dashboard. The demo mode is no longer a separate
thing that "pretends"; it feeds the exact same pipeline with tagged
`source="simulation"` rows, which is why the demo now actually demonstrates
the system.

The perception stack also got honest about itself: the heavy TensorFlow
emotion model (the thing that cooked the Pi) is an opt-in extra, off by
default, and everything else runs on a laptop.

## Quickstart

```bash
# 1. Backend
python -m venv .venv
.venv/bin/pip install -e ".[dev,sensors]"   # add [ml] for face-based mood
workwell                                   # API + dashboard on http://127.0.0.1:8000

# 2. Dashboard dev mode (optional, hot reload)
cd frontend
npm install
npm run dev                                # http://localhost:5173
```

No sensors attached? No problem — open the dashboard and click a **demo
scenario**. Calm, Focus, Meeting, Stress and Dynamic each drive all five
channels with coherent, mean-reverting motion, and the wellness score reacts
in real time. That is the demo.

## What it does

| Channel | Measures | Source |
|---|---|---|
| **Greenery** | % of camera frame that is plant life | webcam (OpenCV HSV) |
| **Noise** | Ambient sound level 0–100 | microphone (RMS) |
| **Air** | VOC/pollutant reading in ppm | MQ-135 via ADC (Pi) or simulated |
| **Mood** | 0–100 positive-mood score + emotion mix | DeepFace (opt-in, off by default) |
| **Presence** | People detected in frame | webcam |

On top of the raw channels, the **wellness engine** produces:

- a **0–100 score** built from every channel that has data (piecewise-linear
  curves per channel, weights tunable in config),
- a **plain-English explanation** that names the weakest channel,
- **recommendations** prioritised by how bad the problem is
  ("The room is loud — noise is at 82. Noise-cancelling headphones help
  immediately."),
- **longer-range patterns** (noisiest hour, greenery trends, recurring poor
  air) — each only reported when the data actually spans the period the claim
  needs. A three-minute session is never presented as a weekly pattern.

## Architecture

```
channels/          greenery · noise · air · mood · presence
  └── each one: check_available() → start() → read() → {"value", "label"}
          │
          │   real hardware        scenario simulator
          ▼                        (calm/focus/meeting/stress/dynamic)
manager.py         ONE polling loop, live or simulation, never both
          │
          ▼
store.py           single SQLite `readings` table, UTC ISO timestamps,
                   every row tagged with its source
          │
          ├──► wellness.py   score · recommendations · patterns
          ├──► REST /api/*   state, wellness, analytics, control
          └──► WebSocket /ws/live   full snapshot every second
                        │
                        ▼
frontend/          React + Vite + Tailwind dashboard: streaming sparklines,
                   wellness dial, scenario controls, advisories
```

Notable properties:

- **One write path.** Simulation and live data are indistinguishable in the
  pipeline except for their `source` tag. There is no second table, no
  shadow feed.
- **Camera sharing.** On a single-webcam machine the camera channels attach
  to one capture device instead of fighting over it.
- **Honest config.** `config/workwell.yaml` (plus `WORKWELL_*` env vars) is
  read by every component — there is no configuration the code ignores.
- **Honest availability.** Starting live collection without hardware fails
  with a clear 409 and a pointer to simulation mode, not a crash.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | liveness + version + mode |
| `GET /api/state` | full snapshot: mode, uptime, per-channel latest |
| `GET /api/wellness?minutes=N` | score, components, message |
| `GET /api/wellness/recommendations?minutes=N` | prioritised advice |
| `GET /api/wellness/patterns?days=N` | longer-range patterns |
| `GET /api/analytics/series?channel=X&minutes=N&bucket=S` | bucketed history |
| `GET /api/simulation/scenarios` | scenario catalog |
| `POST /api/simulation/start {"scenario": "calm"}` | start/switch scenario |
| `POST /api/simulation/stop` | stop simulation |
| `POST /api/control/start` | start live sensor collection |
| `POST /api/control/stop` | stop everything |
| `WS /ws/live` | full state snapshot every second |

Interactive docs: `http://127.0.0.1:8000/docs`.

## Hardware & limitations

What this repo supports today:

- **Webcam** (greenery + presence) — works on Windows/Linux/macOS with any
  UVC camera.
- **Microphone** (noise) — via `sounddevice`; any default input device.
- **MQ-135 air sensor** — wired to an ADS1115 ADC on a Raspberry Pi; this is
  the path from the original project. Without the ADC, air runs simulated.
- **DeepFace mood** — deliberately heavy. `pip install -e ".[ml]"` pulls
  TensorFlow; expect high CPU and it is disabled by default
  (`channels.mood.enabled: false`). On a Raspberry Pi 4 this is what you do
  *not* want running unattended — it is the component that overheated the
  original build.

Honest limits:

- Greenery is a heuristic (HSV green-pixel ratio), not plant recognition. It
  measures "does this room look planted", not "what species".
- Noise is a level, not a source. It tells you *when* it's loud, not *what*.
- The wellness score is a **local heuristic for feedback and experimentation**,
  not a medical or scientific measurement.

## Development

```bash
pytest          # 56 self-contained tests, no hardware required
ruff check .    # lint
```

The test suite covers the store, config, simulator, wellness engine, manager
and the full API over HTTP — including the original failure mode as a
regression test: start the demo and assert that every channel flows *and*
that the wellness score actually drops in the stressful scenario.

## Layout

```
workwell/            backend package
  app.py             FastAPI factory + static dashboard mount
  manager.py         the single polling loop
  store.py           SQLite persistence, UTC time handling
  simulator.py       scenario engine (mean-reverting, coherent)
  wellness.py        score / recommendations / patterns
  channels/          greenery, noise, air, mood, presence + base
  config.py          validated config (yaml + env)
frontend/            React dashboard (Vite, Tailwind, no chart libs)
tests/               pytest suite
config/              default workwell.yaml
```

## License

MIT.

Built by Salman Al-Sahli (v2) — the original CV-Mindcare (v1) was a
final-year project built with a classmate, whose hardware work (Raspberry
Pi, webcam, mic, MQ-135) is what this rebuild runs on.
