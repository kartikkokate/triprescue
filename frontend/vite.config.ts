import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // 5180, not the Vite default 5173 - another local project (Celestial) already uses 5173
  server: { port: 5180, strictPort: true },
});
