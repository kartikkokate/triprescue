/** @type {import('tailwindcss').Config} */
// "AeroRescue" light-sky design system (see stitch_triprescue_light_sky_redesign/aerorescue_operations/DESIGN.md)
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Geist", "Inter", "system-ui", "sans-serif"] },
      colors: {
        ink: { DEFAULT: "#102A43", 2: "#486581", 3: "#829AB1" },
        canvas: { DEFAULT: "#F3FAFF", 2: "#EDF8FF", 3: "#E8F5FD" },
        line: { DEFAULT: "#E2EDF4", 2: "#D9EAF5" },
        well: "#FCFEFF",
        icy: "#DDF3FF",
        sky: { DEFAULT: "#228BE6", deep: "#2F80ED", light: "#56CCF2", soft: "#60A5FA", ink: "#005EA3" },
        safe: { DEFAULT: "#10B981", bg: "#ECFDF5", ink: "#065F46" },
        risk: { DEFAULT: "#F59E0B", bg: "#FEF3C7", ink: "#92400E" },
        broken: { DEFAULT: "#EF4444", bg: "#FEF2F2", ink: "#991B1B" },
        cancel: { DEFAULT: "#DC2626", bg: "#FEE2E2", ink: "#7F1D1D" },
        pending: { DEFAULT: "#8B5CF6", bg: "#F5F3FF", ink: "#5B21B6" },
        dropped: { DEFAULT: "#94A3B8", bg: "#F1F5F9", ink: "#475569" },
      },
      boxShadow: {
        l1: "0 1px 3px 0 rgba(16,42,67,0.04), 0 4px 12px 0 rgba(34,139,230,0.05)",
        l2: "0 4px 16px 0 rgba(16,42,67,0.06), 0 8px 24px -4px rgba(34,139,230,0.10)",
        l3: "0 12px 32px -4px rgba(16,42,67,0.08), 0 20px 48px -8px rgba(34,139,230,0.12)",
        cta: "0 4px 14px rgba(34,139,230,0.30)",
      },
      borderRadius: { card: "1rem" },
      keyframes: {
        dash: { to: { strokeDashoffset: "-24" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: { dash: "dash 1.2s linear infinite" },
    },
  },
  plugins: [],
};
