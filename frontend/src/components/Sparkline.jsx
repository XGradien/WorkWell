/**
 * Lightweight SVG streaming sparkline — a rolling buffer of {ts, value}
 * points, rendered as a smoothed line with a soft gradient fill.
 *
 * Zero chart-library dependencies: the whole dashboard streams at 1-2s
 * cadence and this re-renders a single <svg> per channel per push.
 */
export default function Sparkline({
  points,
  color,
  colorDim,
  domain,
  width = 260,
  height = 64,
}) {
  const [min, max] = domain;
  const pad = 4;

  if (!points || points.length < 2) {
    return (
      <div
        className="flex h-full w-full items-center justify-center text-[11px] text-slate-600"
        style={{ height }}
      >
        awaiting data…
      </div>
    );
  }

  const values = points.map((p) => p.value);
  const lo = Math.min(min, ...values);
  const hi = Math.max(max, ...values);
  const span = hi - lo || 1;

  const x = (i) => pad + (i / (points.length - 1)) * (width - pad * 2);
  const y = (v) => height - pad - ((v - lo) / span) * (height - pad * 2);

  // Catmull-Rom -> cubic bezier for a smooth but honest line
  let d = `M ${x(0).toFixed(2)} ${y(values[0]).toFixed(2)}`;
  for (let i = 0; i < values.length - 1; i++) {
    const p0 = values[Math.max(0, i - 1)];
    const p1 = values[i];
    const p2 = values[i + 1];
    const p3 = values[Math.min(values.length - 1, i + 2)];
    const c1x = x(i) + (x(i + 1) - x(Math.max(0, i - 1))) / 6;
    const c1y = y(p1) + (y(p2) - y(p0)) / 6;
    const c2x = x(i + 1) - (x(Math.min(values.length - 1, i + 2)) - x(i)) / 6;
    const c2y = y(p2) - (y(p3) - y(p1)) / 6;
    d += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(
      2
    )}, ${x(i + 1).toFixed(2)} ${y(p2).toFixed(2)}`;
  }

  const last = values[values.length - 1];
  const area = `${d} L ${x(values.length - 1).toFixed(2)} ${height - pad} L ${x(
    0
  ).toFixed(2)} ${height - pad} Z`;
  const gid = `spark-${color.replace(/[^a-z0-9]/gi, "")}`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-full w-full"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={x(values.length - 1)}
        cy={y(last)}
        r="2.6"
        fill={color}
        className="animate-pulse"
      />
    </svg>
  );
}
