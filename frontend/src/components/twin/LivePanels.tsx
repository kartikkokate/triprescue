import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Explanation, LearnerSummary, PlaceInfo, TwinNode, TwinState } from "../../types";
import { Icon, ModelBadge, Segmented, timeAgo } from "../../ui";
import { DRIVER_LABEL, pct } from "./format";

// WMO weather code -> label + icon (Open-Meteo)
function wmo(code: number | undefined): [string, string] {
  if (code == null) return ["—", "help"];
  if (code === 0) return ["Clear", "wb_sunny"];
  if (code <= 3) return ["Cloudy", "partly_cloudy_day"];
  if (code <= 48) return ["Fog", "foggy"];
  if (code <= 57) return ["Drizzle", "rainy_light"];
  if (code <= 67) return ["Rain", "rainy"];
  if (code <= 77) return ["Snow", "weather_snowy"];
  if (code <= 82) return ["Showers", "rainy_heavy"];
  return ["Thunderstorm", "thunderstorm"];
}

// --- live strip -----------------------------------------------------------------------------

export function LiveStrip({ state, onRefresh, refreshing }: { state: TwinState; onRefresh: () => void; refreshing: boolean }) {
  const pts = state.history.map((h) => h.p_any_disruption);
  const path = pts.length > 1 ? pts.map((p, i) => `${(i / (pts.length - 1)) * 100},${28 - p * 26}`).join(" ") : "";
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-[repeat(auto-fit,minmax(220px,1fr))]">
      {Object.entries(state.places).map(([name, p], i) => (
        <PlaceCard key={name} name={name} place={p} delay={i * 0.05} />
      ))}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-4 flex flex-col justify-between">
        <div className="flex items-center gap-2 text-[11px]">
          <span className="relative flex h-2 w-2"><span className="absolute inset-0 rounded-full bg-safe animate-ping opacity-75" /><span className="relative h-2 w-2 rounded-full bg-safe" /></span>
          <span className="text-safe-ink font-bold tracking-wide">LIVE TWIN</span>
          <span className="text-ink-3">updated {timeAgo(state.updated_at)}</span>
        </div>
        {path ? (
          <svg viewBox="0 0 100 30" className="w-full h-9 my-1">
            <polyline points={path} fill="none" stroke="#228BE6" strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
          </svg>
        ) : (
          <p className="text-[11px] text-ink-3 my-2">Trip-risk sparkline builds up with each refresh</p>
        )}
        <div className="flex items-center justify-between text-[11px] text-ink-2 tnum">
          <span>{state.sources.forecast_points} forecast points · {state.samples} sims</span>
          <motion.button whileTap={{ rotate: 180 }} onClick={onRefresh} disabled={refreshing} className="text-sky-ink font-semibold flex items-center gap-0.5">
            <Icon name="refresh" className="!text-[16px]" />{refreshing ? "…" : "Refresh"}
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}

function PlaceCard({ name, place, delay }: { name: string; place: PlaceInfo; delay: number }) {
  const c = place.current;
  const [label, icon] = wmo(c?.weather_code);
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }} className="card p-4 flex items-center justify-between gap-3">
      <div>
        <p className="text-[11px] font-semibold text-ink-2 uppercase tracking-wide">{name} · now</p>
        <p className="text-[28px] font-bold tnum leading-9">{c ? `${Math.round(c.temp_c)}°C` : "—"}</p>
        <p className="text-[12px] text-ink-2 flex items-center gap-1">{c ? <><Icon name={icon} className="!text-[16px] text-sky" />{label}</> : place.forecast_live ? "" : "forecast offline"}</p>
      </div>
      <div className="text-right text-[11px] text-ink-2 space-y-1 tnum">
        <p className="flex items-center justify-end gap-1"><Icon name="water_drop" className="!text-[14px] text-sky" />{c?.rain_mm_h ?? 0} mm/h</p>
        <p className="flex items-center justify-end gap-1"><Icon name="air" className="!text-[14px] text-sky" />{c?.wind_kmh ?? 0} km/h</p>
        <p className="flex items-center justify-end gap-1" title="Share of recent public posts / news reporting weather disruption"><Icon name="campaign" className="!text-[14px] text-sky" />social {pct(place.social.social_index)}</p>
      </div>
    </motion.div>
  );
}

// --- social signals -------------------------------------------------------------------------

export function SocialFeed({ places }: { places: Record<string, PlaceInfo> }) {
  const names = Object.keys(places);
  const [tab, setTab] = useState(names[0] ?? "");
  useEffect(() => {
    if (!names.includes(tab)) setTab(names[0] ?? "");
  }, [names.join()]);
  const signals = places[tab]?.social;
  return (
    <div className="card p-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[16px] font-semibold flex items-center gap-2"><Icon name="campaign" className="text-sky" /> Real-world social signals</h3>
        {names.length > 1 && <Segmented size="sm" value={tab} onChange={setTab} options={names.map((n) => ({ value: n, label: n }))} />}
      </div>
      <p className="text-[11px] text-ink-2">Public Mastodon posts + Google News, last {signals?.window_hours ?? 72} h, filtered to weather reports. Their volume feeds the twin as a model feature.</p>
      {signals && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(signals.category_counts).filter(([, v]) => v > 0).map(([k, v]) => (
            <span key={k} className="h-6 px-2.5 rounded-full bg-icy text-sky-ink text-[11px] font-semibold inline-flex items-center">{k.replace("_", " ")} · {v}</span>
          ))}
        </div>
      )}
      <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
        <AnimatePresence mode="popLayout">
          {signals?.items.length ? (
            signals.items.map((it, i) => (
              <motion.a key={it.url + i} href={it.url} target="_blank" rel="noreferrer" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="block rounded-xl bg-canvas border border-line hover:border-sky p-3 transition">
                <p className="text-[12px] text-ink leading-5">{it.text}</p>
                <p className="text-[10px] text-ink-3 mt-1 flex items-center gap-1">
                  <Icon name={it.source === "Mastodon" ? "forum" : "newspaper"} className="!text-[13px]" />
                  {it.source} · {it.author} · {timeAgo(it.published)} · {it.categories.join(", ")}
                  <Icon name="open_in_new" className="!text-[12px] ml-auto" />
                </p>
              </motion.a>
            ))
          ) : (
            <p className="text-[12px] text-ink-3">{signals?.live === false ? "Social feeds unreachable right now." : "No weather reports in the last 72 h."}</p>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// --- AI briefing ---------------------------------------------------------------------------

export function TwinBriefing({ briefing, loading, onRun }: { briefing: Explanation | null; loading: boolean; onRun: () => void }) {
  return (
    <div className="card p-5 space-y-3 relative overflow-hidden">
      {loading && <motion.div className="absolute left-0 top-0 h-0.5 bg-gradient-to-r from-sky-deep to-sky-light" initial={{ width: 0 }} animate={{ width: "100%" }} transition={{ duration: 2.5, repeat: Infinity }} />}
      <div className="flex items-center justify-between">
        <h3 className="text-[16px] font-semibold flex items-center gap-2"><Icon name="psychology" className="text-sky" /> AI twin briefing</h3>
        <button onClick={onRun} disabled={loading} className="btn-primary h-9">{loading ? "Thinking…" : "Brief me"}</button>
      </div>
      <AnimatePresence initial={false}>
        {briefing ? (
          <motion.div key={briefing.explanation} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-2">
            <ModelBadge model={briefing.model} />
            <p className="text-[13px] leading-6 text-ink">{briefing.explanation}</p>
          </motion.div>
        ) : (
          <p className="text-[12px] text-ink-2">Ask the domain-aligned advisor to interpret the current scenario in plain language.</p>
        )}
      </AnimatePresence>
    </div>
  );
}

// --- continuous learning -------------------------------------------------------------------

export function LearningPanel({ learner, nodes, onObserve }: { learner: LearnerSummary; nodes: TwinNode[]; onObserve: (nodeId: string, minutes: number) => Promise<void> }) {
  const exposed = nodes.filter((n) => n.weather_exposed);
  const [nodeId, setNodeId] = useState(exposed[0]?.id ?? "");
  const [minutes, setMinutes] = useState(60);
  const [busy, setBusy] = useState(false);
  const rainIdx = learner.features.indexOf("rain_mm_h");
  useEffect(() => {
    if (!exposed.find((n) => n.id === nodeId)) setNodeId(exposed[0]?.id ?? "");
  }, [nodes]);

  return (
    <div className="card p-5 space-y-3">
      <h3 className="text-[16px] font-semibold flex items-center gap-2"><Icon name="model_training" className="text-sky" /> Continuous learning</h3>
      <p className="text-[11px] text-ink-2">Bayesian weather→delay model per booking type. Each real observation (weather-caused disruptions, live flight status, or a report below) updates it and tightens its uncertainty.</p>
      <div className="grid grid-cols-3 gap-2">
        {Object.entries(learner.models).map(([type, m]) => (
          <div key={type} className="rounded-xl bg-canvas border border-line p-2.5">
            <p className="text-[10px] font-semibold text-ink-2 uppercase">{type}</p>
            <p className="text-[14px] font-semibold tnum">{m.coefficients[rainIdx]}<span className="text-ink-3 text-[11px]"> ± {m.coefficient_sd[rainIdx]}</span></p>
            <p className="text-[10px] text-ink-3">min per mm/h rain</p>
            <p className="text-[10px] text-sky-ink font-semibold mt-1 tnum">{m.observations} observations</p>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-[1fr_90px] gap-2">
        <label>
          <span className="label">Booking</span>
          <select className="input" value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
            {exposed.map((n) => <option key={n.id} value={n.id}>{n.title}</option>)}
          </select>
        </label>
        <label>
          <span className="label">Delay (min)</span>
          <input className="input tnum" type="number" min={0} max={2000} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} />
        </label>
      </div>
      <button
        className="btn-secondary w-full"
        disabled={busy || !nodeId}
        onClick={async () => {
          setBusy(true);
          try {
            await onObserve(nodeId, minutes);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Icon name="add_chart" className="!text-[18px]" /> {busy ? "Learning…" : "Feed observation"}
      </button>
      <AnimatePresence initial={false}>
        {learner.recent_observations.slice(0, 4).map((o) => (
          <motion.div key={o.at} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="text-[11px] text-ink-2 border-l-2 border-sky pl-2 tnum">
            {o.entity_type} · observed {o.observed_delay} min ({o.source.replace(/_/g, " ")}) · predicted {o.predicted_before} → now {o.predicted_after} min
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

export function WeatherAtBooking({ node }: { node: TwinNode | undefined }) {
  if (!node) return null;
  const w = node.weather;
  const items: [string, string, string][] = [
    ["water_drop", "Rain", `${(w.rain_mm_h ?? 0).toFixed(1)} mm/h (${pct(w.precip_prob ?? 0)})`],
    ["air", "Wind", `${(w.wind_kmh ?? 0).toFixed(0)} km/h`],
    ["thermostat", "Temp", `${(w.temp_c ?? 0).toFixed(0)}°C`],
    ["flood", "Flood", pct(w.flood_index ?? 0)],
    ["thunderstorm", "Storm", `${w.storm_hours ?? 0} h`],
  ];
  return (
    <motion.div key={node.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="card p-5">
      <p className="eyebrow mb-1">Weather at selected booking</p>
      <p className="font-semibold text-[15px] mb-3">{node.title}</p>
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        {items.map(([icon, k, v]) => (
          <div key={k} className="rounded-xl bg-canvas border border-line p-2 text-center">
            <Icon name={icon} className="!text-[18px] text-sky" />
            <p className="text-[10px] text-ink-2">{k}</p>
            <p className="text-[12px] font-semibold tnum">{v}</p>
          </div>
        ))}
      </div>
      <p className="text-[12px] text-ink-2 mt-3">
        Most likely: <b className="text-ink">{node.most_likely.replace("_", " ")}</b>
        {node.top_driver && <> · main driver: <b className="text-ink">{DRIVER_LABEL[node.top_driver]}</b></>}
      </p>
    </motion.div>
  );
}
