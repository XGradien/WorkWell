import Sparkline from "./Sparkline.jsx";
import { CHANNELS, MOOD_COLORS, MOOD_NAMES } from "../lib/channels.js";

function MoodMix({ names }) {
  if (!names) return null;
  const total = MOOD_NAMES.reduce((s, n) => s + (names[n] || 0), 0) || 1;
  return (
    <div className="mt-2">
      <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-slate-800/80">
        {MOOD_NAMES.map((n) => (
          <div
            key={n}
            title={`${n}: ${Math.round(((names[n] || 0) / total) * 100)}%`}
            style={{
              width: `${((names[n] || 0) / total) * 100}%`,
              backgroundColor: MOOD_COLORS[n],
            }}
          />
        ))}
      </div>
      <div className="mt-1 flex gap-2 text-[10px] text-slate-500">
        {MOOD_NAMES.filter((n) => (names[n] || 0) / total > 0.08).map((n) => (
          <span key={n} className="flex items-center gap-1">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: MOOD_COLORS[n] }}
            />
            {n} {Math.round(((names[n] || 0) / total) * 100)}%
          </span>
        ))}
      </div>
    </div>
  );
}

function SourceTag({ source }) {
  if (source === "simulation") {
    return (
      <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-300">
        simulation
      </span>
    );
  }
  if (source === "live") {
    return (
      <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-300">
        live sensor
      </span>
    );
  }
  return null;
}

export default function ChannelCard({ channel, data, points }) {
  const meta = CHANNELS[channel];
  const value = data?.value;
  const hasData = value != null && Number.isFinite(Number(value));

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4 transition-colors hover:border-white/[0.12]">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: meta.color }}
            />
            <h3 className="text-sm font-medium text-slate-200">{meta.label}</h3>
          </div>
          <p className="mt-0.5 text-[11px] leading-snug text-slate-500">{meta.blurb}</p>
        </div>
        <SourceTag source={data?.source} />
      </div>

      <div className="mt-3 flex items-baseline gap-1">
        <span
          className="font-mono text-3xl font-semibold tabular-nums"
          style={{ color: hasData ? meta.color : "#475569" }}
        >
          {hasData ? Math.round(Number(value) * 10) / 10 : "—"}
        </span>
        {hasData && <span className="text-xs text-slate-500">{meta.unit}</span>}
        {data?.label && (
          <span className="ml-auto rounded-md bg-slate-800/70 px-1.5 py-0.5 text-[11px] text-slate-300">
            {data.label}
          </span>
        )}
      </div>

      <div className="mt-3 h-16">
        <Sparkline points={points} color={meta.color} colorDim={meta.colorDim} domain={meta.domain} />
      </div>

      {channel === "mood" && <MoodMix names={data?.names} />}
      {channel === "presence" && hasData && (
        <div className="mt-2 text-[11px] text-slate-400">
          {Number(value) > 0 ? `${Number(value)} person${Number(value) > 1 ? "s" : ""} in frame` : "room empty"}
        </div>
      )}

      {data?.error_count > 0 && (
        <div className="mt-2 text-[11px] text-rose-400/80">
          {data.error_count} read error{data.error_count > 1 ? "s" : ""} since start
        </div>
      )}
    </div>
  );
}
