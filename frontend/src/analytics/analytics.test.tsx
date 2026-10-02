import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { App } from "../App";
import { formatHours } from "./AnalyticsPage";
import { todayIso } from "../format";
import { apiError, client, operator, sessionFor } from "../test/fixtures";
import { renderAt } from "../test/render";
import { server } from "../test/server";

// The page is lazy-loaded; load its (large) chart module once up front, not inside the first test's time.
beforeAll(async () => {
  await import("./AnalyticsPage");
});

const report = {
  range: { from: "2026-09-03", to: "2026-10-02" },
  episodes_per_day: [
    { date: "2026-09-05", robot_id: "arm-01", episodes: 4 },
    { date: "2026-09-05", robot_id: "arm-02", episodes: 2 },
    { date: "2026-09-06", robot_id: "arm-01", episodes: 3 },
  ],
  top_tasks_by_good_episodes: [
    { task_name: "pick cup", good_episodes: 19 },
    { task_name: "open drawer", good_episodes: 16 },
  ],
  requests: {
    by_status: { submitted: 2, in_progress: 1, delivered: 1, accepted: 1, rejected: 1 },
    median_hours_to_delivery: 36,
    delivered_count: 3,
  },
};

function daysBefore(days: number) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return todayIso(date);
}

function analyticsApi() {
  const queries: URLSearchParams[] = [];
  server.use(
    ...sessionFor(operator),
    http.get("/api/analytics/", ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return HttpResponse.json(report);
    }),
  );
  return queries;
}

test("shows the last 30 days by default, with the headline numbers", async () => {
  const queries = analyticsApi();

  renderAt(<App />, "/analytics");

  // The first render waits for the lazy page and the data; allow for a busy CI runner.
  expect(await screen.findByText("9", {}, { timeout: 10_000 })).toBeInTheDocument(); // episodes recorded
  expect(screen.getByText("1.5 days")).toBeInTheDocument(); // median time to delivery
  expect(screen.getByText(/based on 3 deliveries/i)).toBeInTheDocument();
  expect(queries[0]?.get("from")).toBe(daysBefore(29));
  expect(queries[0]?.get("to")).toBe(todayIso());
});

test("lists the top tasks by good episodes, best first", async () => {
  analyticsApi();

  renderAt(<App />, "/analytics");

  const top = await screen.findByRole("list", { name: "Top tasks by good episodes" });
  const items = within(top).getAllByRole("listitem");
  expect(items[0]).toHaveTextContent(/pick cup.*19/);
  expect(items[1]).toHaveTextContent(/open drawer.*16/);
});

test("counts requests by status", async () => {
  analyticsApi();

  renderAt(<App />, "/analytics");

  const statuses = await screen.findByRole("list", { name: "Requests by status" });
  expect(statuses).toHaveTextContent(/Submitted\s*2/);
  expect(statuses).toHaveTextContent(/Accepted\s*1/);
});

test("the range can be changed, and is kept in the address", async () => {
  const queries = analyticsApi();
  renderAt(<App />, "/analytics");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("radio", { name: "Last 7 days" }));

  await waitFor(() => expect(queries.at(-1)?.get("from")).toBe(daysBefore(6)));
});

test("the chart's numbers are also available as a table", async () => {
  analyticsApi();
  renderAt(<App />, "/analytics");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Show as table" }));

  const rows = within(screen.getByRole("table", { name: "Episodes per day" })).getAllByRole("row");
  expect(rows[1]).toHaveTextContent(/5 Sept 2026.*4.*2.*6/); // arm-01, arm-02, total
});

test("a range the API refuses says why", async () => {
  server.use(
    ...sessionFor(operator),
    http.get("/api/analytics/", () =>
      apiError(400, "invalid", "Some fields are invalid.", { to: ["The range can be at most 366 days."] }),
    ),
  );

  renderAt(<App />, "/analytics?from=2020-01-01&to=2026-01-01");

  expect(await screen.findByRole("alert")).toHaveTextContent("The range can be at most 366 days.");
});

test("clients can't open analytics", async () => {
  server.use(...sessionFor(client));

  renderAt(<App />, "/analytics");

  expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
});

test.each([
  [null, "—"],
  [0.2, "under 1 h"],
  [5, "5 h"],
  [36, "1.5 days"],
])("a median of %s hours reads %s", (hours, text) => {
  expect(formatHours(hours)).toBe(text);
});
