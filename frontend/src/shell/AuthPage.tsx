import { useState } from "react";
import { motion } from "framer-motion";
import { signIn, signUp } from "../auth";
import { Icon } from "../ui";

type Mode = "signin" | "signup";
const spring = { type: "spring" as const, stiffness: 260, damping: 32 };

/** Sign in / sign up with a sliding panel. Optional for now: "Continue as guest" skips it. */
export default function AuthPage({ onDone, onGuest }: { onDone: (msg: string) => void; onGuest: () => void }) {
  const [mode, setMode] = useState<Mode>("signin");

  return (
    <div className="fixed inset-0 z-[1300] overflow-y-auto bg-gradient-to-br from-canvas via-canvas-2 to-icy">
      <Backdrop />
      <div className="relative min-h-full grid place-items-center px-4 py-10">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="w-full max-w-[960px]">
          <div className="flex items-center justify-center gap-2 mb-6">
            <span className="h-9 w-9 rounded-lg grid place-items-center text-white" style={{ background: "linear-gradient(135deg,#2F80ED,#56CCF2)" }}>
              <Icon name="flight_takeoff" className="!text-[20px]" />
            </span>
            <span className="text-[22px] font-bold tracking-[-0.02em]">
              <span className="text-ink">Trip</span>
              <span className="text-sky">Rescue</span>
            </span>
          </div>

          {/* ---- desktop: two forms side by side, a gradient panel slides over the inactive one ---- */}
          <div className="hidden md:block relative card shadow-l3 overflow-hidden h-[580px]">
            <div className="grid grid-cols-2 h-full">
              <motion.div animate={{ opacity: mode === "signin" ? 1 : 0, x: mode === "signin" ? 0 : 40 }} transition={spring} className="p-10 flex flex-col justify-center" aria-hidden={mode !== "signin"}>
                <SignInForm onDone={onDone} active={mode === "signin"} />
                <GuestLink onGuest={onGuest} />
              </motion.div>
              <motion.div animate={{ opacity: mode === "signup" ? 1 : 0, x: mode === "signup" ? 0 : -40 }} transition={spring} className="p-10 flex flex-col justify-center" aria-hidden={mode !== "signup"}>
                <SignUpForm onDone={onDone} onSwitch={() => setMode("signin")} active={mode === "signup"} />
                <GuestLink onGuest={onGuest} />
              </motion.div>
            </div>
            <motion.div
              className="absolute inset-y-0 left-0 w-1/2 text-white overflow-hidden"
              style={{ background: "linear-gradient(135deg,#005EA3 0%,#2F80ED 55%,#56CCF2 100%)" }}
              animate={{ x: mode === "signin" ? "100%" : "0%", borderRadius: mode === "signin" ? "120px 0 0 120px" : "0 120px 120px 0" }}
              transition={spring}
            >
              <PanelArt />
              <div className="relative h-full flex flex-col items-center justify-center text-center px-12 gap-4">
                <motion.div key={mode} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="space-y-4">
                  <h2 className="text-[30px] leading-[38px] font-bold tracking-[-0.02em]">{mode === "signin" ? "New to TripRescue?" : "Welcome back!"}</h2>
                  <p className="text-[15px] leading-6 text-white/85">
                    {mode === "signin"
                      ? "Create an account and every trip you build is saved to it - open it again from any device."
                      : "Sign in to open the trips saved to your account and pick up where you left off."}
                  </p>
                  <button onClick={() => setMode(mode === "signin" ? "signup" : "signin")} className="btn h-11 px-8 rounded-full border-2 border-white/80 text-white hover:bg-white hover:text-sky-ink transition">
                    {mode === "signin" ? "Create account" : "Sign in"} <Icon name="arrow_forward" className="!text-[18px]" />
                  </button>
                </motion.div>
              </div>
            </motion.div>
          </div>

          {/* ---- mobile: segmented switch, forms slide horizontally ---- */}
          <div className="md:hidden card shadow-l3 p-6 overflow-hidden">
            <div className="relative grid grid-cols-2 p-1 rounded-full bg-canvas-3 border border-line mb-6">
              <motion.span className="absolute top-1 bottom-1 w-[calc(50%-4px)] rounded-full bg-white shadow-[0_2px_6px_rgba(16,42,67,0.08)]" animate={{ left: mode === "signin" ? 4 : "50%" }} transition={spring} />
              {(["signin", "signup"] as Mode[]).map((m) => (
                <button key={m} onClick={() => setMode(m)} className={`relative h-9 text-[13px] font-medium ${mode === m ? "text-ink" : "text-ink-2"}`}>
                  {m === "signin" ? "Sign in" : "Create account"}
                </button>
              ))}
            </div>
            <div className="overflow-hidden">
              <motion.div className="flex w-[200%]" animate={{ x: mode === "signin" ? "0%" : "-50%" }} transition={spring}>
                <div className="w-1/2 pr-2">
                  <SignInForm onDone={onDone} active={mode === "signin"} />
                </div>
                <div className="w-1/2 pl-2">
                  <SignUpForm onDone={onDone} onSwitch={() => setMode("signin")} active={mode === "signup"} />
                </div>
              </motion.div>
            </div>
            <GuestLink onGuest={onGuest} />
          </div>

          <p className="text-center text-[11px] text-ink-3 mt-5 flex items-center justify-center gap-1.5">
            <Icon name="verified_user" className="!text-[14px] text-sky" /> Secured by Supabase Auth · TripRescue never books or charges on your behalf
          </p>
        </motion.div>
      </div>
    </div>
  );
}

function SignInForm({ onDone, active }: { onDone: (m: string) => void; active: boolean }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
      onDone("Signed in - your trips are saved to your account");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-4" {...((active ? {} : { inert: "" }) as any)}>
      <div>
        <h1 className="text-[28px] leading-9 font-bold tracking-[-0.02em]">Sign in</h1>
        <p className="text-[13px] text-ink-2 mt-1">Your saved trips, recovery plans and alerts.</p>
      </div>
      <Field icon="mail" label="Email">
        <input className="input pl-10" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
      </Field>
      <Field icon="lock" label="Password">
        <input className="input pl-10 pr-10" type={show ? "text" : "password"} autoComplete="current-password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
        <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-2 top-1/2 -translate-y-1/2 h-7 w-7 grid place-items-center text-ink-3 hover:text-ink" aria-label={show ? "Hide password" : "Show password"}>
          <Icon name={show ? "visibility_off" : "visibility"} className="!text-[18px]" />
        </button>
      </Field>
      {error && <Note tone="error">{error}</Note>}
      <button className="btn-primary w-full h-11" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"} <Icon name="login" className="!text-[18px]" />
      </button>
    </form>
  );
}

function SignUpForm({ onDone, onSwitch, active }: { onDone: (m: string) => void; onSwitch: () => void; active: boolean }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 6) return setError("Use at least 6 characters for the password.");
    setBusy(true);
    setError(null);
    try {
      const res = await signUp(name.trim(), email.trim(), password);
      if (res === "signed_in") onDone(`Welcome, ${name.trim() || "traveler"} - your account is ready`);
      else setSent(true);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  if (sent)
    return (
      <div className="space-y-4 text-center">
        <span className="mx-auto h-14 w-14 rounded-full bg-icy grid place-items-center"><Icon name="mark_email_read" className="text-sky !text-[28px]" /></span>
        <h1 className="text-[24px] font-bold">Check your inbox</h1>
        <p className="text-[13px] text-ink-2">We sent a confirmation link to <b>{email}</b>. Open it, then sign in.</p>
        <button type="button" className="btn-secondary" onClick={onSwitch}>Go to sign in</button>
      </div>
    );
  return (
    <form onSubmit={submit} className="space-y-4" {...((active ? {} : { inert: "" }) as any)}>
      <div>
        <h1 className="text-[28px] leading-9 font-bold tracking-[-0.02em]">Create account</h1>
        <p className="text-[13px] text-ink-2 mt-1">Save every trip to your own account.</p>
      </div>
      <Field icon="person" label="Name">
        <input className="input pl-10" autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
      </Field>
      <Field icon="mail" label="Email">
        <input className="input pl-10" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
      </Field>
      <Field icon="lock" label="Password">
        <input className="input pl-10" type="password" autoComplete="new-password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 6 characters" />
      </Field>
      {error && <Note tone="error">{error}</Note>}
      <button className="btn-primary w-full h-11" disabled={busy}>
        {busy ? "Creating…" : "Create account"} <Icon name="person_add" className="!text-[18px]" />
      </button>
    </form>
  );
}

function Field({ icon, label, children }: { icon: string; label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <span className="relative block">
        <Icon name={icon} className="absolute left-3 top-1/2 -translate-y-1/2 !text-[18px] text-ink-3 pointer-events-none" />
        {children}
      </span>
    </label>
  );
}

function Note({ tone, children }: { tone: "error"; children: React.ReactNode }) {
  return (
    <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className={`text-[12px] rounded-lg px-3 py-2 flex items-start gap-1.5 ${tone === "error" ? "bg-broken-bg text-broken-ink" : ""}`}>
      <Icon name="error" className="!text-[16px]" /> {children}
    </motion.p>
  );
}

function GuestLink({ onGuest }: { onGuest: () => void }) {
  return (
    <button type="button" onClick={onGuest} className="mt-5 mx-auto flex items-center gap-1 text-[13px] font-medium text-sky-ink hover:underline">
      Continue as guest <Icon name="arrow_forward" className="!text-[16px]" />
    </button>
  );
}

/** Slow-drifting route line and planes in the gradient panel. */
function PanelArt() {
  return (
    <svg className="absolute inset-0 w-full h-full opacity-30" viewBox="0 0 400 580" preserveAspectRatio="none" aria-hidden>
      <path d="M-20 460 C 120 380, 180 520, 300 360 S 420 200, 460 120" fill="none" stroke="white" strokeWidth="2" strokeDasharray="6 8" className="animate-dash" />
      <path d="M-20 200 C 80 140, 200 260, 320 120" fill="none" stroke="white" strokeWidth="1.5" strokeDasharray="4 10" className="animate-dash" />
      <circle cx="300" cy="360" r="5" fill="white" />
      <circle cx="120" cy="170" r="4" fill="white" />
    </svg>
  );
}

function Backdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      <motion.div className="absolute -top-32 -left-24 h-96 w-96 rounded-full bg-sky-light/25 blur-3xl" animate={{ x: [0, 40, 0], y: [0, 30, 0] }} transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }} />
      <motion.div className="absolute -bottom-40 -right-24 h-[28rem] w-[28rem] rounded-full bg-sky/15 blur-3xl" animate={{ x: [0, -40, 0], y: [0, -20, 0] }} transition={{ duration: 22, repeat: Infinity, ease: "easeInOut" }} />
    </div>
  );
}
