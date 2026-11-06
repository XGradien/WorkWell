"""WorkWell data store.

Single normalized ``readings`` table: every sensor channel writes and
reads through this one place. This is the fix for v1's core defect,
where four separate tables each had their own write path and the live
feed read from tables nobody wrote to.

Time handling: all timestamps are UTC ISO-8601 strings
(``YYYY-MM-DDTHH:MM:SSZ``), which sort lexicographically, so range
queries are plain string comparisons.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any

# --- channel registry ------------------------------------------------------

CHANNELS = ("greenery", "noise", "air", "mood", "presence")

# Human display metadata per channel
CHANNEL_META: dict[str, dict[str, str]] = {
    "greenery": {"label": "Greenery", "unit": "%", "description": "Share of the camera frame that is green (plants, vegetation)."},
    "noise": {"label": "Noise", "unit": "dBn", "description": "Ambient sound level, 0-100 normalized from the microphone."},
    "air": {"label": "Air quality", "unit": "ppm", "description": "Air pollutant concentration from the MQ-135 (CO2, NH3, smoke)."},
    "mood": {"label": "Mood", "unit": "", "description": "Dominant occupant mood from facial expression analysis (per-emotion probabilities)."},
    "presence": {"label": "Presence", "unit": "faces", "description": "Number of faces detected in front of the camera."},
}

MOOD_NAMES = ("angry", "disgust", "fear", "happy", "sad", "surprised", "neutral")

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,            -- UTC ISO-8601, e.g. 2026-11-06T10:00:00Z
    channel TEXT NOT NULL,       -- greenery | noise | air | mood | presence
    name TEXT,                   -- sub-metric name (mood: 'happy', 'sad', ...)
    value REAL NOT NULL,
    label TEXT,                  -- text label (air level, noise class, ...)
    source TEXT NOT NULL         -- live | simulation
);
CREATE INDEX IF NOT EXISTS idx_readings_channel_ts ON readings(channel, ts);
CREATE INDEX IF NOT EXISTS idx_readings_channel_name_ts ON readings(channel, name, ts);
CREATE INDEX IF NOT EXISTS idx_readings_source ON readings(source);
"""

# Timestamps are stored without sub-seconds (second resolution is plenty
# for sensor data and keeps the table small).
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    """Current UTC time as a sortable ISO-8601 string."""
    return utcnow().strftime(_TS_FMT)


def parse_ts(ts: str) -> datetime:
    """Parse a stored timestamp back into an aware UTC datetime."""
    return datetime.strptime(ts, _TS_FMT).replace(tzinfo=timezone.utc)


def _minutes_ago_iso(minutes: float) -> str:
    return (utcnow() - timedelta(minutes=minutes)).strftime(_TS_FMT)


class Store:
    """Thread-safe SQLite store for all sensor readings."""

    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    # --- writes ----------------------------------------------------------

    def insert(
        self,
        channel: str,
        value: float,
        *,
        name: str | None = None,
        label: str | None = None,
        source: str = "live",
        ts: str | None = None,
    ) -> None:
        """Insert one reading. ``name`` is used for mood probabilities."""
        if channel not in CHANNELS:
            raise ValueError(f"unknown channel: {channel!r} (expected one of {CHANNELS})")
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO readings (ts, channel, name, value, label, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ts or utcnow_iso(), channel, name, float(value), label, source),
            )
            conn.commit()

    # --- reads -----------------------------------------------------------

    def latest(self, channel: str, name: str | None = None) -> dict[str, Any] | None:
        """Most recent reading for a channel (and optional sub-name)."""
        with closing(self._connect()) as conn:
            if name is not None:
                row = conn.execute(
                    "SELECT ts, value, label, source FROM readings "
                    "WHERE channel = ? AND name = ? ORDER BY id DESC LIMIT 1",
                    (channel, name),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT ts, value, label, source FROM readings "
                    "WHERE channel = ? ORDER BY id DESC LIMIT 1",
                    (channel,),
                ).fetchone()
        return dict(row) if row else None

    def latest_group(self, channel: str) -> list[dict[str, Any]]:
        """All sub-rows of the most recent 'tick' for a channel.

        For mood this returns one row per emotion name from the latest
        tick (the tick is identified by the max id among its rows).
        """
        with closing(self._connect()) as conn:
            max_id = conn.execute(
                "SELECT MAX(id) FROM readings WHERE channel = ?", (channel,)
            ).fetchone()[0]
            if max_id is None:
                return []
            # The tick = rows sharing the latest ts for this channel
            ts = conn.execute(
                "SELECT ts FROM readings WHERE id = ?", (max_id,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT name, value, label FROM readings "
                "WHERE channel = ? AND ts = ? AND name IS NOT NULL ORDER BY name",
                (channel, ts),
            ).fetchall()
        return [dict(r) for r in rows]

    def series(
        self,
        channel: str,
        *,
        minutes: float,
        name: str | None = None,
        limit: int = 10_000,
        scalar_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Readings for a channel in the last N minutes, oldest first.

        ``scalar_only`` restricts to rows without a sub-name (e.g. the
        mood score, not the per-emotion probabilities).
        """
        cutoff = _minutes_ago_iso(minutes)
        with closing(self._connect()) as conn:
            if name is not None:
                rows = conn.execute(
                    "SELECT ts, value, label, source FROM readings "
                    "WHERE channel = ? AND name = ? AND ts >= ? "
                    "ORDER BY ts LIMIT ?",
                    (channel, name, cutoff, limit),
                ).fetchall()
            else:
                name_clause = "AND name IS NULL" if scalar_only else ""
                rows = conn.execute(
                    f"SELECT ts, value, label, source FROM readings "
                    f"WHERE channel = ? {name_clause} AND ts >= ? ORDER BY ts LIMIT ?",
                    (channel, cutoff, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def window_values(self, channel: str, minutes: float, name: str | None = None, scalar_only: bool = False) -> list[float]:
        """Just the values (for statistics), oldest first."""
        return [row["value"] for row in self.series(channel, minutes=minutes, name=name, scalar_only=scalar_only)]

    def count(self, channel: str | None = None) -> int:
        with closing(self._connect()) as conn:
            if channel is None:
                return conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM readings WHERE channel = ?", (channel,)
            ).fetchone()[0]

    def counts_by_channel(self) -> dict[str, int]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT channel, COUNT(*) AS n FROM readings GROUP BY channel"
            ).fetchall()
        return {r["channel"]: r["n"] for r in rows}

    def prune(self, older_than_days: float) -> int:
        """Delete readings older than N days. Returns rows removed."""
        cutoff = (utcnow() - timedelta(days=older_than_days)).strftime(_TS_FMT)
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute("DELETE FROM readings WHERE ts < ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    def clear(self) -> None:
        """Delete all readings (tests / reset)."""
        with self._lock, closing(self._connect()) as conn:
            conn.execute("DELETE FROM readings")
            conn.commit()
