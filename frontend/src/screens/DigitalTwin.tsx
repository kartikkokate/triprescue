import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../api";
import { useApp } from "../context";
import type { Explanation, TwinScenario, TwinSimulation, TwinState, TwinWhatIf } from "../types";
import TwinMap from "../components/twin/TwinMap";
import ScenarioControls, { LIVE } from "../components/twin/ScenarioControls";
import { BookingRisks, Ecosystem, EffectChain, TripGauge } from "../components/twin/Panels";
import { LearningPanel, LiveStrip, SocialFeed, TwinBriefing, WeatherAtBooking } from "../components/twin/LivePanels";
import { Chip, ErrorBanner, Icon, Segmented, Skeleton } from "../ui";

const isLive = (s: TwinScenario) => Object.values(s.overrides).every((v) => v === null || v === undefined);

export default function DigitalTwin() {
  const app = useApp();
  const [live, setLive] = useState<TwinState | null>(null);
  const [whatIf, setWhatIf] = useState<TwinWhatIf | null>(null);
  const [scenario, setScenario] = useState<TwinScenario>(LIVE);
  const [presetId, setPresetId] = useState("live");
  const [days, setDays] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<"local" | "route">("local");
  const [briefing, setBriefing] = useState<Explanation | null>(null);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [confirmPromote, setConfirmPromote] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const debounce = useRef<number>();

  const loadLive = (refresh = false) =>
    api.twinState(refresh).then(setLive).catch((e) => setError(e.message));

  useEffect(() => {
    loadLive();
    api.getItinerary().then((it) => setDays(Array.from(new Set(it.nodes.map((n) => n.start.slice(0, 10)))).sort())).catch(() => {});
  }, [app.itineraryVersion, app.twinVersion]);

  useEffect(() => {
    setBriefing(null);
    setConfirmPromote(false);
    if (isLive(scenario)) {
      setWhatIf(null);
      return;
    }
    window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      setRunning(true);
      api.twinSimulate(scenario).then(setWhatIf).catch((e) => setError(e.message)).finally(() => setRunning(false));
    }, 300);
  }, [scenario]);

  const sim: TwinSimulation | null = whatIf ?? live;
  const nodes = useMemo(() => (sim ? Object.values(sim.nodes) : []), [sim]);
  // places ordered by how many bookings they hold, so presets target the trip's main place
  const places = useMemo(() => {
    if (!live) return [];
    const count = (p: string) => Object.values(live.nodes).filter((n) => n.places.includes(p)).length;
    return Object.keys(live.places).sort((a, b) => count(b) - count(a));
  }, [live]);
  const scenarioRain = useMemo(() => {
    const out: Record<string, number> = {};
    nodes.forEach((n) => n.places.forEach((p) => (out[p] = Math.max(out[p] ?? 0, n.weather.rain_mm_h ?? 0))));
    return out;
  }, [nodes]);

  if (!live || !sim) {
    return (
      <div className="space-y-4">
        {error ? <ErrorBanner message={error} onRetry={() => loadLive()} /> : (
          <div className="flex items-center gap-3 text-ink-2 text-sm">
            <motion.span className="h-5 w-5 rounded-full border-2 border-sky border-t-transparent" animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.9, ease: "linear" }} />
            Pulling live weather, flood forecasts and social signals…
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}</div>
        <Skeleton className="h-[440px]" />
      </div>
    );
  }

  const observe = async (nodeId: string, minutes: number) => {
    try {
      const res = await api.twinObserve(nodeId, minutes);
      app.toast(`Learned: predicted ${res.observation.predicted_before} → now ${res.observation.predicted_after} min`, "success");
      await loadLive();
      if (!isLive(scenario)) setScenario({ ...scenario });
    } catch (e: any) {
      app.toast(e.message, "error");
    }
  };

  const promote = async () => {
    setPromoting(true);
    try {
      const res = await api.twinPromote(scenario);
      app.setLastDisruption({ disruption: { node_id: res.origins[0]?.node_id, reason: "weather (digital twin scenario)" }, impact_report: (res as any).impact_report ?? null });
      app.bumpItinerary();
      app.toast(`Scenario applied to your real trip: ${res.origins.length} booking(s) hit. Pick a recovery plan.`, "warn");
      app.go("console");
    } catch (e: any) {
      app.toast(e.message, "error");
    } finally {
      setPromoting(false);
      setConfirmPromote(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Chip><Icon name="radar" className="!text-[14px]" /> WEATHER DIGITAL TWIN</Chip>
          <h1 className="text-[28px] md:text-[32px] font-bold tracking-[-0.02em] mt-2">How weather ripples through {app.tripName}</h1>
          <p className="text-[13px] text-ink-2 mt-1">Live forecast + flood + social signals, {live.samples} simulated futures through your real itinerary graph. What-ifs never touch the real trip.</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={() => { setError(null); loadLive(); }} />}

      <LiveStrip state={live} refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await loadLive(true); setRefreshing(false); }} />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 items-start">
        <div className="lg:col-span-8 space-y-5 min-w-0">
          <div className="relative card p-1.5">
            <TwinMap nodes={nodes} places={sim.places} scenarioRain={scenarioRain} view={view} selectedId={selectedId} onSelect={setSelectedId} />
            <div className="absolute top-4 right-4 z-[500]">
              <Segmented size="sm" value={view} onChange={setView} options={[{ value: "local", label: "Local view" }, { value: "route", label: "Route view" }]} />
            </div>
            <motion.span key={whatIf ? "w" : "l"} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className={`absolute bottom-4 left-4 z-[500] inline-flex items-center gap-1.5 h-7 px-3 rounded-full text-[11px] font-bold border ${whatIf ? "bg-risk-bg text-risk-ink border-amber-300" : "bg-safe-bg text-safe-ink border-emerald-300"}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${whatIf ? "bg-risk" : "bg-safe animate-pulse"}`} />
              {whatIf ? "WHAT-IF SCENARIO (simulated)" : "LIVE FORECAST"}
            </motion.span>
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <TripGauge trip={sim.trip} baseline={whatIf ? whatIf.baseline_trip : undefined} />
            <WeatherAtBooking node={selectedId ? sim.nodes[selectedId] : nodes.slice().sort((a, b) => b.p_broken + b.p_at_risk - (a.p_broken + a.p_at_risk))[0]} />
          </div>
          <BookingRisks nodes={nodes} delta={whatIf?.delta_vs_live} selectedId={selectedId} onSelect={setSelectedId} />
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 items-start">
            <EffectChain chain={sim.effect_chain} />
            <Ecosystem ecosystem={sim.ecosystem} />
          </div>
        </div>

        <div className="lg:col-span-4 space-y-5 lg:sticky lg:top-24">
          <ScenarioControls scenario={scenario} presetId={presetId} places={places} days={days} running={running} onChange={(s, id) => { setScenario(s); setPresetId(id); }} />
          <AnimatePresence>
            {whatIf && whatIf.trip.p_any_disruption >= 0.3 && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
                {confirmPromote ? (
                  <div className="card p-4 border-amber-300 space-y-3">
                    <p className="text-[13px]"><b>Apply this scenario to your real trip?</b> Its most likely outcome becomes a real disruption, and you'll get recovery plans. Nothing is booked.</p>
                    <div className="flex gap-2">
                      <button className="btn-secondary flex-1" onClick={() => setConfirmPromote(false)}>Cancel</button>
                      <button className="btn flex-1 text-white bg-gradient-to-r from-amber-500 to-red-500" disabled={promoting} onClick={promote}>{promoting ? "Applying…" : "Yes, apply"}</button>
                    </div>
                  </div>
                ) : (
                  <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }} onClick={() => setConfirmPromote(true)} className="w-full btn h-12 text-white bg-gradient-to-r from-amber-500 to-red-500 shadow-l2">
                    Apply this scenario to my real trip <Icon name="arrow_forward" className="!text-[18px]" />
                  </motion.button>
                )}
              </motion.div>
            )}
          </AnimatePresence>
          <TwinBriefing
            briefing={briefing}
            loading={briefingLoading}
            onRun={async () => {
              setBriefingLoading(true);
              try {
                setBriefing(await api.twinExplain(isLive(scenario) ? null : scenario));
              } catch (e: any) {
                app.toast(e.message, "error");
              } finally {
                setBriefingLoading(false);
              }
            }}
          />
          <SocialFeed places={live.places} />
          <LearningPanel learner={live.learner} nodes={nodes} onObserve={observe} />
        </div>
      </div>
    </div>
  );
}
