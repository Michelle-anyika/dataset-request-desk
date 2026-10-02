import path from "node:path";

import { expect, test } from "@playwright/test";

import { expectAccessible, signIn, signOut } from "./helpers";

test("re-importing the seed export changes nothing and reports every messy row", async ({ page }) => {
  await signIn(page, "operator");
  await page.getByRole("link", { name: "Imports" }).click();
  await expectAccessible(page);

  const seed = path.resolve(import.meta.dirname, "../../backend/seed/episodes.csv");
  await page.locator('input[type="file"]').setInputFiles(seed);
  await page.getByRole("button", { name: "Import" }).click();

  await expect(page).toHaveURL(/\/imports\/\d+$/);
  await expect(page.getByText("This exact file was imported before")).toBeVisible();
  await expect(page.getByRole("table")).toContainText("Unknown robot");
  await expect(page.getByRole("table")).toContainText("Duplicate in file");
  await expectAccessible(page);
});

test("analytics can be read as a chart and as a table", async ({ page }) => {
  await signIn(page, "operator");
  await page.getByRole("link", { name: "Analytics" }).click();
  await page.getByText("Last 12 months", { exact: true }).click(); // the visible label of a hidden radio
  await expect(page.getByText("Episodes recorded")).toBeVisible();
  await expectAccessible(page);

  await page.getByRole("button", { name: "Show as table" }).click();
  await expect(page.getByRole("table", { name: "Episodes per day" })).toBeVisible();
});

test("an admin creates an account that can then sign in", async ({ page }) => {
  const stamp = Date.now(); // unique per run: the database outlives the test
  const email = `e2e-${stamp}@example.com`;
  const name = `Edith Endtoend ${stamp}`;
  const password = "a-long-and-unusual-passphrase";
  await signIn(page, "admin");
  await page.getByRole("link", { name: "Users" }).click();
  await expectAccessible(page);

  await page.getByRole("button", { name: "New user" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Email").fill(email);
  await dialog.getByLabel("Full name").fill(name);
  await dialog.getByRole("textbox", { name: "Password", exact: true }).fill(password);
  await expectAccessible(page);
  await dialog.getByRole("button", { name: "Create user" }).click();
  await expect(page.getByRole("row", { name: new RegExp(name) })).toBeVisible();

  // Wait for the sign-in page: until the logout request returns, "Email" would also match the users search box.
  await signOut(page);
  await page.getByLabel("Email").fill(email);
  await page.getByRole("textbox", { name: "Password", exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "My requests" })).toBeVisible();
});

test("each role's pages are closed to other roles", async ({ page }) => {
  await signIn(page, "client");
  for (const url of ["/imports", "/analytics", "/users"]) {
    await page.goto(url);
    await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  }
});
