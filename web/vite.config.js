import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// public/data/*.json is written by `python -m src.emit --web` (see ../src/emit.py).
// Vite serves web/public/* as-is, so the app fetches it at /data/features.json
// with no build-time copy step.
export default defineConfig({
  plugins: [react()],
});
