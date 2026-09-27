export const pct = (x: number) => `${Math.round(x * 100)}%`;

export function riskColor(risk: number): string {
  if (risk >= 0.66) return "#ef4444";
  if (risk >= 0.33) return "#f59e0b";
  if (risk >= 0.15) return "#eab308";
  return "#22c55e";
}

export const DRIVER_LABEL: Record<string, string> = {
  rain_mm_h: "rain",
  wind_10kmh: "wind",
  heat_over_35c: "heat",
  flood_index: "flooding",
  storm_6h: "storm duration",
  social_index: "social reports",
};

export const METRIC_LABEL: Record<string, { label: string; kind: "ratio" | "multiplier"; goodHigh: boolean }> = {
  road_travel_time_x: { label: "Road travel time", kind: "multiplier", goodHigh: false },
  cab_availability: { label: "Cab availability", kind: "ratio", goodHigh: true },
  hotel_occupancy: { label: "Hotel occupancy", kind: "ratio", goodHigh: false },
  outdoor_attraction_demand: { label: "Outdoor attraction demand", kind: "ratio", goodHigh: true },
  indoor_venue_demand: { label: "Indoor venue demand", kind: "multiplier", goodHigh: false },
  dine_in_restaurant_demand: { label: "Dine-in restaurant demand", kind: "ratio", goodHigh: true },
  workforce_availability: { label: "Hospitality workforce", kind: "ratio", goodHigh: true },
};

export function fmtMetric(value: number, kind: "ratio" | "multiplier"): string {
  return kind === "ratio" ? pct(value) : `×${value.toFixed(2)}`;
}

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
