import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../api";
import { useApp } from "../context";
import type { AlertNotification } from "../types";
import { EmptyState, ErrorBanner, Icon, Segmented, Skeleton, StatusPill, inr, mins, timeAgo } from "../ui";

export default function AlertsDrawer({ open, onClose, onUnread }: { open: boolean; onClose: () => void; onUnread: (n: number) => void }) {
  const app = useApp();
  const [tab, setTab] = useState<"all" | "unread">("all");
  const [notes, setNotes] = useState<AlertNotification[] | null>(null);
  const [openEvents, setOpenEvents] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    Promise.all([api.notifications(), api.monitorStatus()])
      .then(([n, s]) => {
        setNotes(n.notifications);
        onUnread(n.unread);
        setOpenEvents(new Set(s.open_events.map((e) => e.id)));
      })
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    if (open) load();
  }, [open, app.alertsVersion]);

  const markRead = async (n: AlertNotification) => {
    if (n.read) return;
    await api.markRead(n.id).catch(() => {});
    setNotes((all) => all?.map((x) => (x.id === n.id ? { ...x, read: true } : x)) ?? null);
    onUnread(Math.max(0, (notes?.filter((x) => !x.read).length ?? 1) - 1));
  };

  const apply = async (n: AlertNotification) => {
    setBusy(n.event_id);
    try {
      const res = await api.applyEvent(n.event_id);
      app.setLastDisruption({ disruption: { node_id: n.node_id, reason: n.message }, impact_report: res.impact_report });
      app.bumpItinerary();
      const broken = res.itinerary.nodes.filter((x) => x.status === "broken" || x.status === "cancelled").length;
      app.toast(broken ? `Alert applied: ${broken} booking(s) broken - pick a recovery plan` : "Alert applied: bookings are at risk but nothing is broken yet", broken ? "warn" : "info");
      onClose();
      app.go("console");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const dismiss = async (n: AlertNotification) => {
    setBusy(n.event_id);
    await api.dismissEvent(n.event_id).catch((e) => setError(e.message));
    setBusy(null);
    load();
  };

  const shown = (notes ?? []).filter((n) => tab === "all" || !n.read);

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[1100]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-ink/15 backdrop-blur-[2px]" onClick={onClose} />
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
            className="absolute right-0 top-0 h-full w-full sm:w-[440px] bg-canvas shadow-l3 border-l border-line flex flex-col"
          >
            <div className="glass border-b border-line px-5 py-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold flex items-center gap-2"><Icon name="notifications_active" className="text-sky" /> Alerts</h3>
                <p className="text-[11px] text-ink-2">From live provider checks every 20 min. Each change alerts once.</p>
              </div>
              <button onClick={onClose} className="h-8 w-8 grid place-items-center rounded-lg hover:bg-white" aria-label="Close"><Icon name="close" /></button>
            </div>
            <div className="px-5 pt-3 flex items-center justify-between">
              <Segmented value={tab} onChange={setTab} size="sm" options={[{ value: "all", label: "All" }, { value: "unread", label: "Unread" }]} />
              <button className="btn-ghost" onClick={() => { onClose(); app.go("monitor"); }}>Monitoring <Icon name="arrow_forward" className="!text-[16px]" /></button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
              {error && <ErrorBanner message={error} onRetry={load} />}
              {notes === null ? (
                [0, 1].map((i) => <Skeleton key={i} className="h-32" />)
              ) : shown.length === 0 ? (
                <EmptyState icon="notifications_paused" title="No alerts" body="When a live check finds a real delay, cancellation or unsafe weather, it lands here." />
              ) : (
                shown.map((n, i) => {
                  const isOpen = openEvents.has(n.event_id);
                  return (
                    <motion.div
                      key={n.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.04 }}
                      onMouseEnter={() => markRead(n)}
                      className={`card overflow-hidden ${n.read ? "" : "ring-2 ring-sky/20"}`}
                    >
                      <div className={`h-1 ${n.severity === "high" ? "bg-broken" : "bg-risk"}`} />
                      <div className="p-4 space-y-2.5">
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-semibold text-sm leading-5">{n.title}</p>
                          {!n.read && <span className="h-2 w-2 rounded-full bg-sky mt-1.5 shrink-0" />}
                        </div>
                        <p className="text-[13px] text-ink-2">{n.message}</p>
                        <p className="text-[11px] text-ink-3">{n.source} · {timeAgo(n.created_at)}</p>
                        {Object.keys(n.impact).length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {Object.entries(n.impact).map(([nid, st]) => <StatusPill key={nid} status={st} label={`${nid} · ${st.replace("_", " ")}`} />)}
                          </div>
                        )}
                        {n.plans_preview.length > 0 && (
                          <div className="rounded-lg bg-canvas border border-line divide-y divide-line">
                            {n.plans_preview.slice(0, 3).map((p) => (
                              <div key={p.id} className="flex items-center justify-between px-3 py-1.5 text-[12px]">
                                <span className="font-medium">{p.label}</span>
                                <span className="tnum text-ink-2">{inr(p.net_cash, true)} · +{mins(p.lateness_minutes)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {isOpen ? (
                          <div className="flex gap-2 pt-1">
                            <button className="btn-primary h-9 flex-1" disabled={busy !== null} onClick={() => apply(n)}>
                              <Icon name="task_alt" className="!text-[18px]" /> Apply to my trip
                            </button>
                            <button className="btn-secondary h-9" disabled={busy !== null} onClick={() => dismiss(n)}>Dismiss</button>
                          </div>
                        ) : (
                          <p className="text-[11px] font-semibold text-ink-3 uppercase tracking-wide">Handled</p>
                        )}
                      </div>
                    </motion.div>
                  );
                })
              )}
            </div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
