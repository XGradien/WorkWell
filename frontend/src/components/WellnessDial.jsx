import { CHANNELS } from "../lib/channels.js";

const RATING_COLORS = {
  excellent: "#34d399",
  good: "#a3e635",
  fair: "#fbbf24",
  poor: "#fb7185",
};

function Dial({ score, rating }) {
  const size = 176;
  const stroke = 13;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const frac = score == null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  const color = RATING_COLORS[rating] || "#64748b";

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="rgba(148,163,184,0.12)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - frac)}
          style={{ transition: "stroke-dashoffset 700ms ease, stroke 400ms ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono text-5xl font-semibold tabular-nums" style={{ color }}>
          {score == null ? "—" : Math.round(score)}
        </span>
        <span className="mt-1 text-xs uppercase tracking-widest text-slate-400">
          {rating || "no data"}
        </span>
      </div>
    </div>
  );
}

export default function WellnessDial({ wellness }) {
  const components = wellness?.components || {};

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
      <h2 className="text-sm font-medium text-slate-200">Wellness score</h2>
      <p className="text-[11px] text-slate-500">
        Weighted blend of everything the sensors can see, last 5 minutes
      </p>

      <div className="mt-4 flex justify-center">
        <Dial score={wellness?.score} rating={wellness?.rating} />
      </div>

      {wellness?.message && (
        <p className="mt-3 text-center text-xs text-slate-400">{wellness.message}</p>
      )}

      {Object.keys(components).length > 0 && (
        <div className="mt-4 space-y-2">
          {Object.entries(components).map(([channel, comp]) => {
            const meta = CHANNELS[channel];
            if (!meta) return null;
            return (
              <div key={channel} className="flex items-center gap-2">
                <span className="w-16 text-[11px] text-slate-400">{meta.label}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800/80">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.max(2, Math.min(100, comp.score))}%`,
                      backgroundColor: meta.color,
                    }}
                  />
                </div>
                <span className="w-7 text-right font-mono text-[11px] tabular-nums text-slate-300">
                  {Math.round(comp.score)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
