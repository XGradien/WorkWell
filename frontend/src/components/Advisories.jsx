import { Lightbulb, Sparkles } from "lucide-react";
import { CHANNELS } from "../lib/channels.js";

const PRIORITY_STYLES = {
  high: "border-rose-400/25 bg-rose-400/[0.07] text-rose-300",
  medium: "border-amber-400/25 bg-amber-400/[0.07] text-amber-300",
  low: "border-slate-400/20 bg-slate-400/[0.06] text-slate-300",
};

export default function Advisories({ recommendations, patterns }) {
  const hasContent = recommendations.length > 0 || patterns.length > 0;

  return (
    <div className="flex min-h-0 flex-col gap-4">
      {recommendations.length > 0 && (
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
          <h2 className="flex items-center gap-2 text-sm font-medium text-slate-200">
            <Lightbulb className="h-4 w-4 text-amber-300" /> Recommendations
          </h2>
          <ul className="mt-3 space-y-2">
            {recommendations.map((r) => (
              <li
                key={r.id}
                className={`rounded-xl border px-3 py-2 ${PRIORITY_STYLES[r.priority] || PRIORITY_STYLES.low}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium">{r.title}</span>
                  <span className="rounded-full bg-slate-900/60 px-1.5 py-0.5 text-[9px] uppercase tracking-wide opacity-70">
                    {r.channel === "system" ? "system" : CHANNELS[r.channel]?.label || r.channel}
                  </span>
                </div>
                <p className="mt-1 text-[11px] leading-snug text-slate-400">{r.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {patterns.length > 0 && (
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
          <h2 className="flex items-center gap-2 text-sm font-medium text-slate-200">
            <Sparkles className="h-4 w-4 text-violet-300" /> Patterns
          </h2>
          <ul className="mt-3 space-y-2">
            {patterns.map((p) => (
              <li
                key={p.title}
                className="rounded-xl border border-violet-400/15 bg-violet-400/[0.05] px-3 py-2"
              >
                <span className="text-xs font-medium text-violet-200">{p.title}</span>
                <p className="mt-1 text-[11px] leading-snug text-slate-400">{p.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!hasContent && (
        <div className="flex flex-1 items-center justify-center rounded-2xl border border-dashed border-white/[0.08] p-6 text-center text-xs text-slate-600">
          {state_hint()}
        </div>
      )}
    </div>
  );
}

function state_hint() {
  return "Run a scenario or live collection and this panel fills with tailored advice and longer-range patterns.";
}
