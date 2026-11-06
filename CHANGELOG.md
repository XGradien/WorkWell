# Changelog

All notable changes to WorkWell. The format is inspired by
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.0.0] - 2026-11-06

Complete rebuild of the original CV-Mindcare project.

### What was wrong with v1

- **The demo path was a different pipeline from the live path.** Simulation
  wrote greenery + noise into one table; the live feed read noise from a
  different table and emotions from sensor types nothing ever wrote. Result:
  in the faculty presentation, 2 of 3 sensors displayed frozen zeros while
  the wellness score hovered near 97.
- **The wellness score ignored 2 of the 3 sensors** and its curves were
  untested (a "stress" scenario scored 97 on greenery).
- **Time handling was inconsistent** — a mix of naive local timestamps and
  UTC, off by the timezone offset in queries.
- **A configuration layer nothing read**, four dead duplicate modules, a
  broken CLI entry point, and a test count in the README that did not match
  the suite.

### What changed

- **One data pipeline.** A single SQLite `readings` table with UTC ISO
  timestamps. Real sensors and the simulator both write the same row shape,
  tagged with their `source`. There is nothing left to disagree.
- **Five channels, one manager loop.** greenery, noise, air, mood, presence —
  polled (or simulated) by a single loop that persists and broadcasts.
  Camera channels share one capture device on single-webcam machines.
- **Coherent scenario simulator.** calm / focus / meeting / stress / dynamic
  drive all five channels with mean-reverting motion around scenario targets
  — the stress scenario is actually loud, stuffy and tense; calm is the
  opposite. Verified: the wellness score drops from ~94 (calm) to ~40 (stress)
  on the same window.
- **Wellness engine.** 0–100 score from every channel that has data
  (piecewise-linear, weights in config), a weakest-channel explanation,
  prioritised recommendations, and patterns that only fire when the data
  spans the period they claim.
- **Honest, wired configuration.** `config/workwell.yaml` + `WORKWELL_*` env
  overrides, validated at load, and actually read by every component.
- **Honest availability.** Live start without hardware returns a clear 409
  pointing at simulation mode. Camera/mic are an opt-in extra; the
  TensorFlow mood model — the component that overheated the original
  Raspberry Pi — is a separate opt-in extra, disabled by default.
- **New dashboard.** React + Vite + Tailwind, no chart libraries: streaming
  SVG sparklines per channel, a wellness dial with per-component breakdown,
  one-click scenario controls, live recommendations and patterns over a
  WebSocket (auto-reconnecting).
- **Working entry point.** `workwell` boots one server that serves both the
  API and the built dashboard on a single port.
- **Real test suite.** 56 self-contained tests (store, config, simulator,
  wellness, manager, API over HTTP). The original failure mode is a standing
  regression test: start the demo and assert every channel flows and the
  score drops in the bad scenario.

### Removed

- The three divergent data paths and their shadow tables.
- Duplicate/dead modules (`camera.py` vs `camera_sensor.py` et al.).
- The claim of "302/302 tests passing" (the suite did not say that).

## [1.x] - 2025

Initial CV-Mindcare implementation (final-year project): Raspberry Pi
hardware (webcam, mic, MQ-135), simulation engine, FastAPI backend and React
dashboard. See the original repository for that history.
