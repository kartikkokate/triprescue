import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../api";
import { useApp } from "../context";
import type { TripStatus, TripSummary } from "../types";
import type { Account } from "../auth";
import { EmptyState, ErrorBanner, Icon, Skeleton, timeAgo } from "../ui";

export default function TripSwitcher({ open, onClose, account }: { open: boolean; onClose: () => void; account: Account | null }) {
  const app = useApp();
  const [status, setStatus] = useState<TripStatus | null>(null);
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    Promise.all([api.getTripStatus(), api.listTrips()])
      .then(([s, t]) => {
        setStatus(s);
        setTrips(t.trips);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    if (open) load();
  }, [open, account?.id]);

  const run = async (key: string, fn: () => Promise<unknown>, done: string) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
      app.toast(done, "success");
      app.refreshTrip();
      app.bumpItinerary();
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[1100] grid place-items-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-ink/20 backdrop-blur-sm" onClick={onClose} />
          <motion.div initial={{ y: 20, scale: 0.97 }} animate={{ y: 0, scale: 1 }} exit={{ y: 12, scale: 0.97 }} className="relative w-full max-w-lg card shadow-l3 p-5">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold">Your trips</h3>
                <p className="text-xs text-ink-2 mt-0.5 flex items-center gap-1">
                  <Icon name={status?.persistence_backend === "supabase" ? "cloud_done" : "memory"} className="!text-[15px] text-sky" />
                  Stored in: {status ? (status.persistence_backend === "supabase" ? "Cloud (Supabase)" : "In memory (resets on restart)") : "…"}
                </p>
                <p className="text-[11px] text-ink-3 mt-0.5 flex items-center gap-1">
                  <Icon name={account ? "person" : "person_off"} className="!text-[14px]" />
                  {account ? `Showing trips saved to ${account.email}` : "Guest: showing trips saved without an account"}
                </p>
              </div>
              <button onClick={onClose} className="h-8 w-8 grid place-items-center rounded-lg hover:bg-canvas" aria-label="Close">
                <Icon name="close" />
              </button>
            </div>

            {error && <div className="mb-3"><ErrorBanner message={error} onRetry={load} /></div>}

            <div className="flex gap-2 mb-2">
              <input className="input" placeholder={status?.is_demo ? "Name a copy of the demo" : "Save the current trip under a new name"} value={name} onChange={(e) => setName(e.target.value)} />
              <button
                className="btn-primary shrink-0"
                disabled={!name.trim() || busy !== null}
                onClick={() => run("create", () => api.createTrip(name.trim()), `Saved "${name.trim()}"`).then(() => setName(""))}
              >
                <Icon name="save" className="!text-[18px]" /> Save as new
              </button>
            </div>
            <button className="btn-ghost mb-1" disabled={busy !== null} onClick={() => run("demo", () => api.loadDemo(), "Demo trip loaded")}>
              <Icon name="travel_explore" className="!text-[18px]" /> Load the demo trip (Delhi → Goa)
            </button>
            {status?.trip_id && !status.is_demo && (
              <button className="btn-ghost mb-3" disabled={busy !== null} onClick={() => run("save", () => api.saveTrip(status.trip_id!), `Updated "${status.trip_name}"`)}>
                <Icon name="sync" className="!text-[18px]" /> Update "{status.trip_name}" with current changes
              </button>
            )}

            <div className="border-t border-line pt-3 max-h-80 overflow-y-auto space-y-1.5">
              {trips === null ? (
                [0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)
              ) : trips.length === 0 ? (
                <EmptyState icon="luggage" title="No saved trips yet" body="Save the current itinerary to come back to it later." />
              ) : (
                trips.map((t) => (
                  <div key={t.id} className={`flex items-center justify-between gap-2 rounded-xl px-3 py-2.5 border ${status?.trip_id === t.id ? "border-sky bg-icy/50" : "border-line bg-well"}`}>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {t.name} {status?.trip_id === t.id && <span className="text-[10px] font-semibold text-sky-ink ml-1">ACTIVE</span>}
                      </p>
                      <p className="text-[11px] text-ink-3">updated {timeAgo(t.updated_at)}</p>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <button className="btn-ghost" disabled={busy !== null} onClick={() => run(`load-${t.id}`, () => api.loadTrip(t.id), `Loaded "${t.name}"`)}>
                        Load
                      </button>
                      {confirmDelete === t.id ? (
                        <button className="btn-danger h-8 px-2.5" onClick={() => { setConfirmDelete(null); run(`del-${t.id}`, () => api.deleteTrip(t.id), `Deleted "${t.name}"`); }}>
                          Confirm
                        </button>
                      ) : (
                        <button className="btn-ghost text-broken hover:bg-broken-bg" onClick={() => setConfirmDelete(t.id)}>
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
