import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../api";
import { useApp } from "../context";
import type { BookingNode, MonitorStatus, ProviderCheck } from "../types";
import { Card, CardHeader, Chip, EmptyState, ErrorBanner, Icon, Skeleton, StatusPill, dayTime, hhmm, mins, timeAgo } from "../ui";

const PSTATUS: Record<ProviderCheck["status"], { label: string; cls: string; icon: string }> = {
  ok: { label: "OK", cls: "bg-safe-bg text-safe-ink", icon: "check_circle" },
  skipped: { label: "Skipped", cls: "bg-canvas-3 text-ink-2", icon: "skip_next" },
  unavailable: { label: "Unavailable", cls: "bg-dropped-bg text-dropped-ink", icon: "cloud_off" },
  error: { label: "Error", cls: "bg-broken-bg text-broken-ink", icon: "error" },
};

const PROVIDER_ICON: Record<string, string> = {
  AviationStack: "flight",
  "Open-Meteo": "partly_cloudy_day",
  "Road (derived from weather)": "add_road",
  "Indian Railways": "train",
  Hotel: "hotel",
};

export default function Monitoring() {
  const app = useApp();
  const [status, setStatus] = useState<MonitorStatus | null>(null);
  const [nodes, setNodes] = useState<BookingNode[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [replayAt, setReplayAt] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [statusFilter, setStatusFilter] = useState<ProviderCheck["status"] | "all">("all");
  const [providerFilter, setProviderFilter] = useState<string>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busyEvent, setBusyEvent] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  const load = () => {
    setError(null);
    Promise.all([api.monitorStatus(), api.getItinerary()])
      .then(([s, it]) => {
        setStatus(s);
        setNodes(it.nodes);
        if (!replayAt && it.nodes.length) {
          // default replay moment: 3 h before the first booking - handy for demos
          const first = [...it.nodes].sort((a, b) => a.start.localeCompare(b.start))[0];
          const d = new Date(new Date(first.start).getTime() - 3 * 3600 * 1000);
          const pad = (n: number) => String(n).padStart(2, "0");
          setReplayAt(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`);
        }
      })
      .catch((e) => setError(e.message));
  };

  useEffect(load, [app.alertsVersion, app.itineraryVersion]);
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const run = async (at?: string) => {
    setRunning(true);
    try {
      const r = await api.monitorRun(at ? `${at}:00` : undefined);
      app.toast(r.new_alerts ? `${r.new_alerts} new alert${r.new_alerts > 1 ? "s" : ""} from ${r.checks} checks` : `${r.checks} checks · no new disruptions${r.suppressed_duplicates ? ` · ${r.suppressed_duplicates} duplicate${r.suppressed_duplicates > 1 ? "s" : ""} suppressed` : ""}`, r.new_alerts ? "warn" : "success");
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const title = (id: string) => nodes.find((n) => n.id === id)?.title ?? id;
  const providers = useMemo(() => Array.from(new Set(status?.providers.map((p) => p.provider) ?? [])), [status]);
  const rows = (status?.providers ?? [])
    .filter((p) => statusFilter === "all" || p.status === statusFilter)
    .filter((p) => providerFilter === "all" || p.provider === providerFilter)
    .sort((a, b) => a.node_id.localeCompare(b.node_id) || a.provider.localeCompare(b.provider));

  const next = status?.last_run?.next_run ? new Date(status.last_run.next_run).getTime() - now : null;
  const countdown = next != null && next > 0 ? `${Math.floor(next / 60000)}:${String(Math.floor((next % 60000) / 1000)).padStart(2, "0")}` : null;

  const act = async (id: string, kind: "apply" | "dismiss") => {
    setBusyEvent(id);
    try {
      if (kind === "apply") {
        const res = await api.applyEvent(id);
        const ev = status?.open_events.find((e) => e.id === id);
        app.setLastDisruption({ disruption: { node_id: ev?.node_id, reason: ev?.reason }, impact_report: res.impact_report });
        app.bumpItinerary();
        const broken = res.itinerary.nodes.filter((x) => x.status === "broken" || x.status === "cancelled").length;
        app.toast(broken ? `Applied: ${broken} booking(s) broken - recovery plans are ready` : "Applied: bookings are at risk but nothing is broken yet", broken ? "warn" : "info");
        app.go("console");
      } else {
        await api.dismissEvent(id);
        load();
      }
    } catch (e: any) {
      app.toast(e.message, "error");
    } finally {
      setBusyEvent(null);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <Chip><Icon name="monitor_heart" className="!text-[14px]" /> PROACTIVE MONITORING</Chip>
        <h1 className="text-[28px] md:text-[32px] font-bold tracking-[-0.02em] mt-2">Every booking, checked against live providers</h1>
        <p className="text-[13px] text-ink-2 mt-1">Flights, weather, flooding and roads are re-checked on a schedule. A real change alerts you once; repeats are suppressed; worse news alerts again.</p>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <Card className="p-5 lg:col-span-5">
          <CardHeader icon="schedule" title="Scheduler" right={<Chip tone={status?.scheduler === "inprocess" ? "safe" : "slate"}>{status?.scheduler === "inprocess" ? "In-app timer" : "External cron"}</Chip>} />
          {!status ? <Skeleton className="h-28" /> : (
            <>
              <div className="flex items-end gap-6">
                <div>
                  <p className="text-[36px] font-bold tnum leading-none text-sky-ink">{status.interval_minutes}<span className="text-base font-semibold text-ink-2"> min</span></p>
                  <p className="text-[11px] text-ink-2 mt-1">check interval</p>
                </div>
                <div className="text-[12px] text-ink-2 space-y-0.5">
                  <p>Last run: <b className="text-ink">{status.last_run ? `${timeAgo(status.last_run.at)} (${status.last_run.trigger})` : "not yet"}</b></p>
                  <p>Next run: <b className="text-ink tnum">{countdown ? `in ${countdown}` : status.scheduler === "inprocess" ? "starting…" : "via cron"}</b></p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 mt-4">
                <button className="btn-primary" disabled={running} onClick={() => run()}>
                  <Icon name={running ? "progress_activity" : "play_arrow"} className={`!text-[18px] ${running ? "animate-spin" : ""}`} /> {running ? "Checking…" : "Run check now"}
                </button>
                <button className="btn-ghost" onClick={() => setShowAdvanced((s) => !s)}>Advanced <Icon name="expand_more" className={`!text-[16px] transition-transform ${showAdvanced ? "rotate-180" : ""}`} /></button>
              </div>
              <AnimatePresence>
                {showAdvanced && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                    <div className="mt-3 rounded-xl bg-canvas border border-line p-3 space-y-2">
                      <p className="text-[12px] text-ink-2">Replay the checks as if it were a given moment, e.g. the morning of travel, so flights fall inside the live-status window.</p>
                      <div className="flex gap-2">
                        <input type="datetime-local" className="input text-[13px]" value={replayAt} onChange={(e) => setReplayAt(e.target.value)} />
                        <button className="btn-secondary shrink-0" disabled={running || !replayAt} onClick={() => run(replayAt)}><Icon name="history" className="!text-[18px]" /> Replay</button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </>
          )}
        </Card>

        <Card className="p-5 lg:col-span-7" delay={0.05}>
          <CardHeader icon="insights" title="Last run summary" sub={status?.last_run ? `${status.last_run.checks} provider checks at ${dayTime(status.last_run.at)}` : "Run a check to see results"} />
          {!status ? <Skeleton className="h-24" /> : !status.last_run ? (
            <EmptyState icon="pending" title="No checks yet" body="The first scheduled pass runs shortly after the server starts, or run one now." />
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
              {(["ok", "skipped", "unavailable", "error"] as const).map((s) => (
                <button key={s} onClick={() => setStatusFilter(statusFilter === s ? "all" : s)} className={`rounded-xl border p-3 text-left transition ${statusFilter === s ? "border-sky bg-icy/50" : "border-line bg-canvas hover:border-line-2"}`}>
                  <p className={`text-[22px] font-bold tnum ${s === "error" && status.last_run!.by_status[s] ? "text-broken" : "text-ink"}`}>{status.last_run!.by_status[s] ?? 0}</p>
                  <p className="text-[10px] font-semibold uppercase text-ink-2">{PSTATUS[s].label}</p>
                </button>
              ))}
              <div className="rounded-xl border border-line bg-canvas p-3">
                <p className={`text-[22px] font-bold tnum ${status.last_run.new_alerts ? "text-risk" : "text-ink"}`}>{status.last_run.new_alerts}</p>
                <p className="text-[10px] font-semibold uppercase text-ink-2">New alerts</p>
              </div>
              <div className="rounded-xl border border-line bg-canvas p-3">
                <p className="text-[22px] font-bold tnum">{status.last_run.suppressed_duplicates}</p>
                <p className="text-[10px] font-semibold uppercase text-ink-2">Dupes suppressed</p>
              </div>
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 items-start">
        <Card className="lg:col-span-8 p-5" delay={0.1}>
          <CardHeader
            icon="dns"
            title="Provider health & evidence"
            sub="Each booking × each relevant source, with freshness"
            right={
              <select className="input h-8 text-[12px] w-44" value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)}>
                <option value="all">All providers</option>
                {providers.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            }
          />
          {!status ? (
            <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : rows.length === 0 ? (
            <EmptyState icon="dns" title="No provider results" body={status.providers.length ? "Nothing matches these filters." : "Run a check to populate provider health."} />
          ) : (
            <div className="rounded-xl border border-line overflow-hidden divide-y divide-line">
              {rows.map((p, i) => {
                const key = `${p.provider}|${p.node_id}`;
                const stale = p.status === "ok" && p.fresh === false;
                return (
                  <motion.div key={key} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }} className="bg-white">
                    <button className="w-full grid grid-cols-12 gap-2 items-center px-3 py-2.5 text-left hover:bg-canvas transition" onClick={() => setExpanded(expanded === key ? null : key)}>
                      <span className="col-span-4 flex items-center gap-2 text-[13px] font-medium min-w-0">
                        <Icon name={PROVIDER_ICON[p.provider] ?? "cloud"} className="!text-[18px] text-sky" />
                        <span className="truncate">{p.provider}</span>
                      </span>
                      <span className="col-span-4 text-[12px] text-ink-2 truncate">{title(p.node_id)}</span>
                      <span className="col-span-2">
                        <span className={`inline-flex items-center gap-1 h-6 px-2 rounded-full text-[10px] font-semibold ${PSTATUS[p.status].cls}`}>
                          <Icon name={PSTATUS[p.status].icon} className="!text-[12px]" />{PSTATUS[p.status].label}
                        </span>
                      </span>
                      <span className={`col-span-2 text-[11px] tnum text-right ${stale ? "text-ink-3" : "text-ink-2"}`} title={`fresh until ${p.fresh_until}`}>
                        <span className={`inline-block h-1.5 w-1.5 rounded-full mr-1 ${p.status !== "ok" ? "bg-dropped" : stale ? "bg-dropped" : "bg-safe"}`} />
                        {hhmm(p.checked_at)}
                      </span>
                    </button>
                    <AnimatePresence>
                      {expanded === key && (
                        <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden">
                          <div className="px-3 pb-3 flex flex-wrap gap-1.5">
                            {Object.entries(p.evidence).map(([k, v]) => (
                              <span key={k} className="inline-flex items-center h-6 px-2 rounded-md bg-canvas border border-line text-[11px]">
                                <span className="text-ink-3 mr-1">{k.replace(/_/g, " ")}</span>
                                <span className="font-medium tnum">{v === null || v === undefined ? "—" : String(v)}</span>
                              </span>
                            ))}
                            <span className="text-[11px] text-ink-3 self-center ml-1">fresh until {hhmm(p.fresh_until)}</span>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                );
              })}
            </div>
          )}
        </Card>

        <Card className="lg:col-span-4 p-5" delay={0.15}>
          <CardHeader icon="crisis_alert" title="Open events" right={<span className="text-[11px] tnum text-ink-2">{status?.open_events.length ?? 0} open</span>} />
          {!status ? <Skeleton className="h-32" /> : status.open_events.length === 0 ? (
            <EmptyState icon="verified" title="Nothing to handle" body="No live check has found a disruption that you haven't acted on." />
          ) : (
            <div className="space-y-3">
              {status.open_events.map((e) => (
                <motion.div key={e.id} layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-line overflow-hidden">
                  <div className={`h-1 ${e.severity === "high" ? "bg-broken" : "bg-risk"}`} />
                  <div className="p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[13px] font-semibold truncate">{title(e.node_id)}</p>
                      <StatusPill status={e.kind === "cancel" ? "cancelled" : "at_risk"} label={e.kind === "cancel" ? "Cancellation" : `Delay ~${mins(e.delay_minutes ?? 0)}`} />
                    </div>
                    <p className="text-[12px] text-ink-2">{e.reason}</p>
                    <p className="text-[11px] text-ink-3">{e.provider} · detected {timeAgo(e.detected_at)}</p>
                    <div className="flex gap-2">
                      <button className="btn-primary h-9 flex-1" disabled={busyEvent !== null} onClick={() => act(e.id, "apply")}>Apply to my trip</button>
                      <button className="btn-secondary h-9" disabled={busyEvent !== null} onClick={() => act(e.id, "dismiss")}>Dismiss</button>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
          <button className="btn-ghost w-full mt-3" onClick={app.openAlerts}><Icon name="notifications" className="!text-[16px]" /> Open alerts</button>
        </Card>
      </div>
    </div>
  );
}
