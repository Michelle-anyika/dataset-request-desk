import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

/** The accounts the seed step creates (backend/seed/users.json). */
export const ACCOUNTS = {
  client: { email: "client-a@example.com", password: "client123" },
  operator: { email: "ops1@example.com", password: "ops123" },
  admin: { email: "admin@example.com", password: "admin123" },
} as const;

export async function signIn(page: Page, who: keyof typeof ACCOUNTS) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ACCOUNTS[who].email);
  await page.getByRole("textbox", { name: "Password", exact: true }).fill(ACCOUNTS[who].password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/requests/);
}

export async function signOut(page: Page) {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
}

/** No serious or critical WCAG 2.2 A/AA violations on the page as it is now. */
export async function expectAccessible(page: Page) {
  // A popover or modal that is still fading in is half transparent, and axe would measure that contrast.
  // Infinite animations (loaders) never finish, so they don't count.
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getTiming().iterations === Infinity),
  );
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  // Each violation with the HTML that caused it, so a failure says exactly what to fix.
  const report = blocking.map((v) => [`${v.id}: ${v.help}`, ...v.nodes.map((n) => `  ${n.html.slice(0, 160)}`)].join(" | "));
  expect(report).toEqual([]);
}

export function daysFromNow(days: number) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}
