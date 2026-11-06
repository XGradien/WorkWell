/**
 * Channel metadata: one place that knows what each sensor measures,
 * its units, accent color and value range — so every component (cards,
 * sparklines, the dial) renders from the same source of truth.
 */
export const CHANNELS = {
  greenery: {
    label: "Greenery",
    unit: "%",
    blurb: "Share of the camera frame that's plant life",
    color: "#34d399", // emerald-400
    colorDim: "rgba(52, 211, 153, 0.15)",
    domain: [0, 100],
  },
  noise: {
    label: "Noise",
    unit: "",
    blurb: "Ambient sound level, 0 (silent) to 100 (loud)",
    color: "#fbbf24", // amber-400
    colorDim: "rgba(251, 191, 36, 0.15)",
    domain: [0, 100],
  },
  air: {
    label: "Air",
    unit: " ppm",
    blurb: "VOC/pollutant reading from the air sensor",
    color: "#38bdf8", // sky-400
    colorDim: "rgba(56, 189, 248, 0.15)",
    domain: [0, 400],
  },
  mood: {
    label: "Mood",
    unit: "",
    blurb: "Emotion estimate from face analysis (when enabled)",
    color: "#a78bfa", // violet-400
    colorDim: "rgba(167, 139, 250, 0.15)",
    domain: [0, 100],
  },
  presence: {
    label: "Presence",
    unit: "",
    blurb: "People detected in the frame",
    color: "#fb7185", // rose-400
    colorDim: "rgba(251, 113, 133, 0.15)",
    domain: [0, 1],
  },
};

export const CHANNEL_ORDER = ["greenery", "noise", "air", "mood", "presence"];

export const MOOD_NAMES = [
  "angry",
  "disgust",
  "fear",
  "happy",
  "sad",
  "surprised",
  "neutral",
];

/** Color per mood for the mix bar. */
export const MOOD_COLORS = {
  angry: "#f87171",
  disgust: "#a3a3a3",
  fear: "#c084fc",
  happy: "#4ade80",
  sad: "#60a5fa",
  surprised: "#facc15",
  neutral: "#94a3b8",
};

export function formatUptime(seconds) {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}
