import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api, RISK_FEED_WS_URL } from "./api";
import { AppContext, type Disruption, type Screen } from "./context";
import { Icon } from "./ui";
import TripBuilder from "./screens/TripBuilder";
import RecoveryConsole from "./screens/RecoveryConsole";
import DigitalTwin from "./screens/DigitalTwin";
import Monitoring from "./screens/Monitoring";
import AiModelScreen from "./screens/AiModelScreen";
import TripSwitcher from "./shell/TripSwitcher";
import AlertsDrawer from "./shell/AlertsDrawer";
import AuthPage from "./shell/AuthPage";
import { signOut, watchSession, type Account } from "./auth";

const GUEST_KEY = "triprescue.guest";
const readGuest = () => {
  try {
    return sessionStorage.getItem(GUEST_KEY) === "1";
  } catch {
    return false;
  }
};

const TABS: { id: Screen; label: string; icon: string }[] = [
  { id: "builder", label: "Trip Builder", icon: "edit_road" },
  { id: "console", label: "Recovery Console", icon: "hub" },
  { id: "twin", label: "Weather Digital Twin", icon: "radar" },
  { id: "monitor", label: "Monitoring", icon: "monitor_heart" },
  { id: "ai", label: "AI Model", icon: "psychology" },
];
const SCREENS = TABS.map((t) => t.id);

type Toast = { id: number; message: string; tone: "info" | "success" | "warn" | "error" };

export default function App() {
  const fromHash = (): Screen => {
    const h = window.location.hash.replace("#", "") as Screen;
    return SCREENS.includes(h) ? h : "builder";
  };
  const [screen, setScreen] = useState<Screen>(fromHash);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [itineraryVersion, setItineraryVersion] = useState(0);
  const [twinVersion, setTwinVersion] = useState(0);
  const [alertsVersion, setAlertsVersion] = useState(0);
  const [lastDisruption, setLastDisruption] = useState<Disruption>({ disruption: null, impact_report: null });
  const [tripName, setTripName] = useState("My Trip");
  const [isDemo, setIsDemo] = useState(false);
  const [tripOpen, setTripOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [latency, setLatency] = useState<number | null>(null);
  const toastId = useRef(0);
  // optional sign-in: undefined = still checking the stored session
  const [account, setAccount] = useState<Account | null | undefined>(undefined);
  const [guest, setGuest] = useState(readGuest);
  const [accountMenu, setAccountMenu] = useState(false);

  const go = useCallback((s: Screen) => {
    setScreen(s);
    window.history.replaceState(null, "", `#${s}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const toast = useCallback((message: string, tone: Toast["tone"] = "info") => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, message, tone }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4800);
  }, []);

  const refreshTrip = useCallback(() => {
    api.getTripStatus().then((s) => {
      setTripName(s.trip_name);
      setIsDemo(s.is_demo);
      // the backend is the source of truth for what is disrupted (survives a page reload)
      setLastDisruption((cur) => {
        const latest = s.disruptions?.[s.disruptions.length - 1] ?? null;
        if (!latest) return cur.disruption ? { disruption: null, impact_report: null } : cur;
        const same = cur.disruption && cur.disruption.node_id === latest.node_id && cur.disruption.kind === latest.kind;
        return same ? cur : { disruption: latest, impact_report: null };
      });
    }).catch(() => {});
  }, []);

  useEffect(() => {
    let stop = () => {};
    watchSession(setAccount).then((u) => { stop = u; });
    return () => stop();
  }, []);

  const continueAsGuest = () => {
    try { sessionStorage.setItem(GUEST_KEY, "1"); } catch { /* private mode: guest for this view only */ }
    setGuest(true);
  };
  const logOut = async () => {
    setAccountMenu(false);
    await signOut();
    try { sessionStorage.removeItem(GUEST_KEY); } catch { /* ignore */ }
    setGuest(false);
    toast("Signed out", "info");
  };

  const refreshUnread = useCallback(() => {
    api.notifications().then((n) => setUnread(n.unread)).catch(() => {});
  }, []);

  useEffect(() => {
    const onHash = () => setScreen(fromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // backend heartbeat -> "Engine connected · 12 ms"
  useEffect(() => {
    const beat = () => api.ping().then(setLatency).catch(() => setLatency(null));
    beat();
    refreshTrip();
    refreshUnread();
    const t = window.setInterval(beat, 15000);
    return () => window.clearInterval(t);
  }, [refreshTrip, refreshUnread]);

  // one websocket for the whole app: twin refreshes + monitoring alerts
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    const connect = () => {
      ws = new WebSocket(RISK_FEED_WS_URL);
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (data.type === "twin_update") setTwinVersion((v) => v + 1);
          if (data.type === "monitor_alert") {
            setAlertsVersion((v) => v + 1);
            refreshUnread();
            toast(`${data.title}: ${data.message}`, data.severity === "high" ? "error" : "warn");
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        if (!closed) window.setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      closed = true;
      ws?.close();
    };
  }, [toast, refreshUnread]);

  const ctx = useMemo(
    () => ({
      go,
      toast,
      itineraryVersion,
      bumpItinerary: () => setItineraryVersion((v) => v + 1),
      twinVersion,
      alertsVersion,
      lastDisruption,
      setLastDisruption,
      tripName,
      isDemo,
      refreshTrip,
      openTrips: () => setTripOpen(true),
      openAlerts: () => setAlertsOpen(true),
    }),
    [go, toast, itineraryVersion, twinVersion, alertsVersion, lastDisruption, tripName, isDemo, refreshTrip]
  );

  return (
    <AppContext.Provider value={ctx}>
      <div className="min-h-screen flex flex-col bg-gradient-to-b from-canvas via-canvas to-canvas-2">
        {/* ---------- top bar ---------- */}
        <header className="sticky top-0 z-[1000] glass border-b border-line">
          <div className="max-w-[1536px] mx-auto px-4 md:px-8 h-16 flex items-center gap-3">
            <button onClick={() => go("builder")} className="flex items-center gap-2 shrink-0">
              <span className="h-8 w-8 rounded-lg grid place-items-center text-white" style={{ background: "linear-gradient(135deg,#2F80ED,#56CCF2)" }}>
                <Icon name="flight_takeoff" className="!text-[18px]" />
              </span>
              <span className="text-[19px] font-bold tracking-[-0.02em]">
                <span className="text-ink">Trip</span>
                <span className="text-sky">Rescue</span>
              </span>
            </button>

            <button onClick={() => setTripOpen(true)} className="hidden md:inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-white border border-line text-[12px] font-medium text-ink hover:border-sky transition max-w-[220px]">
              <Icon name="alt_route" className="!text-[16px] text-sky" />
              <span className="truncate">{tripName}</span>
              <Icon name="expand_more" className="!text-[16px] text-ink-3" />
            </button>

            <nav className="hidden lg:flex mx-auto p-1 rounded-full bg-canvas-3 border border-line">
              {TABS.map((t) => (
                <button key={t.id} onClick={() => go(t.id)} className={`relative h-9 px-4 rounded-full text-[13px] font-medium transition-colors ${screen === t.id ? "text-ink" : "text-ink-2 hover:text-ink"}`}>
                  {screen === t.id && (
                    <motion.span layoutId="nav-pill" className="absolute inset-0 rounded-full bg-white shadow-[0_2px_6px_rgba(16,42,67,0.08)]" transition={{ type: "spring", stiffness: 380, damping: 30 }} />
                  )}
                  <span className="relative">{t.label}</span>
                </button>
              ))}
            </nav>

            <div className="ml-auto lg:ml-0 flex items-center gap-2">
              <span className={`hidden sm:inline-flex items-center gap-1.5 h-8 px-3 rounded-full border text-[11px] font-semibold tnum ${latency != null ? "bg-white border-line text-ink-2" : "bg-dropped-bg border-line text-dropped-ink"}`}>
                <span className="relative flex h-1.5 w-1.5">
                  {latency != null && <span className="absolute inset-0 rounded-full bg-safe animate-ping opacity-75" />}
                  <span className={`relative h-1.5 w-1.5 rounded-full ${latency != null ? "bg-safe" : "bg-dropped"}`} />
                </span>
                {latency != null ? `Engine connected · ${latency} ms` : "Engine offline"}
              </span>
              {account ? (
                <div className="relative">
                  <button onClick={() => setAccountMenu((o) => !o)} className="h-9 pl-1 pr-2.5 inline-flex items-center gap-1.5 rounded-full bg-white border border-line hover:border-sky transition" aria-label="Account">
                    <span className="h-7 w-7 rounded-full grid place-items-center text-white text-[12px] font-bold" style={{ background: "linear-gradient(135deg,#2F80ED,#56CCF2)" }}>
                      {account.name.slice(0, 1).toUpperCase()}
                    </span>
                    <span className="hidden sm:block text-[12px] font-medium max-w-[110px] truncate">{account.name}</span>
                  </button>
                  <AnimatePresence>
                    {accountMenu && (
                      <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} className="absolute right-0 mt-2 w-60 card shadow-l3 p-3 z-[1001]">
                        <p className="text-sm font-semibold truncate">{account.name}</p>
                        <p className="text-[11px] text-ink-2 truncate">{account.email}</p>
                        <p className="text-[11px] text-ink-3 mt-1">Trips you save are stored in this account.</p>
                        <button className="btn-secondary w-full h-9 mt-3" onClick={logOut}><Icon name="logout" className="!text-[18px]" /> Sign out</button>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              ) : account === null ? (
                <button onClick={() => setGuest(false)} className="h-9 px-3 inline-flex items-center gap-1.5 rounded-full bg-white border border-line text-[12px] font-medium text-sky-ink hover:border-sky transition">
                  <Icon name="login" className="!text-[18px]" /> <span className="hidden sm:inline">Sign in</span>
                </button>
              ) : null}
              <button onClick={() => setAlertsOpen(true)} className="relative h-9 w-9 grid place-items-center rounded-lg bg-white border border-line hover:border-sky transition" aria-label="Alerts">
                <Icon name="notifications" className="!text-[20px] text-ink" />
                <AnimatePresence>
                  {unread > 0 && (
                    <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }} className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-sky text-white text-[10px] font-bold grid place-items-center tnum">
                      {unread}
                    </motion.span>
                  )}
                </AnimatePresence>
              </button>
            </div>
          </div>
        </header>

        {/* ---------- toasts ---------- */}
        <div className="fixed top-20 left-1/2 -translate-x-1/2 z-[1200] flex flex-col gap-2 w-[min(92vw,520px)] pointer-events-none">
          <AnimatePresence>
            {toasts.map((t) => (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, y: -12, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -12 }}
                className={`pointer-events-auto card shadow-l3 px-4 py-3 text-sm flex items-start gap-2 border-l-4 ${
                  { info: "border-l-sky", success: "border-l-safe", warn: "border-l-risk", error: "border-l-broken" }[t.tone]
                }`}
              >
                <Icon name={{ info: "info", success: "check_circle", warn: "warning", error: "report" }[t.tone]} className={{ info: "text-sky", success: "text-safe", warn: "text-risk", error: "text-broken" }[t.tone]} />
                <span className="text-ink">{t.message}</span>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {/* ---------- screen ---------- */}
        <main className="flex-1 w-full max-w-[1536px] mx-auto px-4 md:px-8 pt-6 pb-28 lg:pb-10">
          {/* keyed fade-in on mount (no exit animation: exits under mode="wait" can stall and blank the screen) */}
          <motion.div key={screen} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25, ease: "easeOut" }}>
            {screen === "builder" && <TripBuilder />}
            {screen === "console" && <RecoveryConsole />}
            {screen === "twin" && <DigitalTwin />}
            {screen === "monitor" && <Monitoring />}
            {screen === "ai" && <AiModelScreen />}
          </motion.div>
        </main>

        <footer className="hidden lg:block border-t border-line bg-white/60">
          <div className="max-w-[1536px] mx-auto px-8 h-12 flex items-center justify-between text-[11px] text-ink-2">
            <span>TripRescue · advisory only: never books, cancels or charges on your behalf</span>
            <span className="flex gap-5">
              <span>Live data: Open-Meteo · AviationStack · Mastodon · Google News</span>
              <span>DGCA CAR Sec 3 Ser M Pt IV</span>
            </span>
          </div>
        </footer>

        {/* ---------- mobile bottom nav ---------- */}
        <nav className="lg:hidden fixed bottom-0 inset-x-0 z-[1000] glass border-t border-line grid grid-cols-5 pb-[env(safe-area-inset-bottom)]">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => go(t.id)} className={`flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium ${screen === t.id ? "text-sky-ink" : "text-ink-3"}`}>
              <Icon name={t.icon} fill={screen === t.id} className="!text-[22px]" />
              {t.label.split(" ")[0]}
            </button>
          ))}
        </nav>

        <AnimatePresence>
          {account === null && !guest && (
            <motion.div key="auth" initial={{ opacity: 1 }} exit={{ opacity: 0, scale: 1.02 }} transition={{ duration: 0.3 }} className="fixed inset-0 z-[1300]">
              <AuthPage onDone={(msg) => { toast(msg, "success"); refreshTrip(); setItineraryVersion((v) => v + 1); }} onGuest={continueAsGuest} />
            </motion.div>
          )}
        </AnimatePresence>

        <TripSwitcher account={account ?? null} open={tripOpen} onClose={() => setTripOpen(false)} />
        <AlertsDrawer open={alertsOpen} onClose={() => { setAlertsOpen(false); refreshUnread(); }} onUnread={setUnread} />
      </div>
    </AppContext.Provider>
  );
}
