import { expect, test } from "@playwright/test";

import { daysFromNow, expectAccessible, signIn, signOut } from "./helpers";

// The loop the product exists for, through the real UI: a client asks, an operator fulfils, the client is
// told and accepts. Each screen is checked for accessibility on the way.
test("a request goes from submitted to accepted", async ({ page }) => {
  const task = "pick cup";
  const notes = `e2e ${Date.now()}`;

  // The client submits a request.
  await signIn(page, "client");
  await expectAccessible(page);
  await page.getByRole("link", { name: "New request" }).first().click();
  await page.getByLabel("Task").fill(task);
  await page.getByLabel("Episodes requested").fill("2");
  await page.getByLabel("Deadline").fill(daysFromNow(10));
  await page.getByLabel("Notes").fill(notes);
  await expectAccessible(page);
  await page.getByRole("button", { name: "Submit request" }).click();
  await expect(page.getByRole("heading", { name: task })).toBeVisible();
  await expect(page.getByText(notes)).toBeVisible();
  const requestUrl = page.url();
  await expectAccessible(page);
  await signOut(page);

  // An operator starts it, assigns exactly what is needed and delivers.
  await signIn(page, "operator");
  await expectAccessible(page);
  await page.goto(requestUrl);
  await page.getByRole("button", { name: "Start work" }).click();
  await page.getByRole("link", { name: "Assign episodes" }).click();
  await expect(page.getByText("0 of 2 assigned")).toBeVisible();
  await expectAccessible(page);
  await page.getByRole("button", { name: "Select the 2 still needed" }).click();
  await page.getByRole("button", { name: "Assign 2 episodes" }).click();
  await expect(page.getByText("2 of 2 assigned")).toBeVisible();
  await page.goto(requestUrl);
  await page.getByRole("button", { name: "Mark as delivered" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Deliver" }).click();
  await expect(page.getByText(/Waiting for .* to review/)).toBeVisible();
  await signOut(page);

  // The client is notified, opens the delivery from the bell and accepts it.
  await signIn(page, "client");
  await expect(page.getByRole("table").getByText("Action required").first()).toBeVisible();
  await page.getByRole("button", { name: /^Notifications, \d+ unread$/ }).click();
  await expectAccessible(page);
  await page.getByRole("list", { name: "Recent notifications" }).getByRole("link").first().click();
  await expect(page).toHaveURL(requestUrl);
  await page.getByRole("button", { name: "Accept delivery" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Accept" }).click();
  await expect(page.getByRole("list", { name: "History" }).getByRole("listitem")).toHaveCount(4);
  await expect(page.getByText("Complete").or(page.getByText("Accepted", { exact: true })).first()).toBeVisible();
});
