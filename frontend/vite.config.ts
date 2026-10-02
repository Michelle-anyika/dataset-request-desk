import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the API runs on :8000 and is proxied, so the app and the API share one origin, as in
// production (nginx): the refresh cookie works without CORS (PLAN.md decision #8).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  build: {
    sourcemap: false, // no source maps shipped to browsers
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/test/**", "src/**/*.test.{ts,tsx}"],
      // lcov paths relative to the repository root, as SonarCloud expects them.
      reporter: ["text", ["lcov", { projectRoot: ".." }]],
    },
  },
});
