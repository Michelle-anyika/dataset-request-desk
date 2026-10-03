import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { App } from "../App";
import type { DatasetRequest } from "../api/types";
import { apiError, makeRequest, operator, page, sessionFor } from "../test/fixtures";
import { renderAt } from "../test/render";
import { server } from "../test/server";

const daysAgo = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString();

const submitted = makeRequest({ id: "aaaaaaaa-0000-4000-8000-000000000011", task_name: "pick cup" });
const delivered = makeRequest({
  id: "aaaaaaaa-0000-4000-8000-000000000012",
  task_name: "fold towel",
  status: "delivered",
  assigned_count: 20,
  status_changed_at: daysAgo(4),
  client: { id: "c2", full_name: "Bea Buyer", organisation: "Beta Labs" },
});

describe("request queue", () => {
  test("lists every client's requests with who asked and the progress", async () => {
    server.use(...sessionFor(operator), http.get("/api/requests/", () => HttpResponse.json(page([submitted, delivered]))));

    renderAt(<App />, "/requests");

    const rows = within(await screen.findByRole("table")).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("pick cup");
    expect(rows[1]).toHaveTextContent("Carla Client");
    expect(rows[1]).toHaveTextContent("0 / 20");
    expect(rows[2]).toHaveTextContent("Bea Buyer");
    expect(rows[2]).toHaveTextContent("Beta Labs");
  });

  test("delivered requests show how long the client has been deciding, the oldest first", async () => {
    const seen: URLSearchParams[] = [];
    server.use(
      ...sessionFor(operator),
      http.get("/api/requests/", ({ request }) => {
        seen.push(new URL(request.url).searchParams);
        return HttpResponse.json(page([delivered]));
      }),
    );
    renderAt(<App />, "/requests");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("radio", { name: "Delivered" }));

    await waitFor(() =>
      expect(seen.some((p) => p.get("status") === "delivered" && p.get("ordering") === "status_changed_at")).toBe(true),
    );
    expect(await screen.findByText("Awaiting client for 4 days")).toBeInTheDocument();
  });

  test("can be sorted by deadline", async () => {
    const orderings: (string | null)[] = [];
    server.use(
      ...sessionFor(operator),
      http.get("/api/requests/", ({ request }) => {
        orderings.push(new URL(request.url).searchParams.get("ordering"));
        return HttpResponse.json(page([submitted]));
      }),
    );
    renderAt(<App />, "/requests");
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByLabelText("Sort by"), "deadline");

    await waitFor(() => expect(orderings).toContain("deadline"));
  });
});

describe("request detail for staff", () => {
  function detailOf(request: DatasetRequest, events: unknown[] = []) {
    return [
      http.get(`/api/requests/${request.id}/`, () => HttpResponse.json(request)),
      http.get(`/api/requests/${request.id}/events/`, () => HttpResponse.json(page(events))),
      http.get(`/api/requests/${request.id}/assignments/`, () => HttpResponse.json(page([]))),
    ];
  }

  function transitions(request: DatasetRequest, sent: unknown[]) {
    return http.post(`/api/requests/${request.id}/transitions/`, async ({ request: http }) => {
      const body = (await http.json()) as { to_status: DatasetRequest["status"] };
      sent.push(body);
      return HttpResponse.json({ ...request, status: body.to_status });
    });
  }

  test("a submitted request can be started", async () => {
    const sent: unknown[] = [];
    server.use(...sessionFor(operator), ...detailOf(submitted), transitions(submitted, sent));
    renderAt(<App />, `/requests/${submitted.id}`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Start work" }));

    await waitFor(() => expect(sent).toEqual([{ to_status: "in_progress", comment: "" }]));
  });

  test("delivery waits until enough episodes are assigned", async () => {
    const short = makeRequest({ ...submitted, status: "in_progress", assigned_count: 15 });
    server.use(...sessionFor(operator), ...detailOf(short));

    renderAt(<App />, `/requests/${short.id}`);

    expect(await screen.findByRole("button", { name: "Mark as delivered" })).toBeDisabled();
    expect(screen.getByText("Assign 5 more episodes to deliver.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /assign episodes/i })).toHaveAttribute(
      "href",
      `/requests/${short.id}/assign`,
    );
  });

  test("a complete request is delivered after confirming", async () => {
    const ready = makeRequest({ ...submitted, status: "in_progress", assigned_count: 20 });
    const sent: unknown[] = [];
    server.use(...sessionFor(operator), ...detailOf(ready), transitions(ready, sent));
    renderAt(<App />, `/requests/${ready.id}`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Mark as delivered" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Carla Client");
    await user.click(within(dialog).getByRole("button", { name: "Deliver" }));

    await waitFor(() => expect(sent).toEqual([{ to_status: "delivered", comment: "" }]));
  });

  test("the API's reason is shown when a step is refused", async () => {
    const ready = makeRequest({ ...submitted, status: "in_progress", assigned_count: 20 });
    server.use(
      ...sessionFor(operator),
      ...detailOf(ready),
      http.post(`/api/requests/${ready.id}/transitions/`, () =>
        apiError(409, "not_enough_episodes", "Assign at least 20 episodes before delivering."),
      ),
    );
    renderAt(<App />, `/requests/${ready.id}`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Mark as delivered" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Deliver" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Assign at least 20 episodes before delivering.");
  });

  test("if someone else already moved the request, the page catches up with its current status", async () => {
    const stale = makeRequest({ ...submitted, status: "submitted" });
    let current = stale;
    server.use(
      ...sessionFor(operator),
      http.get(`/api/requests/${stale.id}/`, () => HttpResponse.json(current)),
      http.get(`/api/requests/${stale.id}/events/`, () => HttpResponse.json(page([]))),
      http.get(`/api/requests/${stale.id}/assignments/`, () => HttpResponse.json(page([]))),
      http.post(`/api/requests/${stale.id}/transitions/`, () => {
        current = { ...stale, status: "in_progress" }; // another operator started it a moment ago
        return apiError(409, "invalid_transition", "Can't go from in progress to in progress.");
      }),
    );
    renderAt(<App />, `/requests/${stale.id}`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Start work" }));

    expect(await screen.findByRole("button", { name: "Mark as delivered" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start work" })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/changed since you opened it/i);
  });

  test("a rejected request shows the client's reason and can be reworked", async () => {
    const rejected = makeRequest({ ...submitted, status: "rejected", assigned_count: 20 });
    const sent: unknown[] = [];
    const rejection = {
      from_status: "delivered",
      to_status: "rejected",
      changed_by: { full_name: "Carla Client", role: "client" },
      changed_at: daysAgo(1),
      comment: "Two clips are blurry.",
    };
    server.use(...sessionFor(operator), ...detailOf(rejected, [rejection]), transitions(rejected, sent));
    renderAt(<App />, `/requests/${rejected.id}`);
    const user = userEvent.setup();

    expect(await screen.findByText(/Carla Client rejected the delivery/)).toBeInTheDocument();
    expect((await screen.findAllByText(/Two clips are blurry./)).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Start rework" }));

    await waitFor(() => expect(sent).toEqual([{ to_status: "in_progress", comment: "" }]));
  });

  test("staff can't accept or reject for the client", async () => {
    server.use(...sessionFor(operator), ...detailOf(delivered));

    renderAt(<App />, `/requests/${delivered.id}`);

    expect(await screen.findByText(/Waiting for Bea Buyer to review/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept delivery" })).not.toBeInTheDocument();
  });
});
