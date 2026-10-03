import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { App } from "./App";
import type { User } from "./api/types";
import { admin, apiError, client, makeRequest, operator, page, sessionFor } from "./test/fixtures";
import { renderAt } from "./test/render";
import { server } from "./test/server";

// Every screen must survive an API that refuses to answer: a named error with a way to try again, never a
// blank page. 403 is used because, like any 4xx, it is not retried, and its hint is specific.
let refused = 0;
const refuseEverything = http.all("/api/*", () => {
  refused += 1;
  return apiError(403, "permission_denied", "No.");
});

beforeEach(() => {
  refused = 0;
});

/** Click "Try again" in the alert about `what`, and check that it really asked the API again. */
async function retry(what: string) {
  const alert = (await screen.findByText(`We couldn't load ${what}`)).closest<HTMLElement>("[role=alert]");
  if (!alert) throw new Error(`no alert for ${what}`);
  const before = refused;
  await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
  await waitFor(() => expect(refused).toBeGreaterThan(before));
}

const request = makeRequest({ id: "aaaaaaaa-0000-4000-8000-0000000000f1", status: "in_progress" });

test.each<[string, User, string, string]>([
  ["a client's request list", client, "/requests", "your requests"],
  ["a client's request", client, `/requests/${request.id}`, "this request"],
  ["the notifications inbox", client, "/notifications", "your notifications"],
  ["the request queue", operator, "/requests", "the requests"],
  ["the assign page", operator, `/requests/${request.id}/assign`, "this request"],
  ["the imports", operator, "/imports", "the imports"],
  ["an import report", operator, "/imports/7", "this import"],
  ["the analytics", operator, "/analytics", "the analytics"],
  ["the accounts", admin, "/users", "the accounts"],
])("%s explains a failed load and offers to try again", async (_, user, url, what) => {
  server.use(...sessionFor(user), refuseEverything);

  renderAt(<App />, url);

  const alert = await screen.findByRole("alert", {}, { timeout: 5000 });
  expect(alert).toHaveTextContent(`We couldn't load ${what}`);
  expect(alert).toHaveTextContent("Your account doesn't have access to this.");
  await retry(what);
});

test("on a request, the history and the episodes fail on their own, and the rest still works", async () => {
  server.use(
    ...sessionFor(client),
    http.get(`/api/requests/${request.id}/`, () => HttpResponse.json(request)),
    refuseEverything,
  );

  renderAt(<App />, `/requests/${request.id}`);

  expect(await screen.findByRole("heading", { name: request.task_name, level: 1 })).toBeInTheDocument();
  await retry("the history");
  await retry("the episodes");
});

test("on the assign page, the catalogue and the assigned list fail on their own", async () => {
  server.use(
    ...sessionFor(operator),
    http.get(`/api/requests/${request.id}/`, () => HttpResponse.json(request)),
    refuseEverything,
  );

  renderAt(<App />, `/requests/${request.id}/assign`);

  await retry("the episodes");
  await retry("the assigned episodes");
});

test("on an import report, the rows fail on their own", async () => {
  server.use(
    ...sessionFor(operator),
    http.get("/api/imports/7/", () =>
      HttpResponse.json({
        id: 7,
        file_name: "episodes.csv",
        status: "completed",
        total_rows: 2,
        created_count: 2,
        updated_count: 0,
        unchanged_count: 0,
        skipped_count: 0,
        fixed_count: 0,
        error_message: "",
        previously_imported: false,
        uploaded_by: { full_name: "Olu Operator" },
        started_at: "2026-10-01T10:00:00Z",
        finished_at: "2026-10-01T10:00:02Z",
      }),
    ),
    http.get("/api/imports/7/issues/", () => {
      refused += 1;
      return apiError(403, "permission_denied", "No.");
    }),
    http.get("/api/imports/", () => HttpResponse.json(page([]))),
  );

  renderAt(<App />, "/imports/7");

  await retry("the rows");
});
