import type { AiModelStatus,
  AlertNotification,
  BookingInput,
  MonitorEvent,
  MonitorRun,
  MonitorStatus,
  PlanAnalysis,
  LearnerSummary,
  TwinScenario,
  TwinState,
  TwinTrip,
  TwinWhatIf,
  Explanation,
  FlightStatusResult,
  Itinerary,
  LiveRiskEvent,
  RecoveryPlan,
  RiskWarning,
  TravelerPreferences,
  TripStatus,
  TripSummary,
  WeatherCheckResult,
} from "./types";

// Set VITE_API_BASE_URL (e.g. "https://your-backend.onrender.com") when deploying;
// defaults to localhost for local dev. WS URL is derived from the same host.
const API_ROOT = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const BASE_URL = `${API_ROOT}/api`;
export const RISK_FEED_WS_URL = `${API_ROOT.replace(/^http/, "ws")}/ws/risk-feed`;

// Signed-in account (optional). Trip save/list/load calls carry its access token; the
// backend verifies it with Supabase and scopes trips to that account. No token = guest.
let accessToken: string | null = null;
export const setAccessToken = (t: string | null) => { accessToken = t; };
const auth = (extra: Record<string, string> = {}): Record<string, string> =>
  accessToken ? { ...extra, Authorization: `Bearer ${accessToken}` } : extra;

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  getItinerary: (): Promise<Itinerary> =>
    fetch(`${BASE_URL}/itinerary`).then((r) => handle(r)),

  loadDemo: (): Promise<Itinerary> => fetch(`${BASE_URL}/demo`, { method: "POST" }).then((r) => handle(r)),

  reset: (): Promise<Itinerary> =>
    fetch(`${BASE_URL}/reset`, { method: "POST" }).then((r) => handle(r)),

  disrupt: (nodeId: string, kind: "delay" | "cancel", delayMinutes: number, reason: string) =>
    fetch(`${BASE_URL}/disrupt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: nodeId, kind, delay_minutes: delayMinutes, reason }),
    }).then((r) => handle<{ itinerary: Itinerary; impact_report: any; disruption: any }>(r)),

  disruptWeather: (date: string, severity: "moderate" | "severe") =>
    fetch(`${BASE_URL}/disrupt-weather`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date, severity }),
    }).then((r) =>
      handle<{ itinerary: Itinerary; impact_report: any; disruption: any; weather_origins: any[] }>(r)
    ),

  // dependencies omitted -> the backend infers them from the timeline
  setItinerary: (
    name: string,
    bookings: BookingInput[],
    dependencies?: { source: string; target: string; type?: string; buffer_minutes?: number }[],
    updateTripId?: string | null // set = overwrite that saved trip; omitted = save as a new trip
  ): Promise<{ itinerary: Itinerary; trip_name: string; trip_id: string }> =>
    fetch(`${BASE_URL}/itinerary`, {
      method: "POST",
      headers: auth({ "Content-Type": "application/json" }),
      body: JSON.stringify({ name, bookings, dependencies, geocode: true, update_trip_id: updateTripId ?? null }),
    }).then((r) => handle(r)),

  getRecoveryPlans: (): Promise<{ plans: RecoveryPlan[]; analysis: PlanAnalysis }> =>
    fetch(`${BASE_URL}/recovery-plans`).then((r) => handle(r)),

  applyPlan: (planId: string) =>
    fetch(`${BASE_URL}/apply-plan/${planId}`, { method: "POST" }).then((r) =>
      handle<{ itinerary: Itinerary; applied_plan: RecoveryPlan }>(r)
    ),

  riskScan: (): Promise<{ warnings: RiskWarning[] }> =>
    fetch(`${BASE_URL}/risk-scan`).then((r) => handle(r)),

  explainImpact: (): Promise<Explanation> =>
    fetch(`${BASE_URL}/explain-impact`).then((r) => handle(r)),

  explainPlans: (): Promise<Explanation> =>
    fetch(`${BASE_URL}/explain-plans`).then((r) => handle(r)),

  travelerRights: (): Promise<Explanation> =>
    fetch(`${BASE_URL}/traveler-rights`).then((r) => handle(r)),

  aiModel: (): Promise<AiModelStatus> =>
    fetch(`${BASE_URL}/ai-model`).then((r) => handle(r)),

  // --- weather digital twin ---
  twinState: (refresh = false): Promise<TwinState> =>
    fetch(`${BASE_URL}/twin/state?refresh=${refresh}`).then((r) => handle(r)),

  twinSimulate: (scenario: TwinScenario): Promise<TwinWhatIf> =>
    fetch(`${BASE_URL}/twin/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scenario),
    }).then((r) => handle(r)),

  twinExplain: (scenario: TwinScenario | null): Promise<Explanation> =>
    fetch(`${BASE_URL}/twin/explain`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scenario),
    }).then((r) => handle(r)),

  twinObserve: (nodeId: string, delayMinutes: number) =>
    fetch(`${BASE_URL}/twin/observe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: nodeId, delay_minutes: delayMinutes }),
    }).then((r) =>
      handle<{ observation: LearnerSummary["recent_observations"][number]; learner: LearnerSummary; trip: TwinTrip }>(r)
    ),

  twinPromote: (scenario: TwinScenario) =>
    fetch(`${BASE_URL}/twin/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scenario),
    }).then((r) => handle<{ itinerary: Itinerary; origins: any[] }>(r)),

  twinPlanRisk: (): Promise<{ plans: Record<string, { p_success: number; risks: string[] }> }> =>
    fetch(`${BASE_URL}/twin/plan-risk`).then((r) => handle(r)),

  getRiskFeed: (): Promise<{ events: LiveRiskEvent[] }> =>
    fetch(`${BASE_URL}/risk-feed`).then((r) => handle(r)),

  getPreferences: (): Promise<TravelerPreferences> =>
    fetch(`${BASE_URL}/preferences`).then((r) => handle(r)),

  setPreferences: (prefs: TravelerPreferences): Promise<TravelerPreferences> =>
    fetch(`${BASE_URL}/preferences`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prefs),
    }).then((r) => handle(r)),

  getTripStatus: (): Promise<TripStatus> =>
    fetch(`${BASE_URL}/trip-status`).then((r) => handle(r)),

  listTrips: (): Promise<{ trips: TripSummary[] }> =>
    fetch(`${BASE_URL}/trips`, { headers: auth() }).then((r) => handle(r)),

  createTrip: (name: string) =>
    fetch(`${BASE_URL}/trips`, {
      method: "POST",
      headers: auth({ "Content-Type": "application/json" }),
      body: JSON.stringify({ name }),
    }).then((r) => handle<TripSummary & { itinerary: Itinerary }>(r)),

  saveTrip: (tripId: string) =>
    fetch(`${BASE_URL}/trips/${tripId}/save`, { method: "POST", headers: auth() }).then((r) => handle(r)),

  loadTrip: (tripId: string) =>
    fetch(`${BASE_URL}/trips/${tripId}/load`, { method: "POST", headers: auth() }).then((r) =>
      handle<{ itinerary: Itinerary; preferences: TravelerPreferences; trip: { id: string; name: string } }>(r)
    ),

  deleteTrip: (tripId: string) =>
    fetch(`${BASE_URL}/trips/${tripId}`, { method: "DELETE", headers: auth() }).then((r) => handle(r)),

  checkWeather: (location: string, date: string): Promise<WeatherCheckResult> =>
    fetch(`${BASE_URL}/weather-check?${new URLSearchParams({ location, date })}`).then((r) => handle(r)),

  checkFlightStatus: (flightIata: string): Promise<FlightStatusResult> =>
    fetch(`${BASE_URL}/flight-status?${new URLSearchParams({ flight_iata: flightIata })}`).then((r) =>
      handle(r)
    ),

  // --- proactive monitoring ---
  monitorStatus: (): Promise<MonitorStatus> => fetch(`${BASE_URL}/monitor/status`).then((r) => handle(r)),

  monitorRun: (now?: string): Promise<MonitorRun & { notifications: AlertNotification[] }> =>
    fetch(`${BASE_URL}/monitor/run${now ? `?now=${encodeURIComponent(now)}` : ""}`, { method: "POST" }).then((r) => handle(r)),

  notifications: (): Promise<{ notifications: AlertNotification[]; unread: number }> =>
    fetch(`${BASE_URL}/notifications`).then((r) => handle(r)),

  markRead: (id: string) => fetch(`${BASE_URL}/notifications/${id}/read`, { method: "POST" }).then((r) => handle(r)),

  applyEvent: (eventId: string): Promise<{ itinerary: Itinerary; impact_report: any; plans: RecoveryPlan[] }> =>
    fetch(`${BASE_URL}/monitor/events/${eventId}/apply`, { method: "POST" }).then((r) => handle(r)),

  dismissEvent: (eventId: string): Promise<{ dismissed: string }> =>
    fetch(`${BASE_URL}/monitor/events/${eventId}/dismiss`, { method: "POST" }).then((r) => handle(r)),

  authConfig: (): Promise<{ enabled: boolean; url: string; key: string }> =>
    fetch(`${BASE_URL}/auth-config`).then((r) => handle(r)),

  ping: async (): Promise<number> => {
    const t = performance.now();
    const r = await fetch(`${BASE_URL}/trip-status`);
    if (!r.ok) throw new Error("offline");
    return Math.round(performance.now() - t);
  },
};
