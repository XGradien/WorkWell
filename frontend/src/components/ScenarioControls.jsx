import { Activity, Camera, Cpu, Pause, Play, Radio, Wind } from "lucide-react";

const SCENARIO_ICONS = {
  calm: <Wind className="h-4 w-4" />,
  focus: <Activity className="h-4 w-4" />,
  meeting: <Radio className="h-4 w-4" />,
  stress: <Cpu className="h-4 w-4" />,
  dynamic: <Play className="h-4 w-4" />,
};

export default function ScenarioControls({
  scenarios,
  state,
  busy,
  actions,
  error,
}) {
  const simRunning = state?.mode === "simulation";
  const liveRunning = state?.mode === "live";

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-slate-200">Demo scenarios</h2>
          <p className="text-[11px] text-slate-500">
            Drive all sensors with a scripted office situation — no hardware needed
          </p>
        </div>
        {simRunning && (
          <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2.5 py-1 text-[11px] font-medium text-amber-300">
            {state.scenario}
          </span>
        )}
        {liveRunning && (
          <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300">
            live sensors
          </span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {scenarios.map((s) => (
          <button
            key={s.name}
            onClick={() => actions.startSimulation(s.name)}
            disabled={busy}
            title={s.description}
            className={`group rounded-xl border px-3 py-2.5 text-left transition-all disabled:opacity-50 ${
              simRunning && state?.scenario === s.name
                ? "border-amber-400/50 bg-amber-400/10"
                : "border-white/[0.07] bg-slate-900/40 hover:border-white/20 hover:bg-slate-900"
            }`}
          >
            <div className="flex items-center gap-1.5 text-slate-200">
              {SCENARIO_ICONS[s.name] || <Play className="h-4 w-4" />}
              <span className="text-xs font-medium capitalize">{s.name}</span>
            </div>
            <p className="mt-1 line-clamp-2 text-[10px] leading-snug text-slate-500 group-hover:text-slate-400">
              {s.description}
            </p>
          </button>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {simRunning || liveRunning ? (
          <button
            onClick={actions.stopAll}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-lg border border-rose-400/30 bg-rose-400/10 px-3 py-1.5 text-xs font-medium text-rose-300 transition-colors hover:bg-rose-400/20 disabled:opacity-50"
          >
            <Pause className="h-3.5 w-3.5" /> Stop
          </button>
        ) : (
          <>
            <button
              onClick={actions.startLive}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-xs font-medium text-emerald-300 transition-colors hover:bg-emerald-400/20 disabled:opacity-50"
            >
              <Camera className="h-3.5 w-3.5" /> Start live sensors
            </button>
            <span className="text-[10px] text-slate-600">
              (needs webcam / mic / air sensor attached)
            </span>
          </>
        )}
        {busy && <span className="text-[11px] text-slate-500">working…</span>}
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-rose-400/20 bg-rose-400/5 px-3 py-2 text-[11px] text-rose-300">
          {error}
        </p>
      )}
    </div>
  );
}
