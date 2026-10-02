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
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
