import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../api";
import { useApp } from "../context";
import type { BookingNode, Explanation, Itinerary, PlanAnalysis, RecoveryPlan, RiskWarning, TravelerPreferences, TwinState } from "../types";
import {
  Card, CardHeader, Chip, EmptyState, ErrorBanner, Icon, ModelBadge, Money, ProgressBar, Segmented, Skeleton, StatusPill,
  TYPE_ICON, dayShort, dayTime, hhmm, inr, mins, pct,
} from "../ui";

const PRESETS: Record<string, TravelerPreferences> = {
  Balanced: { cost_weight: 0.2, time_weight: 0.3, convenience_weight: 0.4, disruption_weight: 0.1, min_rating: 0, avoid_next_day: false },
  "Save money": { cost_weight: 0.7, time_weight: 0.1, convenience_weight: 0.1, disruption_weight: 0.1, min_rating: 0, avoid_next_day: false },
  "Save time": { cost_weight: 0.1, time_weight: 0.7, convenience_weight: 0.1, disruption_weight: 0.1, min_rating: 0, avoid_next_day: true },
  "Maximize comfort": { cost_weight: 0.05, time_weight: 0.15, convenience_weight: 0.7, disruption_weight: 0.1, min_rating: 70, avoid_next_day: false },
};

const ACTION: Record<string, { label: string; cls: string; icon: string }> = {
  keep: { label: "Keep", cls: "bg-safe-bg text-safe-ink", icon: "check" },
  reschedule: { label: "Reschedule", cls: "bg-icy text-sky-ink", icon: "event_repeat" },
  rebook: { label: "New booking", cls: "bg-canvas-3 text-ink", icon: "confirmation_number" },
  manual_booking: { label: "Book yourself", cls: "bg-pending-bg text-pending-ink", icon: "person" },
  drop: { label: "Drop", cls: "bg-dropped-bg text-dropped-ink", icon: "block" },
};

const EDGE_WORD: Record<string, string> = { transfer_required: "transfer", checkin_dependency: "check-in", same_day: "same day", sequential: "next" };
const SEG: Record<string, string> = { flight: "AIR", train: "RAIL", transfer: "ROAD", hotel: "STAY", activity: "ACTIVITY", event: "EVENT" };

export default function RecoveryConsole() {
  const app = useApp();
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [plans, setPlans] = useState<RecoveryPlan[]>([]);
  const [analysis, setAnalysis] = useState<PlanAnalysis | null>(null);
  const [planRisk, setPlanRisk] = useState<Record<string, { p_success: number; risks: string[] }>>({});
  const [warnings, setWarnings] = useState<RiskWarning[]>([]);
  const [twin, setTwin] = useState<TwinState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<RecoveryPlan | null>(null);

  const load = async () => {
    setError(null);
    try {
      const [it, rp, rs] = await Promise.all([api.getItinerary(), api.getRecoveryPlans(), api.riskScan()]);
      setItinerary(it);
      setPlans(rp.plans);
      setAnalysis(rp.analysis);
      setWarnings(rs.warnings);
      if (rp.plans.length) api.twinPlanRisk().then((r) => setPlanRisk(r.plans)).catch(() => setPlanRisk({}));
      api.twinState().then(setTwin).catch(() => setTwin(null));
    } catch (e: any) {
      setError(e.message);
    }
  };

  useEffect(() => {
    load();
  }, [app.itineraryVersion]);

  const nodes = useMemo(() => (itinerary ? [...itinerary.nodes].sort((a, b) => a.start.localeCompare(b.start)) : []), [itinerary]);
  const broken = nodes.filter((n) => n.status === "broken" || n.status === "cancelled");
  const atRisk = nodes.filter((n) => n.status === "at_risk");
  const origin = nodes.find((n) => n.id === app.lastDisruption.disruption?.node_id) ?? nodes.find((n) => n.status === "cancelled") ?? broken[0];
  const impact = app.lastDisruption.impact_report ?? {};
  const disrupted = broken.length > 0;

  const reset = async () => {
    await api.reset();
    app.setLastDisruption({ disruption: null, impact_report: null });
    setApplied(null);
    app.refreshTrip();
    app.bumpItinerary();
    app.toast("Disruptions undone: back to your trip as booked");
  };

  const headline = !itinerary
    ? ""
    : disrupted && origin
    ? origin.status === "cancelled"
      ? `${origin.title} cancelled: cascade breaks ${broken.length - 1} downstream booking${broken.length - 1 === 1 ? "" : "s"}`
      : `${origin.title} delayed${impact[origin.id]?.overrun_minutes ? ` (+${mins(impact[origin.id]!.overrun_minutes!)})` : ""}: ${broken.length} booking${broken.length === 1 ? "" : "s"} broken`
    : atRisk.length
    ? `${atRisk.length} booking${atRisk.length === 1 ? "" : "s"} at risk, nothing broken yet`
    : `All ${nodes.length} bookings on schedule`;

  return (
    <div className="space-y-6">
      {/* ---------- ops header ---------- */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold tracking-wide text-ink-2">
          <Chip tone={disrupted ? "broken" : atRisk.length ? "risk" : "safe"}>
            <span className={`h-1.5 w-1.5 rounded-full ${disrupted ? "bg-broken animate-pulse" : atRisk.length ? "bg-risk" : "bg-safe"}`} />
            {disrupted ? "DISRUPTION ACTIVE" : atRisk.length ? "WATCHING" : "NOMINAL"}
          </Chip>
          <span>/ DISRUPTION RECOVERY OPS / {app.tripName.toUpperCase()}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary h-9" onClick={() => app.go("twin")}><Icon name="radar" className="!text-[18px]" /> Simulate what-if</button>
          <button className="btn-secondary h-9" onClick={app.openTrips}><Icon name="folder_open" className="!text-[18px]" /> Trips…</button>
          <button className="btn-secondary h-9" onClick={reset}><Icon name="undo" className="!text-[18px]" /> Undo disruptions</button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-end">
        <div className="lg:col-span-8">
          {disrupted && (
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wider bg-broken text-white px-2 py-0.5 rounded">Severed link</span>
              <span className="text-[11px] font-semibold text-broken uppercase tracking-wide">Cascade propagation detected</span>
            </div>
          )}
          {itinerary ? (
            <motion.h1 key={headline} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="text-[26px] leading-[34px] md:text-[32px] md:leading-[40px] font-bold tracking-[-0.02em]">
              {headline}
            </motion.h1>
          ) : (
            <Skeleton className="h-10 w-3/4" />
          )}
          <p className="text-[13px] text-ink-2 mt-2 flex items-center gap-1.5">
            <Icon name="cloud_sync" className="!text-[16px] text-sky" /> Live checks every 20 min · deterministic recovery engine · all options strictly non-transacting advisory
          </p>
          {disrupted && origin && (
            <div className="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-[12px]">
              <span><span className="inline-block h-1.5 w-1.5 rounded-full bg-broken mr-1.5" />Disruption root: <b>{origin.title}</b>{app.lastDisruption.disruption?.reason ? ` (${String(app.lastDisruption.disruption.reason).replace(/_/g, " ")})` : ""}</span>
              {broken.filter((n) => n.id !== origin.id)[0] && (
                <span><span className="inline-block h-1.5 w-1.5 rounded-full bg-risk mr-1.5" />Severed connection: <b>{broken.filter((n) => n.id !== origin.id).map((n) => n.title).join(" & ")}</b></span>
              )}
            </div>
          )}
        </div>
        <div className="lg:col-span-4 grid grid-cols-3 gap-2">
          <Kpi label="Broken" value={String(broken.length)} tone={broken.length ? "broken" : "ink"} />
          <Kpi label="At risk" value={String(atRisk.length)} tone={atRisk.length ? "risk" : "ink"} />
          <Kpi label="Trip risk" value={twin ? pct(twin.trip.p_any_disruption) : "…"} tone={twin && twin.trip.p_any_disruption >= 0.5 ? "broken" : "ink"} dot />
        </div>
      </div>

      <div className="flex items-center justify-between rounded-xl bg-white/70 border border-line px-4 py-2 text-[12px] text-ink-2">
        <span className="flex items-center gap-1.5"><Icon name="info" className="!text-[16px]" /> Advisory policy: TripRescue does NOT charge, book or process tickets. Every step below is something you do with the provider.</span>
        {warnings.length > 0 && <span className="hidden md:flex items-center gap-1 text-risk-ink font-medium"><Icon name="warning" className="!text-[16px]" />{warnings.length} tight connection{warnings.length > 1 ? "s" : ""}</span>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* ================= LEFT ================= */}
        <div className="lg:col-span-8 space-y-5 min-w-0">
          <CascadeChain nodes={nodes} itinerary={itinerary} impact={impact} warnings={warnings} />
          <DisruptionControls nodes={nodes} onDone={(d) => { app.setLastDisruption(d); setApplied(null); app.bumpItinerary(); }} />
          <PlansSection
            plans={plans}
            analysis={analysis}
            planRisk={planRisk}
            nodes={nodes}
            disrupted={disrupted}
            onApplied={(p) => { setApplied(p); app.setLastDisruption({ disruption: null, impact_report: null }); app.bumpItinerary(); }}
          />
        </div>

        {/* ================= RIGHT ================= */}
        <div className="lg:col-span-4 space-y-5">
          <RiskTelemetry twin={twin} />
          <AdvisorCard disrupted={disrupted} hasPlans={plans.length > 0} disruptedType={(nodes.find((n) => n.id === app.lastDisruption.disruption?.node_id) ?? broken[0])?.type} />
          <CascadeAudit nodes={nodes} impact={impact} />
          <ExecutionList plan={applied ?? plans[0] ?? null} applied={!!applied} />
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, tone, dot }: { label: string; value: string; tone: "broken" | "risk" | "ink"; dot?: boolean }) {
  const color = { broken: "text-broken", risk: "text-risk", ink: "text-ink" }[tone];
  return (
    <div className="card px-3 py-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.05em] text-ink-2">{label}</p>
      <p className={`text-xl font-bold tnum ${color} flex items-center gap-1`}>{dot && tone === "broken" && <span className="h-2 w-2 rounded-full bg-broken" />}{value}</p>
    </div>
  );
}

/* ---------------------------------------------------------------- cascade chain */

function CascadeChain({ nodes, itinerary, impact, warnings }: { nodes: BookingNode[]; itinerary: Itinerary | null; impact: Record<string, any>; warnings: RiskWarning[] }) {
  const edgeInto = (id: string) => itinerary?.edges.find((e) => e.target === id);
  const breakEdge = itinerary?.edges.find((e) => {
    const t = nodes.find((n) => n.id === e.target);
    const s = nodes.find((n) => n.id === e.source);
    return t && s && (t.status === "broken" || t.status === "cancelled") && s.status !== "safe";
  });
  const breakSrc = nodes.find((n) => n.id === breakEdge?.source);
  const breakDst = nodes.find((n) => n.id === breakEdge?.target);
  const srcDelay = breakSrc ? impact[breakSrc.id]?.overrun_minutes : null;

  return (
    <Card className="p-5">
      <CardHeader
        icon="hub"
        title="Itinerary cascade chain & disruption map"
        sub="Each booking and the buffer it needs from the one before"
        right={
          <div className="hidden sm:flex gap-1.5">
            <StatusPill status="safe" label="Preserved" />
            <StatusPill status="at_risk" label="At risk" />
            <StatusPill status="broken" label="Severed" />
          </div>
        }
      />
      {breakEdge && breakSrc && breakDst && (
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between gap-3 rounded-xl bg-broken-bg border border-red-200 px-4 py-2.5 mb-4 text-[13px] text-broken-ink">
          <span className="flex items-center gap-2">
            <Icon name="link_off" className="!text-[18px]" />
            <span>
              <b>Break point identified:</b>{" "}
              {breakSrc.status === "cancelled"
                ? `${breakSrc.title} is cancelled, so ${breakDst.title} can't happen as booked.`
                : `${srcDelay ? `a ${mins(srcDelay)} delay on ` : ""}${breakSrc.title} eats the ${breakEdge.buffer_minutes} min ${EDGE_WORD[breakEdge.type] ?? ""} window before ${breakDst.title}.`}
            </span>
          </span>
          {srcDelay && srcDelay > breakEdge.buffer_minutes && <span className="tnum font-bold shrink-0">−{srcDelay - breakEdge.buffer_minutes}m</span>}
        </motion.div>
      )}
      {!itinerary ? (
        <div className="flex gap-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-36 w-48 shrink-0" />)}</div>
      ) : nodes.length === 0 ? (
        <EmptyState icon="luggage" title="No bookings" body="Build your trip in the Trip Builder." />
      ) : (
        <div className="overflow-x-auto -mx-1 px-1 pb-2">
          <div className="flex items-stretch min-w-max">
            {nodes.map((n, i) => {
              const inEdge = edgeInto(n.id);
              const warn = warnings.find((w) => w.node_id === n.id);
              const hit = n.status === "broken" || n.status === "cancelled";
              // a connection is missed only when the booking feeding it is itself late/cancelled -
              // a delay that starts at this booking breaks the booking, not the link into it
              const feeder = inEdge ? nodes.find((x) => x.id === inEdge.source) : undefined;
              const missed = hit && !!feeder && feeder.status !== "safe";
              const ov = impact[n.id]?.overrun_minutes;
              const pending = n.booking_status === "pending_manual_booking";
              // route: "A to B" in the location, else "A -> B" / "A → B" in the title (flights)
              const m = n.title.match(/([A-Z]{3})\s*(?:->|→)\s*([A-Z]{3})/);
              const [from, to] = n.location.includes(" to ") ? n.location.split(" to ") : m ? [m[1], m[2]] : [n.location, ""];
              return (
                <div key={n.id} className="flex items-stretch">
                  {i > 0 && (
                    <div className="w-24 flex flex-col items-center justify-center text-center px-1">
                      <span className={`text-[10px] font-semibold uppercase tracking-wide ${missed ? "text-broken" : warn ? "text-risk-ink" : "text-ink-3"}`}>
                        {missed ? "missed" : inEdge ? EDGE_WORD[inEdge.type] : ""}
                      </span>
                      <div className="relative w-full my-1">
                        <div className={`h-0.5 w-full ${missed ? "bg-broken" : n.status === "at_risk" ? "bg-risk" : "bg-line-2"} ${missed ? "" : "opacity-80"}`} style={missed ? { backgroundImage: "repeating-linear-gradient(90deg,#EF4444 0 6px,transparent 6px 10px)", backgroundColor: "transparent" } : undefined} />
                        <Icon name={missed ? "close" : "chevron_right"} className={`!text-[16px] absolute left-1/2 -translate-x-1/2 -top-2 bg-white rounded-full ${missed ? "text-broken" : "text-ink-3"}`} />
                      </div>
                      <span className="text-[10px] text-ink-2 tnum">{inEdge ? `${inEdge.buffer_minutes}m buffer` : ""}</span>
                    </div>
                  )}
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className={`w-52 rounded-xl border p-3 flex flex-col gap-1.5 ${
                      pending ? "border-dashed border-pending bg-pending-bg/40" : hit ? "border-red-200 bg-broken-bg/40" : n.status === "at_risk" ? "border-amber-200 bg-risk-bg/40" : "border-line bg-well"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-[10px] font-semibold text-ink-2 tracking-wide">SEG-{String(i + 1).padStart(2, "0")} · {SEG[n.type]}</span>
                      <StatusPill status={pending ? "pending_manual_booking" : n.status} label={pending ? "Book yourself" : ov && n.status !== "cancelled" ? `+${mins(ov)}` : undefined} />
                    </div>
                    <div className="flex items-center gap-1.5 min-h-[28px]">
                      <Icon name={TYPE_ICON[n.type]} className="!text-[18px] text-sky-ink" />
                      <p className={`text-[14px] font-semibold leading-tight ${n.status === "cancelled" ? "line-through decoration-2 decoration-cancel" : ""}`}>
                        {to ? <>{from.trim()} <Icon name="east" className="!text-[13px]" /> {to.trim()}</> : n.location || n.title}
                      </p>
                    </div>
                    <p className="text-[12px] text-ink-2 line-clamp-2">{n.title}</p>
                    <p className="text-[11px] text-ink-2 tnum mt-auto">
                      {dayShort(n.start)} · {hhmm(n.start)}
                      {ov && impact[n.id]?.new_start ? <span className="text-broken font-semibold"> → {hhmm(impact[n.id].new_start)}</span> : null}
                    </p>
                    <p className="text-[11px] text-ink-3">{n.provider} · {inr(n.cost)}</p>
                  </motion.div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
}

/* ---------------------------------------------------------------- disruption controls */

function DisruptionControls({ nodes, onDone }: { nodes: BookingNode[]; onDone: (d: { disruption: any; impact_report: any }) => void }) {
  const app = useApp();
  const [tab, setTab] = useState<"booking" | "weather" | "prefs">("booking");
  const [nodeId, setNodeId] = useState("");
  const [kind, setKind] = useState<"delay" | "cancel">("delay");
  const [delay, setDelay] = useState(180);
  const [reason, setReason] = useState("operator_cancellation");
  const [flightCode, setFlightCode] = useState("");
  const [flightResult, setFlightResult] = useState<string | null>(null);
  const days = Array.from(new Set(nodes.map((n) => n.start.slice(0, 10))));
  const [day, setDay] = useState("");
  const [severity, setSeverity] = useState<"moderate" | "severe">("severe");
  const [forecast, setForecast] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [prefs, setPrefs] = useState<TravelerPreferences | null>(null);

  // A booking the traveler already disrupted (e.g. from the cascade simulator) is not asked for
  // again: show it as the active disruption, open on Weather (what else could hit the trip),
  // and default "another booking" to one that is still on schedule.
  const lastDisrupted = app.lastDisruption.disruption;
  const active = nodes.find((n) => n.id === lastDisrupted?.node_id);
  const hit = new Set(nodes.filter((n) => n.status === "broken" || n.status === "cancelled").map((n) => n.id));
  if (active) hit.add(active.id);
  useEffect(() => {
    if (active) {
      setTab("weather");
      setDay(active.start.slice(0, 10));
      setNodeId(nodes.find((n) => !hit.has(n.id))?.id ?? active.id);
    } else {
      if (!nodes.find((n) => n.id === nodeId)) setNodeId(nodes[0]?.id ?? "");
      if (!days.includes(day)) setDay(days[0] ?? "");
    }
  }, [nodes, lastDisrupted?.node_id, lastDisrupted?.kind]);
  useEffect(() => {
    const n = nodes.find((x) => x.id === nodeId);
    setFlightCode(n?.service_code ?? "");
    setFlightResult(null);
  }, [nodeId]);
  useEffect(() => {
    if (tab === "prefs" && !prefs) api.getPreferences().then(setPrefs).catch(() => {});
  }, [tab]);

  const node = nodes.find((n) => n.id === nodeId);
  const wrap = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try {
      await fn();
    } catch (e: any) {
      app.toast(e.message, "error");
    } finally {
      setBusy(null);
    }
  };

  const trigger = () => wrap("trigger", async () => {
    const res = await api.disrupt(nodeId, kind, kind === "delay" ? delay : 0, kind === "cancel" ? reason : "delay");
    onDone({ disruption: res.disruption, impact_report: res.impact_report });
    app.toast(`${node?.title}: ${kind === "cancel" ? "cancellation" : `+${mins(delay)} delay`} applied`, "warn");
  });

  const checkFlight = () => wrap("flight", async () => {
    const r = await api.checkFlightStatus(flightCode);
    if (!r.configured) setFlightResult("Live flight status not configured on the server.");
    else if (r.error) setFlightResult(r.error);
    else if (!r.found) setFlightResult(r.message ?? "No live data for this flight.");
    else {
      setFlightResult(`${r.flight_iata}: ${r.status}, ${r.delay_minutes ?? 0} min delay${r.suggested_action ? ` - suggests ${r.suggested_action}` : " - no disruption"}`);
      if (r.suggested_action === "delay" && r.delay_minutes) { setKind("delay"); setDelay(r.delay_minutes); }
      if (r.suggested_action === "cancel") setKind("cancel");
    }
  });

  // forecast location = where the trip is that day (destination for transport legs)
  const dayNode = nodes.find((n) => n.start.startsWith(day) && n.type !== "flight" && n.type !== "train") ?? nodes.find((n) => n.start.startsWith(day));
  const place = (dayNode?.location ?? "").split(" to ").pop()!.replace(/(Airport|Beach|Station|Railway)/gi, "").trim() || (dayNode?.location ?? "");
  const checkForecast = () => wrap("forecast", async () => {
    const r = await api.checkWeather(place, day);
    if (r.error) setForecast(r.error);
    else if (!r.found) setForecast(r.message ?? "No forecast for that day yet.");
    else {
      setForecast(`${r.provider ?? "Forecast"} for ${r.location} on ${r.date}: max ${r.max_rain_mm_h ?? 0} mm/h, wind ${r.max_wind_speed_ms} m/s${r.severity_suggestion ? ` - suggests "${r.severity_suggestion}"` : " - no weather event suggested"}`);
      if (r.severity_suggestion) setSeverity(r.severity_suggestion);
    }
  });

  const triggerWeather = () => wrap("weather", async () => {
    const res = await api.disruptWeather(day, severity);
    onDone({ disruption: res.disruption, impact_report: res.impact_report });
    app.toast(`${severity} weather applied to ${dayShort(day)}`, "warn");
  });

  const savePrefs = (p: TravelerPreferences) => wrap("prefs", async () => {
    const saved = await api.setPreferences(p);
    setPrefs(saved);
    app.bumpItinerary();
    app.toast("Preferences saved - plans re-ranked", "success");
  });

  const wsum = prefs ? prefs.cost_weight + prefs.time_weight + prefs.convenience_weight + prefs.disruption_weight || 1 : 1;

  return (
    <Card className="p-5" delay={0.05}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h3 className="text-[16px] font-semibold flex items-center gap-2"><Icon name="bolt" className="text-sky" /> Disruption controls</h3>
        <Segmented value={tab} onChange={setTab} size="sm" options={[{ value: "booking", label: active ? "Another booking" : "Booking" }, { value: "weather", label: "Weather" }, { value: "prefs", label: "Preferences" }]} />
      </div>

      {active && (
        <div className="mb-4 rounded-xl border border-red-200 bg-broken-bg px-3.5 py-2.5 text-[13px] text-broken-ink flex flex-wrap items-center gap-x-2 gap-y-1">
          <Icon name="error" className="!text-[18px]" />
          <span>
            Active: <b>{active.title}</b>{" "}
            {lastDisrupted?.kind === "cancel" ? "cancelled" : `+${mins(Number(lastDisrupted?.delay_minutes) || 0)} late`}
            {/simulation/i.test(String(lastDisrupted?.reason ?? "")) ? " (from the cascade simulator)" : ""}. The plans below recover it.
          </span>
          <span className="text-ink-2 w-full sm:w-auto sm:ml-auto text-[12px]">Check weather on top of it, or disrupt another booking.</span>
        </div>
      )}

      <motion.div key={tab} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.18 }}>
          {tab === "booking" && (
            <div className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
                <label className="sm:col-span-5"><span className="label">Booking</span>
                  <select className="input" value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
                    {nodes.map((n) => <option key={n.id} value={n.id}>{n.title}{hit.has(n.id) ? " (already disrupted)" : ""}</option>)}
                  </select>
                </label>
                <div className="sm:col-span-3"><span className="label">Type</span>
                  <Segmented value={kind} onChange={setKind} size="sm" options={[{ value: "delay", label: "Delay" }, { value: "cancel", label: "Cancel" }]} />
                </div>
                <label className="sm:col-span-4">
                  <span className="label">{kind === "delay" ? "Delay (minutes)" : "Reason"}</span>
                  {kind === "delay" ? (
                    <input className="input tnum" type="number" min={0} step={15} value={delay} onChange={(e) => setDelay(Number(e.target.value))} />
                  ) : (
                    <select className="input" value={reason} onChange={(e) => setReason(e.target.value)}>
                      <option value="operator_cancellation">Operator cancellation</option>
                      <option value="weather">Weather</option>
                      <option value="traveler_request">Traveler request</option>
                      <option value="overbooked">Overbooked</option>
                    </select>
                  )}
                </label>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button className="btn bg-broken text-white hover:bg-red-600" disabled={!nodeId || busy !== null} onClick={trigger}>
                  <Icon name="report" className="!text-[18px]" /> {busy === "trigger" ? "Applying…" : "Trigger disruption"}
                </button>
                {node?.type === "flight" && (
                  <>
                    <input className="input w-28 h-10" value={flightCode} placeholder="Flight no." onChange={(e) => setFlightCode(e.target.value.toUpperCase())} />
                    <button className="btn-secondary" disabled={!flightCode || busy !== null} onClick={checkFlight}>
                      <Icon name="flight" className="!text-[18px]" /> {busy === "flight" ? "Checking…" : "Check real flight status"}
                    </button>
                  </>
                )}
              </div>
              {flightResult && <p className="text-[12px] text-ink-2 bg-canvas rounded-lg px-3 py-2 border border-line">{flightResult}</p>}
            </div>
          )}

          {tab === "weather" && (
            <div className="space-y-3">
              <p className="text-[12px] text-ink-2">Hits every weather-sensitive booking that day at once: outdoor activities and same-day transfers.</p>
              <div className="flex flex-wrap items-end gap-3">
                <label><span className="label">Day</span>
                  <select className="input w-40" value={day} onChange={(e) => { setDay(e.target.value); setForecast(null); }}>
                    {days.map((d) => <option key={d} value={d}>{dayShort(d)}</option>)}
                  </select>
                </label>
                <div><span className="label">Severity</span>
                  <Segmented value={severity} onChange={setSeverity} size="sm" options={[{ value: "moderate", label: "Moderate" }, { value: "severe", label: "Severe" }]} />
                </div>
                <button className="btn-secondary" disabled={!day || busy !== null} onClick={checkForecast}><Icon name="wb_sunny" className="!text-[18px]" /> {busy === "forecast" ? "Checking…" : "Check real forecast"}</button>
                <button className="btn-solid" disabled={!day || busy !== null} onClick={triggerWeather}><Icon name="thunderstorm" className="!text-[18px]" /> {busy === "weather" ? "Applying…" : "Trigger weather event"}</button>
              </div>
              {forecast && <p className="text-[12px] text-ink-2 bg-canvas rounded-lg px-3 py-2 border border-line">{forecast}</p>}
            </div>
          )}

          {tab === "prefs" && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {Object.keys(PRESETS).map((name) => (
                  <button key={name} className="btn-secondary h-8 text-[12px]" disabled={busy !== null} onClick={() => savePrefs(PRESETS[name])}>{name}</button>
                ))}
              </div>
              {prefs ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
                  {([["cost_weight", "Cost"], ["time_weight", "Time"], ["convenience_weight", "Convenience"], ["disruption_weight", "Minimize disruption"]] as const).map(([k, label]) => (
                    <label key={k} className="block">
                      <span className="flex justify-between text-[12px]"><span className="text-ink-2">{label}</span><span className="font-semibold tnum">{Math.round((prefs[k] / wsum) * 100)}%</span></span>
                      <input type="range" min={0} max={100} value={Math.round(prefs[k] * 100)} onChange={(e) => setPrefs({ ...prefs, [k]: Number(e.target.value) / 100 })} className="w-full" />
                    </label>
                  ))}
                  <label className="block">
                    <span className="flex justify-between text-[12px]"><span className="text-ink-2">Minimum acceptable rating</span><span className="font-semibold tnum">{prefs.min_rating}</span></span>
                    <input type="range" min={0} max={100} value={prefs.min_rating} onChange={(e) => setPrefs({ ...prefs, min_rating: Number(e.target.value) })} className="w-full" />
                  </label>
                  <label className="flex items-center gap-2 text-[13px] pt-4">
                    <input type="checkbox" className="h-[18px] w-[18px] accent-[#228BE6]" checked={prefs.avoid_next_day} onChange={(e) => setPrefs({ ...prefs, avoid_next_day: e.target.checked })} />
                    Avoid pushing anything to the next day
                  </label>
                  <div className="sm:col-span-2"><button className="btn-solid" disabled={busy !== null} onClick={() => savePrefs(prefs)}><Icon name="tune" className="!text-[18px]" /> Save preferences</button></div>
                </div>
              ) : (
                <Skeleton className="h-24" />
              )}
            </div>
          )}
      </motion.div>
    </Card>
  );
}

/* ---------------------------------------------------------------- plans */

function PlansSection({ plans, analysis, planRisk, nodes, disrupted, onApplied }: {
  plans: RecoveryPlan[]; analysis: PlanAnalysis | null; planRisk: Record<string, { p_success: number; risks: string[] }>;
  nodes: BookingNode[]; disrupted: boolean; onApplied: (p: RecoveryPlan) => void;
}) {
  const app = useApp();
  const [sort, setSort] = useState<"recommended" | "time" | "cost">("recommended");
  const [openId, setOpenId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showRejected, setShowRejected] = useState(false);

  const sorted = useMemo(() => {
    const p = [...plans];
    if (sort === "time") p.sort((a, b) => a.total_time_delta_minutes - b.total_time_delta_minutes || b.score - a.score);
    if (sort === "cost") p.sort((a, b) => a.total_cost_delta - b.total_cost_delta || b.score - a.score);
    return p;
  }, [plans, sort]);

  const apply = async (p: RecoveryPlan) => {
    setBusy(true);
    try {
      await api.applyPlan(p.id);
      app.toast(`"${p.label}" adopted. Book the items marked "Book yourself".`, "success");
      setConfirm(null);
      onApplied(p);
    } catch (e: any) {
      app.toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  if (!disrupted && plans.length === 0) {
    return (
      <Card className="p-5" delay={0.1}>
        <EmptyState icon="verified" title="No recovery needed" body="Trigger a disruption above, simulate one in the Trip Builder, or apply a weather what-if from the Digital Twin." />
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="h-12 min-w-12 px-2 rounded-xl bg-sky-ink text-white grid place-items-center text-center leading-none">
            <span><span className="text-lg font-bold tnum">{plans.length}</span><br /><span className="text-[8px] font-semibold tracking-wider">PLANS</span></span>
          </span>
          <div>
            <h2 className="h-section">Feasible recovery plans</h2>
            {analysis && (
              <p className="text-[12px] text-ink-2 tnum">
                {analysis.combinations_checked} combinations checked · {analysis.feasible} feasible · ranked by your preferences
              </p>
            )}
          </div>
        </div>
        <Segmented value={sort} onChange={setSort} size="sm" options={[{ value: "recommended", label: "Recommended first" }, { value: "time", label: "Lowest time loss" }, { value: "cost", label: "Minimal extra cost" }]} />
      </div>

      {analysis && analysis.infeasible_examples.length > 0 && (
        <div className="rounded-xl bg-white border border-line">
          <button className="w-full flex items-center justify-between px-4 py-2.5 text-[12px] font-semibold text-ink-2" onClick={() => setShowRejected((s) => !s)}>
            <span className="flex items-center gap-1.5"><Icon name="block" className="!text-[16px]" /> Why {analysis.combinations_checked - analysis.feasible} combinations were rejected</span>
            <Icon name="expand_more" className={`!text-[18px] transition-transform ${showRejected ? "rotate-180" : ""}`} />
          </button>
          <AnimatePresence>
            {showRejected && (
              <motion.ul initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden px-4 pb-3 space-y-1 text-[12px] text-ink-2">
                {analysis.infeasible_examples.map((r) => <li key={r} className="flex gap-1.5"><Icon name="close" className="!text-[14px] text-broken mt-0.5" />{r}</li>)}
              </motion.ul>
            )}
          </AnimatePresence>
        </div>
      )}

      {plans.length === 0 ? (
        <Card className="p-5"><EmptyState icon="sync_problem" title="No feasible plan" body="Every combination of options would make you miss another booking. Try relaxing your preferences." /></Card>
      ) : (
        <AnimatePresence>
          {sorted.map((p, i) => (
            <PlanCard
              key={p.id}
              plan={p}
              index={i}
              featured={i === 0}
              expanded={i === 0 || openId === p.id}
              onToggle={() => setOpenId(openId === p.id ? null : p.id)}
              risk={planRisk[p.id]}
              nodes={nodes}
              confirming={confirm === p.id}
              busy={busy}
              onChoose={() => setConfirm(p.id)}
              onCancel={() => setConfirm(null)}
              onConfirm={() => apply(p)}
            />
          ))}
        </AnimatePresence>
      )}
    </div>
  );
}

function PlanCard({ plan, index, featured, expanded, onToggle, risk, nodes, confirming, busy, onChoose, onCancel, onConfirm }: {
  plan: RecoveryPlan; index: number; featured: boolean; expanded: boolean; onToggle: () => void; risk?: { p_success: number; risks: string[] };
  nodes: BookingNode[]; confirming: boolean; busy: boolean; onChoose: () => void; onCancel: () => void; onConfirm: () => void;
}) {
  const [why, setWhy] = useState(false);
  const title = (id: string) => nodes.find((n) => n.id === id)?.title ?? id;
  const extra = plan.badges.filter((b) => b !== plan.category);
  const headline = plan.options
    .filter((o) => o.action !== "keep")
    .map((o) => o.replacement_title.replace(/\s*\(.*?\)\s*$/, ""))
    .join(" + ") || "Keep everything, just later";

  return (
    <motion.div layout initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.06 }} className={`card overflow-hidden ${featured ? "border-sky shadow-l2 ring-1 ring-sky/20" : "card-hover"}`}>
      {featured && <div className="h-1 bg-gradient-to-r from-sky-deep to-sky-light" />}
      <div className="p-5 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1.5">
              <span className={`inline-flex items-center gap-1 h-6 px-2.5 rounded-md text-[11px] font-bold tracking-wide ${featured ? "bg-sky-ink text-white" : "bg-canvas-3 text-ink"}`}>
                {featured && <Icon name="star" fill className="!text-[14px]" />} {plan.label.toUpperCase()}{extra.length ? ` · ALSO ${extra.join(" + ").toUpperCase()}` : ""}
              </span>
              {risk && <Chip tone={risk.p_success >= 0.8 ? "safe" : risk.p_success >= 0.5 ? "risk" : "broken"}><Icon name="radar" className="!text-[13px]" /> {pct(risk.p_success)} holds under forecast</Chip>}
            </div>
            <h3 className={`${featured ? "text-[22px] leading-7" : "text-[18px] leading-6"} font-semibold tracking-[-0.01em]`}>{headline}</h3>
            <p className="text-[12px] text-ink-2 mt-1">
              Score <b className="text-ink tnum">{plan.score}</b>/100 · convenience {Math.round(plan.convenience_score)}/100 · changes {Math.round(plan.pct_itinerary_affected)}% of the trip
            </p>
          </div>
          <div className="text-right">
            <Money value={plan.total_cost_delta} className="text-[22px] font-bold" />
            <p className="text-[12px] text-ink-2">Net cash vs original</p>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-px rounded-xl overflow-hidden bg-line border border-line">
          <Metric label="Time impact" value={`+${mins(plan.total_time_delta_minutes)}`} sub="worst lateness" tone={plan.total_time_delta_minutes > 240 ? "broken" : "ink"} />
          <Metric label="New spend" value={inr(plan.money.new_spend)} sub={`${inr(plan.money.cash_refund)} cash refund`} />
          <Metric label="Penalties" value={inr(plan.money.penalty)} sub={plan.money.credit ? `${inr(plan.money.credit)} as credit` : "lost to fees"} tone={plan.money.penalty > 0 ? "risk" : "ink"} />
          <Metric label="Bookings touched" value={`${plan.options.filter((o) => o.action !== "keep").length} of ${plan.options.length}`} sub={`${plan.options.filter((o) => o.requires_manual_booking).length} to book yourself`} />
        </div>

        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden space-y-4">
              <div>
                <p className="eyebrow mb-2">Operational execution path</p>
                <div className="space-y-2">
                  {plan.options.map((o, i) => (
                    <div key={o.node_id} className="flex gap-3 rounded-xl border border-line bg-well p-3">
                      <span className="h-6 w-6 rounded-full bg-sky-ink text-white text-[11px] font-bold grid place-items-center shrink-0 tnum">{i + 1}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-[14px] font-semibold">
                            <span className={`inline-flex items-center gap-1 h-5 px-1.5 mr-1.5 rounded text-[10px] font-bold uppercase align-middle ${ACTION[o.action].cls}`}>
                              <Icon name={ACTION[o.action].icon} className="!text-[12px]" /> {ACTION[o.action].label}
                            </span>
                            {o.replacement_title}
                          </p>
                          <span className="text-[11px] font-semibold text-sky-ink tnum">{dayTime(o.start)} → {hhmm(o.end)}</span>
                        </div>
                        <p className="text-[12px] text-ink-2 mt-0.5">For <b>{title(o.node_id)}</b> · {o.provider} · {o.notes}</p>
                        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-[11px] tnum">
                          <span className="text-ink">Price {inr(o.cost)}</span>
                          {o.action !== "keep" && o.action !== "reschedule" && <span className={o.price_vs_original > 0 ? "text-broken" : "text-safe"}>{inr(o.price_vs_original, true)} vs what you paid</span>}
                          <span className="text-ink-3">source: {o.price_source}</span>
                          <span className="text-ink-3">market price: {o.market_price != null ? inr(o.market_price) : "unavailable"}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl border border-line p-3">
                  <p className="eyebrow mb-2">Money breakdown</p>
                  {[["Penalties", plan.money.penalty], ["Cash refund", -plan.money.cash_refund], ["Provider credit", -plan.money.credit], ["New spend", plan.money.new_spend]].map(([k, v]) => (
                    <div key={k as string} className="flex justify-between text-[13px] py-0.5"><span className="text-ink-2">{k}</span><Money value={v as number} /></div>
                  ))}
                  <div className="flex justify-between text-[13px] pt-1.5 mt-1.5 border-t border-line font-semibold"><span>Net cash</span><Money value={plan.money.net_cash} /></div>
                </div>
                <div className="rounded-xl border border-line p-3">
                  <button className="w-full flex items-center justify-between eyebrow mb-2" onClick={() => setWhy((w) => !w)}>
                    Why this score ({plan.score})
                    <Icon name="expand_more" className={`!text-[16px] transition-transform ${why ? "rotate-180" : ""}`} />
                  </button>
                  <div className="space-y-2">
                    {(["cost", "time", "convenience", "disruption"] as const).map((k) => {
                      const s = plan.score_breakdown[k];
                      return (
                        <div key={k}>
                          <div className="flex justify-between text-[12px]"><span className="capitalize text-ink-2">{k} <span className="text-ink-3">· weight {pct(s.weight)}</span></span><span className="font-semibold tnum">{s.contribution} pts</span></div>
                          <ProgressBar value={s.weight ? s.contribution / (s.weight * 100) : 0} />
                          {why && <p className="text-[10px] text-ink-3 tnum mt-0.5">{typeof s.value === "number" ? Math.round(s.value * 10) / 10 : s.value} {s.unit} → normalized {s.normalized}</p>}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
              {risk && risk.risks.length > 0 && (
                <div className="rounded-xl bg-risk-bg border border-amber-200 px-3 py-2 text-[12px] text-risk-ink">
                  <b>Digital twin:</b> {risk.risks.join(" · ")}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <p className="text-[11px] text-ink-3">*TripRescue never books or pays on your behalf. Advisory only.</p>
          <AnimatePresence initial={false}>
            {confirming ? (
              <motion.div key="c" initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} className="flex items-center gap-2">
                <span className="text-[12px] text-ink-2 max-w-[260px]">Updates your itinerary. You'll book the "Book yourself" items.</span>
                <button className="btn-secondary h-9" onClick={onCancel}>Cancel</button>
                <button className="btn-primary h-9" disabled={busy} onClick={onConfirm}>{busy ? "Adopting…" : "Confirm"}</button>
              </motion.div>
            ) : (
              <motion.div key="b" className="flex gap-2">
                {!featured && <button className="btn-secondary h-9" onClick={onToggle}>{expanded ? "Hide details" : "Compare details"}</button>}
                <button className={featured ? "btn-solid h-9" : "btn-secondary h-9"} onClick={onChoose}>
                  <Icon name="task_alt" className="!text-[18px]" /> {featured ? "Adopt advisory plan" : "Select advisory"}
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}

function Metric({ label, value, sub, tone = "ink" }: { label: string; value: string; sub: string; tone?: "ink" | "broken" | "risk" }) {
  return (
    <div className="bg-canvas p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.05em] text-ink-2">{label}</p>
      <p className={`text-[16px] font-semibold tnum ${{ ink: "text-ink", broken: "text-broken", risk: "text-risk-ink" }[tone]}`}>{value}</p>
      <p className="text-[11px] text-ink-3">{sub}</p>
    </div>
  );
}

/* ---------------------------------------------------------------- right rail */

function RiskTelemetry({ twin }: { twin: TwinState | null }) {
  const app = useApp();
  const p = twin?.trip.p_any_disruption ?? 0;
  const r = 44;
  const c = 2 * Math.PI * r;
  const tone = p >= 0.6 ? "#EF4444" : p >= 0.25 ? "#F59E0B" : "#10B981";
  const top = twin ? Object.values(twin.nodes).sort((a, b) => b.p_broken + b.p_at_risk - (a.p_broken + a.p_at_risk)).slice(0, 3) : [];
  return (
    <Card className="p-5">
      <CardHeader icon="speed" title="Telemetry risk analysis" right={<span className="text-[10px] font-semibold text-ink-3">{twin ? `LIVE TWIN · ${twin.samples} SIMS` : ""}</span>} />
      {!twin ? (
        <Skeleton className="h-40" />
      ) : (
        <>
          <div className="flex justify-center">
            <div className="relative h-32 w-32">
              <svg viewBox="0 0 100 100" className="-rotate-90 h-full w-full">
                <circle cx="50" cy="50" r={r} stroke="#E8F5FD" strokeWidth="9" fill="none" />
                <motion.circle cx="50" cy="50" r={r} stroke={tone} strokeWidth="9" fill="none" strokeLinecap="round" strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - p) }} transition={{ duration: 1, ease: "easeOut" }} />
              </svg>
              <div className="absolute inset-0 grid place-items-center text-center">
                <div>
                  <p className="text-[28px] font-bold tnum leading-none" style={{ color: tone }}>{Math.round(p * 100)}<span className="text-sm">%</span></p>
                  <p className="text-[9px] font-bold tracking-wider mt-1" style={{ color: tone }}>{p >= 0.6 ? "HIGH RISK" : p >= 0.25 ? "ELEVATED" : "LOW RISK"}</p>
                </div>
              </div>
            </div>
          </div>
          <p className="text-center text-[11px] text-ink-2 mt-1">Chance any booking breaks under the live forecast</p>
          <div className="space-y-2.5 mt-4">
            {top.map((n) => (
              <div key={n.id}>
                <div className="flex justify-between text-[11px]"><span className="text-ink-2 truncate">{n.title}</span><span className="font-semibold tnum">{pct(n.p_broken + n.p_at_risk)}</span></div>
                <ProgressBar value={n.p_broken + n.p_at_risk} tone={n.p_broken + n.p_at_risk >= 0.6 ? "broken" : n.p_broken + n.p_at_risk >= 0.25 ? "risk" : "safe"} />
              </div>
            ))}
          </div>
          <button className="btn-ghost w-full mt-3" onClick={() => app.go("twin")}>Open weather digital twin <Icon name="arrow_forward" className="!text-[16px]" /></button>
        </>
      )}
    </Card>
  );
}

// the rules that apply depend on what was disrupted, not on a fixed flight regulation
const RULEBOOK: Record<string, { tag: string; title: string }> = {
  flight: { tag: "DGCA REGULATORY SHIELD & AI ADVISOR", title: "DGCA CAR Section 3, Series M, Part IV" },
  train: { tag: "RAIL REFUND RULES & AI ADVISOR", title: "Indian Railways refund rules (TDR)" },
  hotel: { tag: "BOOKING TERMS & AI ADVISOR", title: "Hotel cancellation terms" },
  transfer: { tag: "BOOKING TERMS & AI ADVISOR", title: "Cab / transfer operator terms" },
  activity: { tag: "BOOKING TERMS & AI ADVISOR", title: "Activity cancellation terms" },
  event: { tag: "BOOKING TERMS & AI ADVISOR", title: "Event ticket terms" },
};

function AdvisorCard({ disrupted, hasPlans, disruptedType }: { disrupted: boolean; hasPlans: boolean; disruptedType?: string }) {
  const rules = (disruptedType && RULEBOOK[disruptedType]) || { tag: "TRAVELER RIGHTS & AI ADVISOR", title: "Your rights for this trip" };
  const [answers, setAnswers] = useState<Partial<Record<"impact" | "plans" | "rights", Explanation>>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const app = useApp();
  useEffect(() => setAnswers({}), [app.itineraryVersion]);

  const ask = async (k: "impact" | "plans" | "rights") => {
    setLoading(k);
    setErr(null);
    try {
      const fn = { impact: api.explainImpact, plans: api.explainPlans, rights: api.travelerRights }[k];
      const res = await fn();
      setAnswers((a) => ({ ...a, [k]: res }));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(null);
    }
  };

  return (
    <Card className="p-5" delay={0.05}>
      <p className="text-[11px] font-semibold text-sky-ink tracking-wide flex items-center gap-1.5 mb-1"><Icon name="gavel" className="!text-[16px]" /> {rules.tag}</p>
      <h3 className="text-[17px] font-semibold">{rules.title}</h3>
      <p className="text-[12px] text-ink-2 mt-1 mb-3">Ask the domain-aligned advisor what happened, which plan fits, and what refunds or compensation you are owed.</p>
      <div className="grid grid-cols-1 gap-2">
        {([["rights", "Know your rights", "shield", disrupted], ["impact", "Explain what happened", "psychology", disrupted], ["plans", "Explain recovery plans", "alt_route", hasPlans]] as const).map(([k, label, icon, enabled]) => (
          <button key={k} className="btn-secondary justify-start" disabled={!enabled || loading !== null} onClick={() => ask(k)}>
            <Icon name={icon} className="!text-[18px] text-sky" /> {loading === k ? "Thinking…" : label}
          </button>
        ))}
      </div>
      {!disrupted && <p className="text-[11px] text-ink-3 mt-2">Available once a booking is disrupted.</p>}
      {err && <p className="text-[12px] text-broken mt-2">{err}</p>}
      <AnimatePresence>
        {(["rights", "impact", "plans"] as const).filter((k) => answers[k]).map((k) => (
          <motion.div key={k} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-3 rounded-xl bg-canvas border border-line p-3 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <p className="eyebrow">{{ rights: "Your rights & next steps", impact: "What happened", plans: "Recommendation" }[k]}</p>
              <ModelBadge model={answers[k]!.model} />
            </div>
            <p className="text-[13px] leading-5 text-ink">{answers[k]!.explanation}</p>
          </motion.div>
        ))}
      </AnimatePresence>
    </Card>
  );
}

function CascadeAudit({ nodes, impact }: { nodes: BookingNode[]; impact: Record<string, any> }) {
  const hit = nodes.filter((n) => n.status !== "safe" || n.booking_status === "pending_manual_booking");
  return (
    <Card className="p-5" delay={0.1}>
      <CardHeader icon="account_tree" title="Downstream cascade audit" right={<span className="text-[11px] text-ink-2 tnum">{hit.length} affected</span>} />
      <div className="space-y-2">
        {nodes.map((n) => {
          const ov = impact[n.id]?.overrun_minutes;
          const pending = n.booking_status === "pending_manual_booking";
          const icon = pending ? "person" : n.status === "safe" ? "check_circle" : n.status === "at_risk" ? "warning" : "cancel";
          const color = pending ? "text-pending" : n.status === "safe" ? "text-safe" : n.status === "at_risk" ? "text-risk" : "text-broken";
          return (
            <div key={n.id} className="flex items-start gap-2.5 rounded-xl border border-line bg-well px-3 py-2">
              <Icon name={icon} className={`!text-[18px] ${color} mt-0.5`} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[13px] font-medium truncate">{n.title}</p>
                  <StatusPill status={pending ? "pending_manual_booking" : n.status} />
                </div>
                <p className="text-[11px] text-ink-2 tnum">
                  {dayTime(n.start)}{ov ? ` · pushed ${mins(ov)}` : ""}{n.status === "at_risk" && n.type === "hotel" ? " · late check-in holds the room" : ""}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function ExecutionList({ plan, applied }: { plan: RecoveryPlan | null; applied: boolean }) {
  const [done, setDone] = useState<Record<string, boolean>>({});
  useEffect(() => setDone({}), [plan?.id]);
  const [copied, setCopied] = useState(false);
  if (!plan) return null;
  const copy = async () => {
    await navigator.clipboard.writeText(`${plan.label}\n` + plan.action_items.map((a, i) => `${i + 1}. ${a}`).join("\n")).catch(() => {});
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };
  return (
    <Card className="p-5" delay={0.15}>
      <CardHeader icon="checklist" title="Self-booking execution list" right={<span className="text-[10px] font-semibold text-sky-ink">{applied ? "ADOPTED PLAN" : "TOP PLAN"}</span>} />
      <p className="text-[12px] text-ink-2 mb-3">{applied ? `You adopted "${plan.label}". Tick each step as you complete it.` : `Steps for "${plan.label}" if you adopt it.`}</p>
      <div className="space-y-2">
        {plan.action_items.map((a) => (
          <label key={a} className="flex items-start gap-2.5 text-[12px] cursor-pointer">
            <input type="checkbox" className="h-[18px] w-[18px] mt-0.5 accent-[#228BE6] shrink-0" checked={!!done[a]} onChange={(e) => setDone({ ...done, [a]: e.target.checked })} />
            <span className={done[a] ? "line-through text-ink-3" : "text-ink"}>{a}</span>
          </label>
        ))}
      </div>
      <button className="btn-secondary w-full mt-4 h-9" onClick={copy}><Icon name={copied ? "check" : "content_copy"} className="!text-[16px]" /> {copied ? "Copied" : "Copy checklist"}</button>
    </Card>
  );
}
