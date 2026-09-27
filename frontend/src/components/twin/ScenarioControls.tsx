import { motion } from "framer-motion";
import type { TwinOverrides, TwinScenario } from "../../types";
import { Icon } from "../../ui";

export const LIVE: TwinScenario = { overrides: {}, target_place: "all", target_date: null };

/** Presets are built from the trip itself: its main place and its days. */
export function buildPresets(mainPlace: string | undefined, days: string[]) {
  const place = mainPlace ?? "all";
  const mid = days[1] ?? days[0] ?? null;
  const first = days[0] ?? null;
  return [
    { id: "live", label: "Live forecast", icon: "sensors", scenario: LIVE },
    { id: "normal", label: "Normal day", icon: "wb_sunny", scenario: { overrides: { rain_mm_h: 0, wind_kmh: 10, temp_c: 30, storm_hours: 0, flood_index: 0 }, target_place: "all", target_date: null } },
    { id: "monsoon", label: "Heavy monsoon", icon: "rainy", scenario: { overrides: { rain_mm_h: 35, storm_hours: 10, wind_kmh: 35, flood_index: 0.2 }, target_place: place, target_date: mid } },
    { id: "flood", label: "Flash flood", icon: "flood", scenario: { overrides: { rain_mm_h: 50, storm_hours: 18, flood_index: 0.9 }, target_place: place, target_date: first } },
    { id: "cyclone", label: "Cyclone", icon: "cyclone", scenario: { overrides: { rain_mm_h: 70, wind_kmh: 95, storm_hours: 24, flood_index: 0.8 }, target_place: place, target_date: null } },
    { id: "heat", label: "Heatwave", icon: "local_fire_department", scenario: { overrides: { temp_c: 44, rain_mm_h: 0, wind_kmh: 15 }, target_place: "all", target_date: null } },
  ] as { id: string; label: string; icon: string; scenario: TwinScenario }[];
}

const SLIDERS: { key: keyof TwinOverrides; label: string; min: number; max: number; step: number; unit: string; live: number }[] = [
  { key: "rain_mm_h", label: "Rainfall intensity", min: 0, max: 100, step: 1, unit: "mm/h", live: 0 },
  { key: "storm_hours", label: "Storm duration", min: 0, max: 48, step: 1, unit: "h", live: 0 },
  { key: "temp_c", label: "Temperature", min: 15, max: 48, step: 1, unit: "°C", live: 29 },
  { key: "wind_kmh", label: "Wind speed", min: 0, max: 150, step: 5, unit: "km/h", live: 10 },
  { key: "flood_index", label: "Flooding", min: 0, max: 1, step: 0.05, unit: "", live: 0 },
];

interface Props {
  scenario: TwinScenario;
  presetId: string;
  places: string[];
  days: string[];
  onChange: (scenario: TwinScenario, presetId: string) => void;
  running: boolean;
}

export default function ScenarioControls({ scenario, presetId, places, days, onChange, running }: Props) {
  const presets = buildPresets(places[0], days);
  const set = (key: keyof TwinOverrides, value: number | null) => onChange({ ...scenario, overrides: { ...scenario.overrides, [key]: value } }, "custom");

  return (
    <div className="card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[16px] font-semibold flex items-center gap-2"><Icon name="tune" className="text-sky" /> What-if simulator</h3>
        <span className={`inline-flex items-center gap-1 h-6 px-2.5 rounded-full text-[10px] font-semibold ${running ? "bg-icy text-sky-ink" : "bg-safe-bg text-safe-ink"}`}>
          {running ? <><motion.span className="h-1.5 w-1.5 rounded-full bg-sky" animate={{ opacity: [1, 0.2, 1] }} transition={{ repeat: Infinity, duration: 0.8 }} /> SIMULATING…</> : <><Icon name="lock" className="!text-[12px]" /> SANDBOX · REAL TRIP UNTOUCHED</>}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {presets.map((p) => (
          <motion.button
            key={p.id}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => onChange(p.scenario, p.id)}
            className={`flex flex-col items-center gap-1 rounded-xl border px-2 py-2.5 text-[11px] font-medium transition ${
              presetId === p.id ? "border-sky bg-icy text-sky-ink shadow-l1" : "border-line bg-well text-ink-2 hover:border-line-2 hover:text-ink"
            }`}
          >
            <Icon name={p.icon} fill={presetId === p.id} className="!text-[22px]" />
            {p.label}
          </motion.button>
        ))}
      </div>

      <div className="space-y-3.5">
        {SLIDERS.map((s) => {
          const value = scenario.overrides[s.key];
          const active = value !== undefined && value !== null;
          const shown = active ? (value as number) : s.live;
          return (
            <div key={s.key}>
              <div className="flex justify-between text-[12px] mb-1">
                <span className={active ? "text-ink font-medium" : "text-ink-2"}>{s.label}</span>
                <span className="tnum text-ink-2">
                  {active ? <b className="text-sky-ink">{s.key === "flood_index" ? `${Math.round(shown * 100)}%` : `${shown} ${s.unit}`}</b> : "live"}
                  {active && <button onClick={() => set(s.key, null)} className="ml-2 text-ink-3 hover:text-sky" title="Back to live value">↺</button>}
                </span>
              </div>
              <input type="range" min={s.min} max={s.max} step={s.step} value={shown} onChange={(e) => set(s.key, Number(e.target.value))} className={`w-full ${active ? "" : "opacity-50"}`} />
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label>
          <span className="label">Where</span>
          <select className="input" value={scenario.target_place} onChange={(e) => onChange({ ...scenario, target_place: e.target.value }, "custom")}>
            <option value="all">Everywhere</option>
            {places.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label>
          <span className="label">When</span>
          <select className="input" value={scenario.target_date ?? ""} onChange={(e) => onChange({ ...scenario, target_date: e.target.value || null }, "custom")}>
            <option value="">Whole trip</option>
            {days.map((d) => <option key={d} value={d}>{new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</option>)}
          </select>
        </label>
      </div>
    </div>
  );
}
