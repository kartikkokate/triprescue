// Shared building blocks for the light-sky ("AeroRescue") design system.
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import type { Explanation, NodeStatus, NodeType } from "./types";

export function Icon({ name, className = "", fill = false }: { name: string; className?: string; fill?: boolean }) {
  return <span className={`material-symbols-outlined ${fill ? "icon-fill" : ""} ${className}`} aria-hidden>{name}</span>;
}

export const TYPE_ICON: Record<NodeType | string, string> = {
  flight: "flight",
  train: "train",
  transfer: "local_taxi",
  hotel: "hotel",
  activity: "beach_access",
  event: "event",
};

export const TYPE_TINT: Record<string, string> = {
  flight: "bg-sky-ink text-white",
  train: "bg-red-600 text-white",
  transfer: "bg-teal-600 text-white",
  hotel: "bg-cyan-700 text-white",
  activity: "bg-amber-500 text-white",
  event: "bg-violet-600 text-white",
};

// --- formatting ------------------------------------------------------------------------

export const inr = (n: number, signed = false) => {
  const abs = Math.abs(Math.round(n)).toLocaleString("en-IN");
  if (!signed) return `₹${abs}`;
  return n > 0 ? `+₹${abs}` : n < 0 ? `−₹${abs}` : "₹0";
};
export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const hhmm = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
export const dayShort = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
export const dayTime = (iso: string) => `${dayShort(iso)}, ${hhmm(iso)}`;
export const mins = (m: number) => (m >= 120 ? `${Math.floor(m / 60)}h ${Math.round(m % 60)}m` : `${Math.round(m)} min`);

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

// --- status ----------------------------------------------------------------------------

type AnyStatus = NodeStatus | "pending_manual_booking" | "dropped" | "confirmed";

const STATUS: Record<string, { label: string; dot: string; bg: string; text: string }> = {
  safe: { label: "Safe", dot: "bg-safe", bg: "bg-safe-bg", text: "text-safe-ink" },
  confirmed: { label: "Confirmed", dot: "bg-safe", bg: "bg-safe-bg", text: "text-safe-ink" },
  at_risk: { label: "At risk", dot: "bg-risk", bg: "bg-risk-bg", text: "text-risk-ink" },
  broken: { label: "Broken", dot: "bg-broken", bg: "bg-broken-bg", text: "text-broken-ink" },
  cancelled: { label: "Cancelled", dot: "bg-cancel", bg: "bg-cancel-bg", text: "text-cancel-ink" },
  pending_manual_booking: { label: "Book yourself", dot: "bg-pending", bg: "bg-pending-bg", text: "text-pending-ink" },
  dropped: { label: "Dropped", dot: "bg-dropped", bg: "bg-dropped-bg", text: "text-dropped-ink" },
};

export function StatusPill({ status, label }: { status: AnyStatus | string; label?: string }) {
  const s = STATUS[status] ?? STATUS.dropped;
  return (
    <span className={`inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full text-[10px] font-semibold uppercase tracking-[0.04em] whitespace-nowrap ${s.bg} ${s.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {label ?? s.label}
    </span>
  );
}

export function Chip({ children, tone = "sky", className = "" }: { children: ReactNode; tone?: "sky" | "slate" | "safe" | "risk" | "broken" | "pending"; className?: string }) {
  const tones = {
    sky: "bg-icy text-sky-ink",
    slate: "bg-canvas-3 text-ink-2",
    safe: "bg-safe-bg text-safe-ink",
    risk: "bg-risk-bg text-risk-ink",
    broken: "bg-broken-bg text-broken-ink",
    pending: "bg-pending-bg text-pending-ink",
  };
  return <span className={`inline-flex items-center gap-1 h-6 px-2.5 rounded-full text-[11px] font-semibold ${tones[tone]} ${className}`}>{children}</span>;
}

export function ModelBadge({ model }: { model: Explanation["model"] }) {
  const m = {
    "nugen-aligned": { label: "TripRescue Advisor · Nugen-aligned", cls: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200", icon: "verified" },
    gemini: { label: "Gemini (fallback)", cls: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: "auto_awesome" },
    "rule-based": { label: "Rule-based fallback", cls: "bg-slate-50 text-slate-600 border-slate-200", icon: "rule" },
  }[model] ?? { label: model, cls: "bg-slate-50 text-slate-600 border-slate-200", icon: "rule" };
  return (
    <span className={`inline-flex items-center gap-1 h-6 px-2 rounded-full border text-[10px] font-semibold ${m.cls}`}>
      <Icon name={m.icon} className="!text-[14px]" />
      {m.label}
    </span>
  );
}

export function Money({ value, signed = true, className = "" }: { value: number; signed?: boolean; className?: string }) {
  const color = !signed || value === 0 ? "text-ink" : value > 0 ? "text-broken" : "text-safe";
  return <span className={`tnum ${color} ${className}`}>{inr(value, signed)}</span>;
}

// --- layout ----------------------------------------------------------------------------

export function Card({ children, className = "", delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay, ease: "easeOut" }}
      className={`card ${className}`}
    >
      {children}
    </motion.section>
  );
}

export function CardHeader({ icon, title, sub, right }: { icon?: string; title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 mb-4">
      <div className="flex items-start gap-2.5 min-w-0">
        {icon && <Icon name={icon} className="text-sky mt-0.5 !text-[20px]" />}
        <div className="min-w-0">
          <h3 className="text-[16px] leading-6 font-semibold text-ink tracking-[-0.005em]">{title}</h3>
          {sub && <p className="text-[12px] text-ink-2 mt-0.5">{sub}</p>}
        </div>
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, size = "md" }: {
  value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex p-1 rounded-full bg-canvas-3 border border-line gap-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`relative rounded-full font-medium transition-colors ${size === "sm" ? "h-7 px-3 text-[12px]" : "h-8 px-3.5 text-[13px]"} ${
            value === o.value ? "text-ink" : "text-ink-2 hover:text-ink"
          }`}
        >
          {value === o.value && (
            <motion.span layoutId={`seg-${options.map((x) => x.value).join("-")}`} className="absolute inset-0 rounded-full bg-white shadow-[0_2px_6px_rgba(16,42,67,0.08)]" transition={{ type: "spring", stiffness: 420, damping: 32 }} />
          )}
          <span className="relative">{o.label}</span>
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-lg bg-canvas-3 ${className}`}>
      <motion.div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/70 to-transparent" initial={{ x: "-100%" }} animate={{ x: "100%" }} transition={{ repeat: Infinity, duration: 1.3, ease: "linear" }} />
    </div>
  );
}

export function EmptyState({ icon, title, body, action }: { icon: string; title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center py-8 px-4">
      <div className="h-12 w-12 rounded-full bg-icy grid place-items-center mb-3">
        <Icon name={icon} className="text-sky" />
      </div>
      <p className="font-semibold text-ink">{title}</p>
      {body && <p className="text-sm text-ink-2 mt-1 max-w-sm">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-broken-bg px-4 py-2.5 text-sm text-broken-ink">
      <span className="flex items-center gap-2"><Icon name="error" className="!text-[18px]" />{message}</span>
      {onRetry && <button onClick={onRetry} className="font-semibold underline underline-offset-2">Retry</button>}
    </motion.div>
  );
}

export function ProgressBar({ value, tone = "sky" }: { value: number; tone?: "sky" | "safe" | "risk" | "broken" }) {
  const bg = { sky: "bg-gradient-to-r from-sky-deep to-sky-light", safe: "bg-safe", risk: "bg-risk", broken: "bg-broken" }[tone];
  return (
    <div className="h-1.5 rounded-full bg-canvas-3 overflow-hidden">
      <motion.div className={`h-full rounded-full ${bg}`} initial={{ width: 0 }} animate={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} transition={{ duration: 0.7, ease: "easeOut" }} />
    </div>
  );
}

export function riskTone(p: number): "safe" | "risk" | "broken" {
  return p >= 0.6 ? "broken" : p >= 0.25 ? "risk" : "safe";
}
