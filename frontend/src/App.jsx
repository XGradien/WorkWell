import { useWorkWell } from "./hooks/useWorkWell.js";
import Header from "./components/Header.jsx";
import WellnessDial from "./components/WellnessDial.jsx";
import ChannelCard from "./components/ChannelCard.jsx";
import ScenarioControls from "./components/ScenarioControls.jsx";
import Advisories from "./components/Advisories.jsx";
import { CHANNEL_ORDER } from "./lib/channels.js";

export default function App() {
  const {
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
  } = useWorkWell();

  const channels = state?.channels || {};

  return (
    <div className="mx-auto flex min-h-full max-w-[1500px] flex-col gap-4 p-4 lg:p-6">
      <Header state={state} connected={connected} />

      <ScenarioControls
        scenarios={scenarios}
        state={state}
        busy={busy}
        actions={actions}
        error={error}
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        {/* channel grid */}
        <div className="grid content-start gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {CHANNEL_ORDER.map((ch) => (
            <ChannelCard
              key={ch}
              channel={ch}
              data={channels[ch]}
              points={history[ch]}
            />
          ))}
          {/* filler card keeps the grid tidy when mood is disabled */}
          <div className="hidden xl:block" />
        </div>

        {/* right rail */}
        <div className="flex min-h-0 flex-col gap-4">
          <WellnessDial wellness={wellness} />
          <Advisories recommendations={recommendations} patterns={patterns} />
        </div>
      </div>

      <footer className="pb-2 text-center text-[10px] text-slate-700">
        WorkWell v2.0 — all processing happens on this machine. Nothing is
        uploaded anywhere.
      </footer>
    </div>
  );
}
