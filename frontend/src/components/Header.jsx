import { Leaf } from "lucide-react";
import { formatUptime } from "../lib/channels.js";

const MODE_BADGES = {
  simulation: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  live: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  stopped: "border-slate-500/30 bg-slate-500/10 text-slate-400",
};

export default function Header({ state, connected }) {
  const mode = state?.mode || "stopped";
  return (
    <header className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-teal-600 shadow-lg shadow-emerald-500/20">
          <Leaf className="h-5 w-5 text-slate-950" />
        </div>
        <div>
          <h1 className="text-base font-semibold leading-tight tracking-tight text-slate-100">
            WorkWell
          </h1>
          <p className="text-[11px] leading-tight text-slate-500">
            workspace wellness · local &amp; private
          </p>
        </div>
      </div>

      <span
        className={`rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide ${
          MODE_BADGES[mode] || MODE_BADGES.stopped
        }`}
      >
        {mode === "simulation" ? `simulation · ${state?.scenario}` : mode}
      </span>

      {state?.uptime_s != null && (
        <span className="rounded-full border border-white/[0.07] bg-white/[0.03] px-2.5 py-1 font-mono text-[11px] tabular-nums text-slate-400">
          up {formatUptime(state.uptime_s)}
        </span>
      )}

      <div className="ml-auto flex items-center gap-1.5 text-[11px]">
        <span
          className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-rose-400"}`}
        />
        <span className={connected ? "text-slate-400" : "text-rose-300"}>
          {connected ? "connected" : "reconnecting…"}
        </span>
      </div>
    </header>
  );
}
