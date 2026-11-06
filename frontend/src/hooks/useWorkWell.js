import { useEffect, useRef, useState, useCallback } from "react";
import { api, connectLive } from "../lib/api.js";
import { CHANNEL_ORDER } from "../lib/channels.js";

const HISTORY_LEN = 120; // ~2-4 min of points at 1-2s intervals
const WELLNESS_POLL_MS = 10_000;
const ADVISORY_POLL_MS = 30_000;

/**
 * Central live state for the dashboard:
 *  - WebSocket stream of /api/state (per-channel value + label + ts)
 *  - rolling history buffer per channel (for sparklines)
 *  - polled wellness score, recommendations and patterns
 */
export function useWorkWell() {
  const [state, setState] = useState(null);
  const [history, setHistory] = useState(() =>
    Object.fromEntries(CHANNEL_ORDER.map((c) => [c, []]))
  );
  const [wellness, setWellness] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [patterns, setPatterns] = useState([]);
  const [connected, setConnected] = useState(false);
  const [scenarios, setScenarios] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const historyRef = useRef(history);
  historyRef.current = history;
  const lastKeyRef = useRef("");

  const pushHistory = useCallback((snapshot) => {
    const channels = snapshot?.channels || {};
    const next = { ...historyRef.current };
    let changed = false;
    for (const ch of CHANNEL_ORDER) {
      const data = channels[ch];
      const key = data?.ts;
      if (!key || key === lastKeyRef.current) continue;
      const value = Number(data.value);
      if (!Number.isFinite(value)) continue;
      const prev = next[ch];
      next[ch] = [...prev.slice(-(HISTORY_LEN - 1)), { ts: data.ts, value }];
      changed = true;
    }
    if (changed) {
      lastKeyRef.current = Object.values(channels)
        .map((d) => d?.ts)
        .filter(Boolean)
        .sort()
        .pop() || lastKeyRef.current;
      setHistory(next);
    }
  }, []);

  // WebSocket lifecycle
  useEffect(() => {
    const disconnect = connectLive(
      (snapshot) => {
        setState(snapshot);
        pushHistory(snapshot);
        setError(null);
      },
      { onOpen: setConnected }
    );
    return disconnect;
  }, [pushHistory]);

  // Scenario catalog (static, fetch once)
  useEffect(() => {
    api
      .scenarios()
      .then((r) => setScenarios(r.scenarios || []))
      .catch((e) => setError(e.message));
  }, []);

  // Wellness score: poll only while something is running
  const running = state && state.mode !== "stopped";
  useEffect(() => {
    if (!running) return;
    let alive = true;
    const tick = async () => {
      try {
        const w = await api.wellness(5);
        if (alive) setWellness(w);
      } catch {
        /* backend briefly busy — next tick retries */
      }
    };
    tick();
    const id = setInterval(tick, WELLNESS_POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [running, state?.scenario]);

  // Recommendations + patterns: slow poll while running
  useEffect(() => {
    if (!running) return;
    let alive = true;
    const tick = async () => {
      try {
        const [recs, pats] = await Promise.all([
          api.recommendations(5),
          api.patterns(7),
        ]);
        if (alive) {
          setRecommendations(recs.recommendations || []);
          setPatterns(pats.patterns || []);
        }
      } catch {
        /* non-fatal */
      }
    };
    tick();
    const id = setInterval(tick, ADVISORY_POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [running, state?.scenario]);

  const control = useCallback(
    async (fn) => {
      setBusy(true);
      try {
        await fn();
        setError(null);
      } catch (e) {
        setError(e.message);
      } finally {
        setBusy(false);
      }
    },
    []
  );

  const actions = {
    startSimulation: (scenario) => control(() => api.startSimulation(scenario)),
    stopSimulation: () => control(() => api.stopSimulation()),
    startLive: () => control(() => api.startLive()),
    stopAll: () => control(() => api.stopAll()),
  };

  return {
    state,
    history,
    wellness,
    recommendations,
    patterns,
    connected,
    scenarios,
    error,
    busy,
    actions,
  };
}
