export type NodeStatus = "safe" | "at_risk" | "broken" | "cancelled";
export type NodeType = "flight" | "train" | "hotel" | "transfer" | "activity" | "event";

export interface BookingNode {
  id: string;
  type: NodeType;
  title: string;
  location: string;
  start: string;
  end: string;
  cost: number;
  provider: string;
  cancellation_policy: string;
  status: NodeStatus;
  weather_sensitive: boolean;
  lat?: number | null;
  lon?: number | null;
  dest_lat?: number | null;
  dest_lon?: number | null;
  cancellation_penalty?: number | null;
  refund_mode?: "cash" | "credit" | "none";
  service_code?: string | null;
  alternatives?: Record<string, any>[];
  booking_status?: "confirmed" | "pending_manual_booking" | "dropped";
}

export interface DependencyEdge {
  source: string;
  target: string;
  type: string;
  buffer_minutes: number;
}

export interface Itinerary {
  nodes: BookingNode[];
  edges: DependencyEdge[];
}

export interface RecoveryOption {
  node_id: string;
  replacement_title: string;
  provider: string;
  cost: number;
  start: string;
  end: string;
  notes: string;
  action: "keep" | "reschedule" | "rebook" | "manual_booking" | "drop";
  requires_manual_booking: boolean;
  price_source: string;
  original_cost: number;
  price_vs_original: number;
  market_price: number | null;
  market_price_source: string;
}

export interface ScorePart {
  value: number;
  unit: string;
  normalized: number;
  weight: number;
  contribution: number;
}

export interface PlanMoney {
  penalty: number;
  cash_refund: number;
  credit: number;
  lost: number;
  new_spend: number;
  net_cash: number;
  net_after_credit: number;
}

export interface RecoveryPlan {
  id: string;
  label: string;
  options: RecoveryOption[];
  total_cost_delta: number;
  total_time_delta_minutes: number;
  convenience_score: number;
  pct_itinerary_affected: number;
  refund_recovered: number;
  score: number;
  category: "balanced" | "cheapest" | "fastest" | "alternative";
  badges: string[];
  score_breakdown: Record<"cost" | "time" | "convenience" | "disruption", ScorePart>;
  money: PlanMoney;
  action_items: string[];
}

export interface PlanAnalysis {
  combinations_checked: number;
  feasible: number;
  infeasible_examples: string[];
}

export interface RiskWarning {
  node_id: string;
  title: string;
  message: string;
  severity: "low" | "medium" | "high";
}

export interface Explanation {
  explanation: string;
  source: "llm" | "rule-based";
  model: "nugen-aligned" | "gemini" | "rule-based";
}

export interface AiModelStatus {
  active_tier: "nugen-aligned" | "gemini-or-rule-based";
  nugen_model_id: string | null;
  pipeline: {
    base_model_id?: string;
    base_model_name?: string;
    alignment_id?: string;
    model_id?: string;
    deployment_status?: string;
    dataset_samples?: number;
    benchmark_questions?: number;
    model_name?: string;
    evaluation?: { metrics?: { metric: string; base: number; evaluated: number; [k: string]: any }[] } | null;
    failed_alignments?: string[];
    previous?: Record<string, string>[];
    document_id?: string;
    benchmark_id?: string;
  };
  dataset: { train_samples?: number; benchmark_questions?: number; by_task?: Record<string, number> };
}

export interface TravelerPreferences {
  cost_weight: number;
  time_weight: number;
  convenience_weight: number;
  disruption_weight: number;
  min_rating: number;
  avoid_next_day: boolean;
}

export interface TripSummary {
  id: string;
  name: string;
  updated_at: string;
}

export interface TripStatus {
  trip_id: string | null;
  trip_name: string;
  is_demo: boolean;
  persistence_backend: "supabase" | "in-memory";
  /** every disruption active on the working trip, oldest first */
  disruptions?: { node_id: string | null; kind: string; delay_minutes?: number; reason?: string; date?: string; severity?: string }[];
}

export interface WeatherCheckResult {
  configured: boolean;
  message?: string;
  error?: string;
  found?: boolean;
  location?: string;
  date?: string;
  conditions?: string[];
  max_wind_speed_ms?: number;
  max_rain_mm_h?: number;
  provider?: string;
  severity_suggestion?: "moderate" | "severe" | null;
}

export interface FlightStatusResult {
  configured: boolean;
  message?: string;
  error?: string;
  found?: boolean;
  flight_iata?: string;
  status?: string;
  delay_minutes?: number;
  suggested_action?: "delay" | "cancel" | null;
}

export interface LiveRiskEvent {
  id: string;
  timestamp: number;
  node_id: string;
  node_title: string;
  source_title: string;
  severity: "medium" | "high";
  live_delay_minutes: number;
  buffer_minutes: number;
  message: string;
}

// --- Weather digital twin ---------------------------------------------------------

export interface TwinOverrides {
  rain_mm_h?: number | null;
  storm_hours?: number | null;
  temp_c?: number | null;
  wind_kmh?: number | null;
  flood_index?: number | null;
  social_index?: number | null;
}

export interface TwinScenario {
  overrides: TwinOverrides;
  target_place: string; // "all" or a place name from the twin state
  target_date: string | null;
}

export interface TwinNode {
  id: string;
  title: string;
  type: string;
  places: string[];
  lat: number | null;
  lon: number | null;
  dest_lat: number | null;
  dest_lon: number | null;
  current_status: string;
  p_safe: number;
  p_at_risk: number;
  p_broken: number;
  p_cancelled: number;
  delay_p10: number;
  delay_p50: number;
  delay_p90: number;
  most_likely: string;
  weather: Record<string, number>;
  weather_exposed: boolean;
  p_weather_cancel?: number;
  top_driver?: string | null;
}

export interface Interval {
  mean: number;
  p10: number;
  p90: number;
}

export interface EffectLink {
  order: 0 | 1 | 2 | 3;
  from: string;
  to: string;
  effect: string;
  probability: number;
  driver?: string | null;
}

export interface SocialItem {
  source: string;
  author: string;
  text: string;
  url: string;
  published: string;
  categories: string[];
}

export interface SocialSignals {
  place: string;
  live: boolean;
  window_hours: number;
  social_index: number;
  category_counts: Record<string, number>;
  items: SocialItem[];
}

export interface PlaceInfo {
  lat: number;
  lon: number;
  forecast_live: boolean;
  current: { time: string; temp_c: number; rain_mm_h: number; wind_kmh: number; gust_kmh: number; weather_code: number } | null;
  social: SocialSignals;
}

export interface TwinTrip {
  p_any_disruption: number;
  expected_loss_inr: number;
  expected_extra_minutes: number;
}

export interface TwinSimulation {
  samples: number;
  nodes: Record<string, TwinNode>;
  ecosystem: Record<string, Record<string, Interval>>;
  trip: TwinTrip;
  effect_chain: EffectLink[];
  places: Record<string, PlaceInfo>;
}

export interface LearnerSummary {
  features: string[];
  models: Record<string, { observations: number; coefficients: number[]; coefficient_sd: number[]; noise_sd: number }>;
  recent_observations: {
    at: string;
    entity_type: string;
    source: string;
    observed_delay: number;
    predicted_before: number;
    predicted_after: number;
    node_id?: string;
  }[];
}

export interface TwinState extends TwinSimulation {
  updated_at: string;
  sources: { forecast_points: number; beyond_horizon: number };
  history: { at: string; p_any_disruption: number; expected_loss_inr: number; max_rain_mm_h: number }[];
  learner: LearnerSummary;
}

export interface TwinWhatIf extends TwinSimulation {
  scenario: TwinScenario;
  baseline_trip: TwinTrip;
  delta_vs_live: Record<string, number>;
}

// --- Proactive monitoring ---------------------------------------------------------

export interface ProviderCheck {
  provider: string;
  category: string;
  node_id: string;
  status: "ok" | "skipped" | "unavailable" | "error";
  checked_at: string;
  fresh_until: string;
  fresh?: boolean;
  evidence: Record<string, any>;
}

export interface MonitorEvent {
  id: string;
  node_id: string;
  provider: string;
  category: string;
  kind: "delay" | "cancel";
  delay_minutes?: number;
  severity: string;
  reason: string;
  evidence: Record<string, any>;
  detected_at: string;
  last_seen: string;
  status: "open" | "applied" | "dismissed";
}

export interface MonitorRun {
  at: string;
  trigger: string;
  checks: number;
  by_status: Record<string, number>;
  new_alerts: number;
  suppressed_duplicates: number;
  next_run: string | null;
}

export interface MonitorStatus {
  interval_minutes: number;
  scheduler: string;
  last_run: MonitorRun | null;
  open_events: MonitorEvent[];
  unread: number;
  providers: ProviderCheck[];
}

export interface AlertNotification {
  id: string;
  event_id: string;
  created_at: string;
  severity: string;
  node_id: string;
  title: string;
  message: string;
  source: string;
  evidence: Record<string, any>;
  impact: Record<string, NodeStatus>;
  plans_preview: { id: string; label: string; badges: string[]; score: number; net_cash: number; lateness_minutes: number }[];
  read: boolean;
}

// --- Trip builder -------------------------------------------------------------------

export interface BookingInput {
  id?: string;
  type: NodeType;
  title: string;
  start: string;
  end: string;
  cost: number;
  provider: string;
  location: string;
  destination?: string;
  cancellation_policy: string;
  cancellation_penalty?: number | null;
  refund_mode: "cash" | "credit" | "none";
  service_code?: string | null;
  weather_sensitive: boolean;
  lat?: number | null;
  lon?: number | null;
  dest_lat?: number | null;
  dest_lon?: number | null;
  alternatives?: Record<string, any>[];
}
