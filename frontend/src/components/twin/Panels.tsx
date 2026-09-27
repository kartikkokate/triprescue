import { AnimatePresence, motion } from "framer-motion";
import type { EffectLink, Interval, TwinNode, TwinTrip } from "../../types";
import { Icon, TYPE_ICON, inr } from "../../ui";
import { DRIVER_LABEL, METRIC_LABEL, fmtMetric, pct, riskColor } from "./format";

// --- trip-level gauge ----------------------------------------------------------------

export function TripGauge({ trip, baseline }: { trip: TwinTrip; baseline?: TwinTrip }) {
  const r = 40;
  const c = 2 * Math.PI * r;
  const p = trip.p_any_disruption;
  const delta = baseline ? p - baseline.p_any_disruption : 0;
  return (
    <div className="card p-5 flex items-center gap-5">
      <div className="relative h-28 w-28 shrink-0">
        <svg viewBox="0 0 100 100" className="-rotate-90 h-full w-full">
          <circle cx="50" cy="50" r={r} stroke="#E8F5FD" strokeWidth="10" fill="none" />
          <motion.circle cx="50" cy="50" r={r} stroke={riskColor(p)} strokeWidth="10" fill="none" strokeLinecap="round" strokeDasharray={c} initial={false} animate={{ strokeDashoffset: c * (1 - p) }} transition={{ type: "spring", stiffness: 60, damping: 16 }} />
        </svg>
        <motion.p key={Math.round(p * 100)} initial={{ scale: 1.15, opacity: 0.4 }} animate={{ scale: 1, opacity: 1 }} className="absolute inset-0 grid place-items-center text-[26px] font-bold tnum" style={{ color: riskColor(p) }}>
          {pct(p)}
        </motion.p>
      </div>
      <div className="space-y-1.5">
        <p className="eyebrow">Chance any booking breaks</p>
        {baseline && Math.abs(delta) >= 0.01 ? (
          <p className={`text-[13px] font-semibold ${delta > 0 ? "text-broken" : "text-safe"}`}>{delta > 0 ? "▲" : "▼"} {pct(Math.abs(delta))} vs live forecast</p>
        ) : (
          <p className="text-[13px] text-ink-2">{baseline ? "Same as live forecast" : "Under the live forecast"}</p>
        )}
        <div className="flex gap-4 text-[12px] tnum">
          <span><span className="text-ink-2">Expected loss</span><br /><b>{inr(trip.expected_loss_inr)}</b></span>
          <span><span className="text-ink-2">Expected extra delay</span><br /><b>+{Math.round(trip.expected_extra_minutes)} min</b></span>
        </div>
      </div>
    </div>
  );
}

// --- per-booking probabilities -----------------------------------------------------

export function BookingRisks({ nodes, delta, selectedId, onSelect }: { nodes: TwinNode[]; delta?: Record<string, number>; selectedId: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="text-[16px] font-semibold flex items-center gap-2"><Icon name="stacked_bar_chart" className="text-sky" /> Bookings under this weather</h3>
        <div className="flex gap-3 text-[11px] text-ink-2">
          <Legend color="bg-safe" label="safe" />
          <Legend color="bg-risk" label="at risk" />
          <Legend color="bg-broken" label="broken" />
        </div>
      </div>
      <div className="space-y-1">
        {nodes.map((n, i) => {
          const d = delta?.[n.id] ?? 0;
          return (
            <motion.button
              key={n.id}
              layout
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03 }}
              onClick={() => onSelect(n.id)}
              className={`w-full text-left rounded-xl px-3 py-2.5 border transition ${selectedId === n.id ? "border-sky bg-icy/40" : "border-transparent hover:bg-canvas"}`}
            >
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="flex items-center gap-2 min-w-0 text-[13px]">
                  <Icon name={TYPE_ICON[n.type]} className="!text-[16px] text-sky-ink" />
                  <span className="truncate font-medium">{n.title}</span>
                </span>
                <span className="flex items-center gap-2 shrink-0 text-[11px]">
                  {n.top_driver && <span className="h-5 px-2 rounded-full bg-icy text-sky-ink font-semibold inline-flex items-center">{DRIVER_LABEL[n.top_driver]}</span>}
                  {Math.abs(d) >= 0.02 && <span className={`font-semibold tnum ${d > 0 ? "text-broken" : "text-safe"}`}>{d > 0 ? "+" : "−"}{pct(Math.abs(d))}</span>}
                </span>
              </div>
              <div className="flex h-2 rounded-full overflow-hidden bg-canvas-3">
                <motion.div className="bg-safe" animate={{ width: pct(n.p_safe) }} transition={{ duration: 0.6 }} />
                <motion.div className="bg-risk" animate={{ width: pct(n.p_at_risk) }} transition={{ duration: 0.6 }} />
                <motion.div className="bg-broken" animate={{ width: pct(n.p_broken) }} transition={{ duration: 0.6 }} />
              </div>
              <p className="text-[11px] text-ink-3 mt-1 tnum">
                delay p10–p90: {n.delay_p10.toFixed(0)}–{n.delay_p90.toFixed(0)} min{n.p_cancelled >= 0.05 && ` · ${pct(n.p_cancelled)} cancelled`}
              </p>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return <span className="flex items-center gap-1"><span className={`inline-block w-2 h-2 rounded-full ${color}`} />{label}</span>;
}

// --- ecosystem ---------------------------------------------------------------------

export function Ecosystem({ ecosystem }: { ecosystem: Record<string, Record<string, Interval>> }) {
  return (
    <div className="card p-5 space-y-3">
      <div>
        <h3 className="text-[16px] font-semibold flex items-center gap-2"><Icon name="apartment" className="text-sky" /> Hospitality ecosystem</h3>
        <p className="text-[11px] text-ink-2 mt-0.5">Mean with 80% interval across simulated futures</p>
      </div>
      {Object.entries(ecosystem).map(([place, metrics]) => (
        <div key={place} className="space-y-2">
          <p className="text-[12px] font-semibold text-sky-ink flex items-center gap-1"><Icon name="location_on" className="!text-[15px]" />{place}</p>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(metrics).map(([key, v]) => {
              const meta = METRIC_LABEL[key];
              if (!meta) return null;
              const scaleMax = meta.kind === "ratio" ? 1 : 3.5;
              const norm = (x: number) => Math.min(1, x / scaleMax);
              const good = meta.goodHigh ? v.mean >= 0.85 : meta.kind === "ratio" ? v.mean <= 0.75 : v.mean <= 1.15;
              return (
                <div key={key} className="rounded-xl bg-canvas border border-line p-2.5">
                  <p className="text-[10px] text-ink-2">{meta.label}</p>
                  <p className={`text-[15px] font-semibold tnum ${good ? "text-ink" : "text-risk-ink"}`}>{fmtMetric(v.mean, meta.kind)}</p>
                  <div className="relative h-1.5 bg-canvas-3 rounded-full mt-1">
                    <motion.div className="absolute h-full rounded-full bg-sky-light/50" animate={{ left: pct(norm(v.p10)), width: pct(Math.max(0.01, norm(v.p90) - norm(v.p10))) }} transition={{ duration: 0.6 }} />
                    <motion.div className="absolute -top-0.5 h-2.5 w-0.5 bg-sky-ink" animate={{ left: pct(norm(v.mean)) }} transition={{ duration: 0.6 }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// --- effect chain ------------------------------------------------------------------

const ORDER_STYLE = {
  0: { label: "Already disrupted · not weather", bar: "border-broken", text: "text-broken-ink" },
  1: { label: "1st order · weather → booking", bar: "border-sky", text: "text-sky-ink" },
  2: { label: "2nd order · booking → dependent booking", bar: "border-risk", text: "text-risk-ink" },
  3: { label: "3rd order · ecosystem → recovery options", bar: "border-pending", text: "text-pending-ink" },
};

export function EffectChain({ chain }: { chain: EffectLink[] }) {
  return (
    <div className="card p-5 space-y-3">
      <h3 className="text-[16px] font-semibold flex items-center gap-2"><Icon name="device_hub" className="text-sky" /> Cascade of effects</h3>
      {chain.filter((c) => c.order > 0).length === 0 && <p className="text-[13px] text-ink-2">No meaningful weather effects under these conditions.</p>}
      {([0, 1, 2, 3] as const).map((order) => {
        const links = chain.filter((c) => c.order === order);
        if (!links.length) return null;
        return (
          <div key={order} className="space-y-1.5">
            <p className={`text-[10px] font-semibold uppercase tracking-wide ${ORDER_STYLE[order].text}`}>{ORDER_STYLE[order].label}</p>
            <AnimatePresence initial={false}>
              {links.map((l, i) => (
                <motion.div key={`${l.from}-${l.to}-${l.effect}`} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ delay: i * 0.05 + order * 0.08 }} className={`border-l-2 pl-3 py-1 ${ORDER_STYLE[order].bar}`}>
                  <p className="text-[12px] text-ink">{l.effect}</p>
                  <p className="text-[10px] text-ink-3 tnum">{l.from} → {l.to} · p={pct(l.probability)}</p>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
