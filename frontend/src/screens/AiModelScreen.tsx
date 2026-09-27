import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../api";
import { useApp } from "../context";
import type { AiModelStatus, Explanation } from "../types";
import { Card, CardHeader, Chip, ErrorBanner, Icon, ModelBadge, Skeleton } from "../ui";

const TASK_INFO: Record<string, { label: string; color: string; where: string; icon: string }> = {
  EXPLAIN_IMPACT: { label: "Impact explanation", color: "from-sky-deep to-sky-light", where: "Recovery Console → Explain what happened", icon: "psychology" },
  TRAVELER_RIGHTS: { label: "Traveler rights (DGCA / rail / policy)", color: "from-emerald-500 to-emerald-300", where: "Recovery Console → Know your rights", icon: "gavel" },
  RECOMMEND_PLAN: { label: "Plan recommendation", color: "from-indigo-500 to-indigo-300", where: "Recovery Console → Explain recovery plans", icon: "alt_route" },
  WEATHER_TWIN: { label: "Weather digital-twin briefing", color: "from-fuchsia-500 to-fuchsia-300", where: "Weather Digital Twin → Brief me", icon: "radar" },
  POLICY_QA: { label: "Travel policy knowledge", color: "from-amber-500 to-amber-300", where: "every advisor answer", icon: "menu_book" },
};

type StepState = "done" | "active" | "pending" | "failed";
const STEP_STYLE: Record<StepState, { ring: string; chip: string; label: string; icon: string }> = {
  done: { ring: "border-safe", chip: "bg-safe-bg text-safe-ink", label: "Complete", icon: "check_circle" },
  active: { ring: "border-risk", chip: "bg-risk-bg text-risk-ink", label: "In progress", icon: "pending" },
  pending: { ring: "border-line", chip: "bg-canvas-3 text-ink-2", label: "Pending", icon: "radio_button_unchecked" },
  failed: { ring: "border-broken", chip: "bg-broken-bg text-broken-ink", label: "Failed at provider", icon: "error" },
};

export default function AiModelScreen() {
  const app = useApp();
  const [status, setStatus] = useState<AiModelStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sample, setSample] = useState<Explanation | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    api.aiModel().then(setStatus).catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorBanner message={error} />;
  if (!status) return <div className="space-y-4"><Skeleton className="h-44" /><div className="grid grid-cols-1 md:grid-cols-2 gap-4"><Skeleton className="h-64" /><Skeleton className="h-64" /></div></div>;

  const p = status.pipeline;
  const ds = status.dataset;
  const deployed = status.active_tier === "nugen-aligned";
  // every alignment job this account has submitted that did not produce a model
  const failedIds = Array.from(new Set([
    ...(p.failed_alignments ?? []),
    ...(p.previous ?? []).map((x) => x.alignment_id).filter(Boolean),
    ...(p.alignment_id && !p.model_id ? [p.alignment_id] : []),
  ]));
  const failed = (p.failed_alignments?.length ?? 0) > 0 && !p.model_id;
  const steps: { title: string; detail: string; state: StepState; icon: string }[] = [
    { title: "Base model", detail: p.base_model_name || p.base_model_id || "llama-v3p2-3b-reasoning", state: p.base_model_id ? "done" : "active", icon: "memory" },
    { title: "TripRescue dataset", detail: ds.train_samples ? `${ds.train_samples} samples · ${ds.benchmark_questions} held-out` : "build the dataset", state: ds.train_samples ? "done" : "active", icon: "dataset" },
    { title: "Nugen alignment", detail: p.alignment_id ?? "not started", state: p.model_id ? "done" : failed ? "failed" : p.alignment_id ? "active" : "pending", icon: "model_training" },
    { title: "Domain-specific model", detail: p.model_id ?? "waiting for alignment", state: deployed ? "done" : p.model_id ? "active" : "pending", icon: "verified" },
    { title: "Integrated in TripRescue", detail: deployed ? "serving advisor answers" : "Gemini → rule-based until deployed", state: deployed ? "done" : "pending", icon: "hub" },
  ];
  const tasks = Object.entries(ds.by_task ?? {}).sort((a, b) => b[1] - a[1]);
  const maxTask = Math.max(1, ...tasks.map(([, n]) => n));

  return (
    <div className="space-y-5">
      <div>
        <Chip><Icon name="psychology" className="!text-[14px]" /> NUGEN INTELLIGENCE · TASK 2</Chip>
        <h1 className="text-[28px] md:text-[32px] font-bold tracking-[-0.02em] mt-2">TripRescue Advisor: model provenance</h1>
        <p className="text-[13px] text-ink-2 mt-1">Base AI model → Nugen alignment/customization → domain-specific model → integration into this app.</p>
      </div>

      <Card className="p-5">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {steps.map((s, i) => (
            <div key={s.title} className="relative">
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.12, type: "spring", stiffness: 220, damping: 22 }} className={`relative h-full rounded-xl border-2 ${STEP_STYLE[s.state].ring} bg-well p-3.5`}>
                {s.state === "active" && <motion.span className="absolute inset-0 rounded-xl border-2 border-risk" animate={{ opacity: [0.15, 0.8, 0.15] }} transition={{ repeat: Infinity, duration: 1.8 }} />}
                <div className="flex items-center justify-between mb-2">
                  <span className="h-8 w-8 rounded-lg bg-icy grid place-items-center"><Icon name={s.icon} className="!text-[18px] text-sky-ink" /></span>
                  <span className="text-[10px] font-semibold text-ink-3">STEP {i + 1}</span>
                </div>
                <p className="text-[14px] font-semibold">{s.title}</p>
                <p className="text-[11px] text-ink-2 break-all mt-0.5 min-h-[30px]">{s.detail}</p>
                <span className={`inline-flex items-center gap-1 h-6 px-2 mt-2 rounded-full text-[10px] font-semibold ${STEP_STYLE[s.state].chip}`}>
                  <Icon name={STEP_STYLE[s.state].icon} className="!text-[12px]" /> {STEP_STYLE[s.state].label}
                </span>
              </motion.div>
              {i < steps.length - 1 && (
                <motion.span className="hidden md:block absolute top-1/2 -right-3 z-10 -translate-y-1/2 text-sky" animate={{ x: [0, 3, 0] }} transition={{ repeat: Infinity, duration: 1.4, delay: i * 0.2 }}>
                  <Icon name="chevron_right" className="!text-[20px]" />
                </motion.span>
              )}
            </div>
          ))}
        </div>
        {failed && (
          <div className="mt-4 rounded-xl bg-broken-bg border border-red-200 p-3 text-[12px] text-broken-ink">
            <p className="font-semibold flex items-center gap-1"><Icon name="report" className="!text-[16px]" /> Nugen's training service rejected the alignment job (HTTP 502 at job creation). Dataset and benchmark uploads succeeded.</p>
            <p className="mt-1 tnum">Job IDs for the Nugen team: {failedIds.join(" · ")}</p>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 items-start">
        <Card className="p-5" delay={0.1}>
          <CardHeader icon="dataset" title="What the model was aligned on" sub="Every sample pairs the exact prompt the app sends with an answer computed by our own impact, recovery and digital-twin engines." />
          <div className="space-y-3">
            {tasks.map(([task, n], i) => (
              <div key={task}>
                <div className="flex justify-between text-[13px] mb-1">
                  <span className="flex items-center gap-1.5"><Icon name={TASK_INFO[task]?.icon ?? "label"} className="!text-[16px] text-sky" />{TASK_INFO[task]?.label ?? task}</span>
                  <span className="tnum font-semibold">{n}</span>
                </div>
                <div className="h-2 rounded-full bg-canvas-3 overflow-hidden">
                  <motion.div className={`h-full rounded-full bg-gradient-to-r ${TASK_INFO[task]?.color ?? "from-slate-400 to-slate-300"}`} initial={{ width: 0 }} animate={{ width: `${(n / maxTask) * 100}%` }} transition={{ delay: 0.2 + i * 0.1, duration: 0.7, ease: "easeOut" }} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5" delay={0.15}>
          <CardHeader icon="hub" title="Where it runs in the app" />
          <div className="space-y-2">
            {Object.entries(TASK_INFO).filter(([k]) => k !== "POLICY_QA").map(([k, t], i) => (
              <motion.div key={k} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.08 * i }} className="flex items-center gap-3 rounded-xl border border-line bg-well px-3 py-2">
                <Icon name={t.icon} className="!text-[18px] text-sky" />
                <div className="min-w-0">
                  <p className="text-[13px] font-medium">{t.label}</p>
                  <p className="text-[11px] text-ink-2">{t.where}</p>
                </div>
              </motion.div>
            ))}
          </div>
          <div className="border-t border-line mt-4 pt-4 space-y-3">
            <button className="btn-primary" disabled={testing} onClick={async () => {
              setTesting(true);
              try { setSample(await api.twinExplain(null)); } catch (e: any) { app.toast(e.message, "error"); } finally { setTesting(false); }
            }}>
              <Icon name="play_arrow" className="!text-[18px]" /> {testing ? "Asking the advisor…" : "Test it on the live twin"}
            </button>
            <AnimatePresence>
              {sample && (
                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl bg-canvas border border-line p-3 space-y-2">
                  <ModelBadge model={sample.model} />
                  <p className="text-[13px] leading-6">{sample.explanation}</p>
                </motion.div>
              )}
            </AnimatePresence>
            <p className="text-[11px] text-ink-2 flex gap-1.5"><Icon name="info" className="!text-[15px]" /> If the aligned model is unreachable, answers fall back to Gemini, then to rule-based text. Every answer shows which one replied.</p>
          </div>
        </Card>
      </div>

      {p.evaluation?.metrics?.length ? (
        <Card className="p-5" delay={0.2}>
          <CardHeader icon="monitoring" title="Nugen evaluation · base vs aligned" sub="On the held-out benchmark" />
          {p.evaluation.metrics.map((m) => (
            <div key={m.metric} className="grid grid-cols-[180px_1fr] items-center gap-3 text-[12px] py-1">
              <span className="text-ink-2">{m.metric.replace(/_/g, " ")}</span>
              <div className="space-y-1">
                {(["base", "evaluated"] as const).map((k) => (
                  <div key={k} className="flex items-center gap-2">
                    <span className="w-14 text-ink-3">{k === "base" ? "base" : "aligned"}</span>
                    <div className="flex-1 h-2 bg-canvas-3 rounded-full overflow-hidden">
                      <motion.div className={k === "base" ? "h-full bg-slate-400" : "h-full bg-fuchsia-500"} initial={{ width: 0 }} animate={{ width: `${Math.min(1, m[k]) * 100}%` }} transition={{ duration: 0.8 }} />
                    </div>
                    <span className="w-10 text-right tnum">{m[k].toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </Card>
      ) : null}
    </div>
  );
}
