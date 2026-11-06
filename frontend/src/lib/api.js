/**
 * WorkWell API client.
 *
 * REST endpoints are relative (/api/...) so the Vite dev proxy forwards them
 * to the backend; in production the API serves the built frontend itself,
 * keeping everything same-origin and on-device.
 */

async function get(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "")
  ).toString();
  const url = `${path}${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not json */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

async function post(path, payload = {}) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not json */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export const api = {
  health: () => get("/api/health"),
  state: () => get("/api/state"),
  wellness: (minutes = 5) => get("/api/wellness", { minutes }),
  recommendations: (minutes = 5) => get("/api/wellness/recommendations", { minutes }),
  patterns: (days = 7) => get("/api/wellness/patterns", { days }),
  scenarios: () => get("/api/simulation/scenarios"),
  startSimulation: (scenario) => post("/api/simulation/start", { scenario }),
  stopSimulation: () => post("/api/simulation/stop"),
  startLive: () => post("/api/control/start"),
  stopAll: () => post("/api/control/stop"),
};

/**
 * Open the live WebSocket with auto-reconnect. `onState` receives the full
 * state object on every push; `onOpen`/`onClose` track the link.
 */
export function connectLive(onState, { onOpen, onClose } = {}) {
  let ws = null;
  let closed = false;
  let retry = 0;

  function open() {
    if (closed) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/live`);
    ws.onopen = () => {
      retry = 0;
      onOpen?.(true);
    };
    ws.onmessage = (ev) => {
      try {
        onState(JSON.parse(ev.data));
      } catch {
        /* malformed frame — ignore */
      }
    };
    ws.onclose = () => {
      onOpen?.(false);
      onClose?.();
      if (!closed) {
        const delay = Math.min(1000 * 2 ** retry, 8000);
        retry += 1;
        setTimeout(open, delay);
      }
    };
    ws.onerror = () => ws?.close();
  }

  open();
  return () => {
    closed = true;
    ws?.close();
  };
}
