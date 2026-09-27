import { createContext, useContext } from "react";

export type Screen = "builder" | "console" | "twin" | "monitor" | "ai";

export interface Disruption {
  disruption: Record<string, any> | null;
  impact_report: Record<string, { overrun_minutes: number | null; new_start: string | null; new_end: string | null }> | null;
}

export interface AppCtx {
  go: (screen: Screen) => void;
  toast: (message: string, tone?: "info" | "success" | "warn" | "error") => void;
  // bump counters: screens re-fetch when these change
  itineraryVersion: number;
  bumpItinerary: () => void;
  twinVersion: number;
  alertsVersion: number;
  // the latest disruption applied in this session (impact report drives buffer deficits)
  lastDisruption: Disruption;
  setLastDisruption: (d: Disruption) => void;
  tripName: string;
  isDemo: boolean;
  refreshTrip: () => void;
  openTrips: () => void;
  openAlerts: () => void;
}

export const AppContext = createContext<AppCtx>(null as unknown as AppCtx);
export const useApp = () => useContext(AppContext);
