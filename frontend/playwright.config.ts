import { defineConfig, devices } from "@playwright/test";

// End-to-end tests against the running Docker stack (docker compose up): the real app, API and database.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // the journeys share one database
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // The app follows the system's reduced-motion setting (theme.ts), so popovers and dialogs appear at full
    // opacity at once. Without it, axe could measure a dropdown mid-fade, or in the frame before its fade starts,
    // and report its text as low contrast.
    reducedMotion: "reduce",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
