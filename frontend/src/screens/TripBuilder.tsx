import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../api";
import { useApp } from "../context";
import type { BookingInput, BookingNode, DependencyEdge, Itinerary, NodeType, RiskWarning } from "../types";
import { Card, CardHeader, Chip, EmptyState, ErrorBanner, Icon, Segmented, Skeleton, StatusPill, TYPE_ICON, TYPE_TINT, dayTime, hhmm, inr, mins, pct } from "../ui";

type Draft = BookingInput & { _key: string; _status?: string };

const TYPES: { value: NodeType; label: string; icon: string }[] = [
  { value: "flight", label: "Flight", icon: "flight" },
  { value: "train", label: "Train", icon: "train" },
  { value: "transfer", label: "Cab", icon: "local_taxi" },
  { value: "hotel", label: "Hotel", icon: "hotel" },
  { value: "activity", label: "Activity", icon: "beach_access" },
];

const POLICIES = [
  { value: "free_24h", label: "Free until 24 h before" },
  { value: "partial_50pct", label: "50% refund" },
  { value: "non_refundable", label: "Non-refundable" },
];

const EDGE_LABEL: Record<string, string> = {
  transfer_required: "transfer window",
  checkin_dependency: "check-in window",
  same_day: "same-day gap",
  sequential: "next up",
};

const toLocal = (iso: string) => iso.slice(0, 16);
let keySeq = 0;
const newKey = () => `k${++keySeq}`;

function fromNode(n: BookingNode): Draft {
  return {
    _key: newKey(),
    _status: n.booking_status && n.booking_status !== "confirmed" ? n.booking_status : n.status,
    id: n.id,
    type: n.type,
    title: n.title,
    start: n.start,
    end: n.end,
    cost: n.cost,
    provider: n.provider,
    location: n.location,
    cancellation_policy: n.cancellation_policy,
    cancellation_penalty: n.cancellation_penalty ?? null,
    refund_mode: n.refund_mode ?? "cash",
    service_code: n.service_code ?? null,
    weather_sensitive: n.weather_sensitive,
    lat: n.lat ?? null,
    lon: n.lon ?? null,
    dest_lat: n.dest_lat ?? null,
    dest_lon: n.dest_lon ?? null,
    alternatives: n.alternatives ?? [],
  };
}

const blankForm = (type: NodeType): Draft => ({
  _key: newKey(),
  type,
  title: "",
  start: "",
  end: "",
  cost: 0,
  provider: "",
  location: "",
  destination: "",
  cancellation_policy: type === "hotel" ? "free_24h" : "non_refundable",
  cancellation_penalty: null,
  refund_mode: "cash",
  service_code: "",
  weather_sensitive: type === "activity",
  alternatives: [],
});

export default function TripBuilder() {
  const app = useApp();
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [warnings, setWarnings] = useState<RiskWarning[]>([]);
  const [draft, setDraft] = useState<Draft[]>([]);
  const [dirty, setDirty] = useState(false);
  const [structureChanged, setStructureChanged] = useState(false);
  const [tripName, setTripName] = useState("My Trip");
  // the saved trip being edited; null = a new trip (Start new trip, or the demo) -> saved as its own row
  const [editingTripId, setEditingTripId] = useState<string | null>(null);
  const [filter, setFilter] = useState<NodeType | "all">("all");
  const [form, setForm] = useState<Draft>(blankForm("flight"));
  const [editing, setEditing] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const chainRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLDivElement>(null);

  const load = () => {
    setError(null);
    Promise.all([api.getItinerary(), api.riskScan(), api.getTripStatus()])
      .then(([it, rs, st]) => {
        setItinerary(it);
        setWarnings(rs.warnings);
        setTripName(st.is_demo ? "" : st.trip_name);
        setEditingTripId(st.is_demo ? null : st.trip_id);
        setDraft([...it.nodes].sort((a, b) => a.start.localeCompare(b.start)).map(fromNode));
        setDirty(false);
        setStructureChanged(false);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(load, [app.itineraryVersion]);

  // --- derived --------------------------------------------------------------------------
  const sorted = useMemo(() => [...draft].sort((a, b) => (a.start || "9").localeCompare(b.start || "9")), [draft]);
  const edgeBetween = (a?: string, b?: string): DependencyEdge | undefined =>
    itinerary?.edges.find((e) => e.source === a && e.target === b);
  const total = draft.reduce((s, d) => s + (Number(d.cost) || 0), 0);
  const counts = TYPES.map((t) => ({ ...t, n: draft.filter((d) => d.type === t.value).length }));
  const visible = filter === "all" ? sorted : sorted.filter((d) => d.type === filter);

  // --- draft editing ----------------------------------------------------------------------
  const submitForm = () => {
    setFormError(null);
    if (!form.title.trim()) return setFormError("Give the booking a name.");
    if (!form.start || !form.end) return setFormError("Enter start and end time.");
    if (form.end < form.start) return setFormError("End time is before start time.");
    if (!(Number(form.cost) >= 0)) return setFormError("Enter the price you paid.");
    const clean: Draft = {
      ...form,
      title: form.title.trim(),
      provider: form.provider.trim() || "unknown",
      cost: Number(form.cost),
      service_code: form.service_code?.trim() || null,
      cancellation_penalty: form.cancellation_penalty === null || (form.cancellation_penalty as any) === "" ? null : Number(form.cancellation_penalty),
    };
    if (editing) {
      setDraft((d) => d.map((x) => (x._key === editing ? { ...clean, _key: editing } : x)));
      const before = draft.find((x) => x._key === editing);
      if (before && (before.start !== clean.start || before.end !== clean.end || before.type !== clean.type)) setStructureChanged(true);
    } else {
      setDraft((d) => [...d, { ...clean, id: undefined, _status: "new" }]);
      setStructureChanged(true);
    }
    setDirty(true);
    setEditing(null);
    setForm(blankForm(form.type));
  };

  const edit = (d: Draft) => {
    setEditing(d._key);
    setForm({ ...d, start: toLocal(d.start), end: toLocal(d.end) });
    setShowAdvanced(true);
  };

  const remove = (key: string) => {
    setDraft((d) => d.filter((x) => x._key !== key));
    setDirty(true);
    setStructureChanged(true);
    if (editing === key) {
      setEditing(null);
      setForm(blankForm(form.type));
    }
  };

  const applyTrip = async () => {
    setSaving(true);
    setError(null);
    try {
      const bookings: BookingInput[] = draft.map(({ _key, _status, ...b }) => ({
        ...b,
        start: b.start.length === 16 ? `${b.start}:00` : b.start,
        end: b.end.length === 16 ? `${b.end}:00` : b.end,
      }));
      // keep the traveler's existing connections unless bookings were added/removed/re-timed
      const keepEdges = !structureChanged && itinerary ? itinerary.edges : undefined;
      if (!tripName.trim() || /^demo trip/i.test(tripName.trim())) {
        setError("Give your trip its own name (e.g. Pune → Indore) before saving.");
        return;
      }
      await api.setItinerary(tripName.trim(), bookings, keepEdges, editingTripId);
      app.toast(`"${tripName.trim()}" saved. Recovery, the digital twin and monitoring now follow this trip`, "success");
      app.refreshTrip();
      app.setLastDisruption({ disruption: null, impact_report: null });
      app.bumpItinerary();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const loadDemo = async () => {
    await api.loadDemo();
    app.setLastDisruption({ disruption: null, impact_report: null });
    app.refreshTrip();
    app.bumpItinerary();
    app.toast("Demo trip loaded", "info");
  };

  // a brand-new, empty trip: nothing from the current or demo itinerary carries over
  const startNewTrip = () => {
    setDraft([]);
    setTripName("");
    setEditingTripId(null);
    setEditing(null);
    setForm(blankForm("flight"));
    setDirty(true);
    setStructureChanged(true);
    setFilter("all");
    window.setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  };

  return (
    <div className="space-y-10">
      {/* ======================= HERO ======================= */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center pt-2 lg:pt-6">
        <motion.div className="lg:col-span-6 space-y-6" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <Chip><Icon name="shield" className="!text-[14px]" /> INTELLIGENT TRAVEL RECOVERY</Chip>
          <h1 className="text-[34px] leading-[42px] md:text-[44px] md:leading-[52px] font-bold tracking-[-0.02em]">
            When one booking breaks,
            <br />
            <span className="bg-gradient-to-r from-sky-ink to-sky bg-clip-text text-transparent">know exactly what to do next.</span>
          </h1>
          <p className="text-[16px] leading-7 text-ink-2 max-w-xl">
            See the impact across your entire trip, compare feasible recovery plans, understand weather risk, and stay ahead of cascade
            disruptions across India's skies, rails and roads.
          </p>
          <div className="flex flex-wrap gap-3">
            <button className="btn-solid h-11 px-5" onClick={() => chainRef.current?.scrollIntoView({ behavior: "smooth" })}>
              <Icon name="add_circle" className="!text-[20px]" /> Build my trip <Icon name="arrow_forward" className="!text-[18px]" />
            </button>
            <button className="btn-secondary h-11 px-5" onClick={() => app.go("console")}>
              <Icon name="bolt" className="!text-[20px]" /> Open Recovery Console
            </button>
          </div>
          <p className="text-[12px] text-ink-2 flex items-center gap-1.5">
            <Icon name="verified_user" className="!text-[16px] text-sky" /> TripRescue never books, cancels, or charges payment on your behalf. Advisory only.
          </p>
        </motion.div>

        <motion.div className="lg:col-span-6 relative" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1 }}>
          <HeroVideo />
        </motion.div>
      </section>

      {/* ======================= CHAIN + FORM ======================= */}
      <section ref={chainRef} className="scroll-mt-24 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-[22px] leading-8 md:text-[30px] md:leading-[38px] font-semibold tracking-[-0.015em] flex items-start gap-2">
              <Icon name="account_tree" className="text-sky" /> Connected Multi-Modal Itinerary Chain
            </h2>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <input value={tripName} placeholder="Name your trip" onChange={(e) => { setTripName(e.target.value); setDirty(true); }} className="input h-8 w-56 text-[13px] font-medium" aria-label="Trip name" />
              <button className="btn-solid h-8 text-[12px]" onClick={startNewTrip}><Icon name="add" className="!text-[18px]" /> Start new trip</button>
              <button className="btn-ghost" onClick={app.openTrips}><Icon name="folder_open" className="!text-[18px]" /> My trips</button>
              <button className="btn-ghost" onClick={loadDemo}><Icon name="travel_explore" className="!text-[18px]" /> Load demo</button>
            </div>
          </div>
          <div className="flex flex-wrap gap-1 p-1 rounded-full bg-white border border-line">
            {[{ value: "all" as const, label: "All bookings", n: draft.length }, ...counts.filter((c) => c.n > 0)].map((t) => (
              <button key={t.value} onClick={() => setFilter(t.value)} className={`h-8 px-3.5 rounded-full text-[12px] font-medium transition ${filter === t.value ? "bg-icy text-sky-ink" : "text-ink-2 hover:text-ink"}`}>
                {t.label} <span className="tnum opacity-70">({t.n})</span>
              </button>
            ))}
          </div>
        </div>

        {error && <ErrorBanner message={error} onRetry={load} />}


        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
          {/* ---- chain ---- */}
          <Card className="lg:col-span-8 p-4 md:p-5">
            <div className="flex items-center justify-between rounded-lg bg-canvas border border-line px-3 py-2 mb-4">
              <span className="eyebrow flex items-center gap-1.5"><Icon name="timeline" className="!text-[16px] text-sky" /> Propagation sequence & transfer windows</span>
              <span className="text-[11px] text-ink-2 tnum">{draft.length} bookings · {inr(total)}</span>
            </div>
            {itinerary === null ? (
              <div className="space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20" />)}</div>
            ) : visible.length === 0 ? (
              <EmptyState icon="luggage" title="No bookings yet" body="Add your first flight, train, cab, hotel or activity with the form. Add them in any order - they're sorted by time and connected automatically." />
            ) : (
              <div className="space-y-2">
                <AnimatePresence initial={false}>
                  {visible.map((d, i) => {
                    const next = visible[i + 1];
                    const edge = filter === "all" ? edgeBetween(d.id, next?.id) : undefined;
                    const warn = edge && warnings.find((w) => w.node_id === edge.target);
                    return (
                      <motion.div key={d._key} layout initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, height: 0 }} transition={{ delay: i * 0.03 }}>
                        <BookingRow d={d} active={editing === d._key} onEdit={() => edit(d)} onRemove={() => remove(d._key)} />
                        {next && filter === "all" && (
                          <div className={`mx-4 my-1.5 flex items-center justify-between rounded-lg px-3 py-1.5 text-[12px] ${warn ? "bg-broken-bg text-broken-ink border border-red-200" : "text-ink-2"}`}>
                            <span className="flex items-center gap-1.5">
                              <Icon name={warn ? "warning" : "schedule"} className="!text-[16px]" />
                              {warn
                                ? `Buffer compressed: only ${edge!.buffer_minutes} min before ${next.title}`
                                : edge
                                ? `Buffer window: ${edge.buffer_minutes} min · ${EDGE_LABEL[edge.type] ?? edge.type}`
                                : "Connection inferred when you apply"}
                            </span>
                            {warn && <span className="text-[10px] font-semibold uppercase tracking-wide">{warn.severity} risk</span>}
                          </div>
                        )}
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
            )}
          </Card>

          {/* ---- form + simulator ---- */}
          <div ref={formRef} className="lg:col-span-4 space-y-5 lg:sticky lg:top-24">
            <AnimatePresence initial={false}>
              {dirty && (
                <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="card p-4 border-sky/40 ring-1 ring-sky/20 space-y-3">
                  <p className="text-[13px] font-medium flex items-center gap-2">
                    <Icon name="pending" className="text-sky !text-[18px]" />
                    {draft.length} booking{draft.length === 1 ? "" : "s"} ready{structureChanged ? " · connections are inferred on save" : ""}
                  </p>
                  <label className="block">
                    <span className="label">Trip name</span>
                    <input
                      className={`input ${!tripName.trim() ? "border-sky ring-4 ring-sky/15" : ""}`}
                      placeholder="e.g. Pune → Indore"
                      value={tripName}
                      onChange={(e) => setTripName(e.target.value)}
                      aria-label="Trip name for saving"
                    />
                    <span className="block text-[11px] text-ink-3 mt-1">
                      {editingTripId ? "Updates this saved trip in My trips." : "Saved as a new trip in My trips."}
                    </span>
                  </label>
                  <button className="btn-primary w-full" disabled={saving || draft.length === 0 || !tripName.trim()} onClick={applyTrip}>
                    <Icon name="rocket_launch" className="!text-[18px]" /> {saving ? "Saving…" : "Save & use this trip"}
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
            <Card className="p-5" delay={0.05}>
              <CardHeader icon={editing ? "edit" : "add_box"} title={editing ? "Edit booking" : "Add booking / segment"} right={<Chip tone="slate">Your price</Chip>} />
              <div className="grid grid-cols-5 gap-1 p-1 rounded-xl bg-canvas border border-line mb-4">
                {TYPES.map((t) => (
                  <button key={t.value} onClick={() => setForm((f) => ({ ...blankForm(t.value), ...(editing ? f : {}), type: t.value }))} className={`flex flex-col items-center gap-0.5 py-2 rounded-lg text-[11px] font-medium transition ${form.type === t.value ? "bg-white shadow-[0_2px_6px_rgba(16,42,67,0.08)] text-sky-ink" : "text-ink-2 hover:text-ink"}`}>
                    <Icon name={t.icon} className="!text-[20px]" />
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="space-y-3">
                <Field label="Title">
                  <input className="input" placeholder={{ flight: "e.g. Airline + flight no., BOM → BLR", train: "e.g. Train name, CSMT → PUNE", transfer: "e.g. Airport → hotel cab", hotel: "e.g. Hotel name check-in", activity: "e.g. City tour", event: "Booking name" }[form.type]} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Provider"><input className="input" placeholder="Airline / hotel / operator" value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} /></Field>
                  <Field label="Price paid (₹)"><input className="input tnum" type="number" min={0} value={form.cost || ""} onChange={(e) => setForm({ ...form, cost: Number(e.target.value) })} /></Field>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Field label={form.type === "hotel" ? "Check-in" : "Start"}><input className="input text-[13px]" type="datetime-local" value={toLocal(form.start)} onChange={(e) => setForm({ ...form, start: e.target.value })} /></Field>
                  <Field label={form.type === "hotel" ? "Check-in ends" : "End"}><input className="input text-[13px]" type="datetime-local" value={toLocal(form.end)} onChange={(e) => setForm({ ...form, end: e.target.value })} /></Field>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Field label={["flight", "train", "transfer"].includes(form.type) ? "Origin" : "Location"}><input className="input" placeholder={["flight", "train", "transfer"].includes(form.type) ? "From (city / airport)" : "City or area"} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field>
                  {["flight", "train", "transfer"].includes(form.type) ? (
                    <Field label="Destination"><input className="input" placeholder="To (city / airport)" value={form.destination ?? ""} onChange={(e) => setForm({ ...form, destination: e.target.value })} /></Field>
                  ) : (
                    <Field label="Outdoor?">
                      <label className="h-10 flex items-center gap-2 text-sm">
                        <input type="checkbox" className="h-[18px] w-[18px] accent-[#228BE6]" checked={form.weather_sensitive} onChange={(e) => setForm({ ...form, weather_sensitive: e.target.checked })} />
                        Weather-sensitive
                      </label>
                    </Field>
                  )}
                </div>

                <button onClick={() => setShowAdvanced((s) => !s)} className="w-full flex items-center justify-between text-[12px] font-semibold text-sky-ink pt-1">
                  Refund terms & live tracking
                  <Icon name="expand_more" className={`!text-[18px] transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
                </button>
                <AnimatePresence initial={false}>
                  {showAdvanced && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden space-y-3">
                      <Field label="Cancellation policy">
                        <select className="input" value={form.cancellation_policy} onChange={(e) => setForm({ ...form, cancellation_policy: e.target.value })}>
                          {POLICIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                        </select>
                      </Field>
                      <div className="grid grid-cols-2 gap-3">
                        <Field label="Fixed penalty (₹, optional)">
                          <input className="input tnum" type="number" min={0} placeholder="overrides policy" value={form.cancellation_penalty ?? ""} onChange={(e) => setForm({ ...form, cancellation_penalty: e.target.value === "" ? null : Number(e.target.value) })} />
                        </Field>
                        <Field label={form.type === "train" ? "Train number" : "Flight number"}>
                          <input className="input" placeholder={form.type === "train" ? "e.g. 12123" : "e.g. AI631"} disabled={!["flight", "train"].includes(form.type)} value={form.service_code ?? ""} onChange={(e) => setForm({ ...form, service_code: e.target.value.toUpperCase() })} />
                        </Field>
                      </div>
                      <Field label="Refund comes back as">
                        <Segmented size="sm" value={form.refund_mode} onChange={(v) => setForm({ ...form, refund_mode: v })} options={[{ value: "cash", label: "Cash" }, { value: "credit", label: "Provider credit" }, { value: "none", label: "None" }]} />
                      </Field>
                      {(form.alternatives?.length ?? 0) > 0 && (
                        <p className="text-[11px] text-ink-2 flex items-center gap-1"><Icon name="alt_route" className="!text-[15px]" /> {form.alternatives!.length} known alternatives kept for recovery</p>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>

                {formError && <p className="text-[12px] text-broken">{formError}</p>}
                <div className="flex gap-2 pt-1">
                  <button className="btn-solid flex-1" onClick={submitForm}>
                    <Icon name={editing ? "check" : "add_link"} className="!text-[18px]" /> {editing ? "Update booking" : "Add to journey chain"}
                  </button>
                  {editing && <button className="btn-secondary" onClick={() => { setEditing(null); setForm(blankForm(form.type)); }}>Cancel</button>}
                </div>
              </div>
            </Card>

            <CascadeSimulator draft={sorted} edges={itinerary?.edges ?? []} disabled={dirty} />
          </div>
        </div>
      </section>

    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

function BookingRow({ d, active, onEdit, onRemove }: { d: Draft; active: boolean; onEdit: () => void; onRemove: () => void }) {
  const status = d._status ?? "safe";
  return (
    <div className={`group flex items-center gap-3 rounded-xl border px-3 py-3 transition ${active ? "border-sky bg-icy/40" : "border-line bg-well hover:border-line-2 hover:shadow-l1"}`}>
      <div className={`h-11 w-11 rounded-xl grid place-items-center shrink-0 ${TYPE_TINT[d.type]}`}>
        <Icon name={TYPE_ICON[d.type]} className="!text-[22px]" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <p className="font-semibold text-[14px] truncate">{d.title}</p>
          <span className="text-[11px] text-ink-2">{d.provider}</span>
          {d.service_code && <span className="text-[11px] font-semibold text-sky-ink tnum">{d.service_code}</span>}
        </div>
        <p className="text-[12px] text-ink-2 tnum mt-0.5">
          {d.start ? dayTime(d.start) : "—"} <Icon name="east" className="!text-[14px] mx-0.5" /> {d.end ? hhmm(d.end) : "—"}
          {d.location && <span className="ml-2 text-ink-3">· {d.location}</span>}
        </p>
      </div>
      <div className="text-right shrink-0 space-y-1">
        {status === "new" ? <Chip tone="sky">NEW</Chip> : <StatusPill status={status} />}
        <p className="text-[12px] font-semibold tnum">{inr(Number(d.cost) || 0)}</p>
      </div>
      <div className="flex flex-col gap-0.5 opacity-60 group-hover:opacity-100 transition">
        <button onClick={onEdit} className="h-7 w-7 grid place-items-center rounded-md hover:bg-icy" aria-label="Edit"><Icon name="edit" className="!text-[16px]" /></button>
        <button onClick={onRemove} className="h-7 w-7 grid place-items-center rounded-md hover:bg-broken-bg text-broken" aria-label="Remove"><Icon name="delete" className="!text-[16px]" /></button>
      </div>
    </div>
  );
}

function CascadeSimulator({ draft, edges, disabled }: { draft: Draft[]; edges: DependencyEdge[]; disabled: boolean }) {
  const app = useApp();
  const candidates = draft.filter((d) => d.id);
  const [nodeId, setNodeId] = useState<string>("");
  const [delay, setDelay] = useState(45);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!candidates.find((c) => c.id === nodeId)) setNodeId(candidates[0]?.id ?? "");
  }, [draft]);
  const node = candidates.find((c) => c.id === nodeId);
  const out = edges.find((e) => e.source === nodeId);
  const next = out ? draft.find((d) => d.id === out.target) : undefined;
  const nextTitle = next?.title;
  // real slack = time between this booking ending and the next one starting, minus the buffer
  const gap = node && next ? Math.round((new Date(next.start).getTime() - new Date(node.end).getTime()) / 60000) : 0;
  const slack = out ? gap - out.buffer_minutes : 0;
  const eats = out ? delay - slack : 0;

  const run = async () => {
    if (!nodeId) return;
    setBusy(true);
    try {
      // a stress test starts from the trip as booked - earlier disruptions don't stack on top
      await api.reset();
      const res = await api.disrupt(nodeId, "delay", delay, "traveler simulation");
      app.setLastDisruption({ disruption: res.disruption, impact_report: res.impact_report });
      app.bumpItinerary();
      app.go("console");
    } catch (e: any) {
      app.toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-5" delay={0.1}>
      <CardHeader icon="science" title="Cascade simulator" sub="Delay one booking (from the trip as booked) and jump straight to its recovery plans." right={<Chip tone="slate">Applies to trip</Chip>} />
      {candidates.length === 0 ? (
        <p className="text-sm text-ink-2">Apply your trip first to simulate delays.</p>
      ) : (
        <div className="space-y-3">
          <select className="input" value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
            {candidates.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          <div className="rounded-xl bg-canvas border border-line p-3">
            <div className="flex justify-between text-[12px] mb-1">
              <span className="text-ink-2">Delay on {node?.title ?? "booking"}</span>
              <span className="font-semibold text-broken tnum">+{mins(delay)}</span>
            </div>
            <input type="range" min={0} max={360} step={15} value={delay} onChange={(e) => setDelay(Number(e.target.value))} className="w-full" />
            <div className="flex justify-between text-[10px] text-ink-3 tnum"><span>0m</span><span>+3h</span><span>+6h</span></div>
          </div>
          {out && (
            <div className={`rounded-xl p-3 text-[12px] border ${eats > 0 ? "bg-broken-bg border-red-200 text-broken-ink" : "bg-safe-bg border-emerald-200 text-safe-ink"}`}>
              <p className="font-semibold flex items-center gap-1"><Icon name={eats > 0 ? "cancel" : "check_circle"} className="!text-[16px]" /> {eats > 0 ? "Downstream impact warning" : "Buffer absorbs it"}</p>
              <p className="mt-0.5">
                {eats > 0
                  ? `${nextTitle} needs ${mins(out.buffer_minutes)} after ${node?.title}; with ${mins(Math.max(0, slack))} of slack, this delay overruns it by ${mins(eats)} - the recovery engine will re-plan it.`
                  : `${nextTitle} starts ${mins(gap)} after ${node?.title} ends - still ${mins(-eats)} of slack after this delay. Only ${node?.title} itself is re-planned.`}
              </p>
            </div>
          )}
          <button className="btn-solid w-full" disabled={busy || disabled || delay === 0} onClick={run}>
            <Icon name="alt_route" className="!text-[18px]" /> {busy ? "Simulating…" : "Simulate & check recoveries"}
          </button>
          {disabled && <p className="text-[11px] text-ink-3">Apply your unsaved trip changes first.</p>}
        </div>
      )}
    </Card>
  );
}

/** Hero clip: poster shows instantly, video fades in once it can play, pauses when off-screen
 *  or in a background tab (no wasted decoding), and stays a still image for reduced motion. */
function HeroVideo() {
  const ref = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const v = ref.current;
    if (!v || reduced) return;
    const play = () => v.play().catch(() => {});
    const io = new IntersectionObserver(([e]) => (e.isIntersecting && !document.hidden ? play() : v.pause()), { threshold: 0.15 });
    io.observe(v);
    const onVis = () => (document.hidden ? v.pause() : play());
    document.addEventListener("visibilitychange", onVis);
    return () => {
      io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [reduced]);

  return (
    <div className="relative rounded-[20px] overflow-hidden shadow-l3 aspect-[16/10] bg-icy">
      <img src="/hero-poster.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" decoding="async" />
      {!reduced && (
        <video
          ref={ref}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-700 ${ready ? "opacity-100" : "opacity-0"}`}
          poster="/hero-poster.jpg"
          muted
          loop
          playsInline
          autoPlay
          preload="auto"
          disablePictureInPicture
          onCanPlay={() => setReady(true)}
          aria-hidden
        >
          <source src="/hero.webm" type="video/webm" />
          <source src="/hero.mp4" type="video/mp4" />
        </video>
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-white/10 to-transparent pointer-events-none" />
    </div>
  );
}
