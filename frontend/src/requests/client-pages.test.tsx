import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { App } from "../App";
import { apiError, client, makeRequest, page, sessionFor } from "../test/fixtures";
import { renderAt } from "../test/render";
import { server } from "../test/server";

const delivered = makeRequest({
  id: "aaaaaaaa-0000-4000-8000-000000000002",
  task_name: "fold towel",
  status: "delivered",
  assigned_count: 20,
  status_changed_at: "2026-09-28T09:00:00Z",
});
const submitted = makeRequest();

describe("my requests", () => {
  test("lists the client's requests with their status, and flags deliveries waiting for them", async () => {
    server.use(
      ...sessionFor(client),
      http.get("/api/requests/", ({ request }) => {
        const status = new URL(request.url).searchParams.get("status");
        return HttpResponse.json(page([delivered, submitted].filter((r) => !status || r.status === status)));
      }),
    );

    renderAt(<App />, "/requests");

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3); // the header and two requests
    expect(rows[1]).toHaveTextContent("fold towel");
    expect(rows[1]).toHaveTextContent("Delivered");
    expect(rows[1]).toHaveTextContent("Action required");
    expect(rows[2]).toHaveTextContent("Submitted");
    expect(rows[2]).not.toHaveTextContent("Action required");
    expect(screen.getByText(/1 delivery is waiting for your review/i)).toBeInTheDocument();
  });

  test("can be filtered by status", async () => {
    const seen: (string | null)[] = [];
    server.use(
      ...sessionFor(client),
      http.get("/api/requests/", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("status"));
        return HttpResponse.json(page([]));
      }),
    );
    renderAt(<App />, "/requests");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("radio", { name: "Delivered" }));

    await waitFor(() => expect(seen).toContain("delivered"));
  });

  test("shows a helpful empty state", async () => {
    server.use(...sessionFor(client), http.get("/api/requests/", () => HttpResponse.json(page([]))));

    renderAt(<App />, "/requests");

    expect(await screen.findByText("No requests yet")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /new request/i }).length).toBeGreaterThan(0);
  });

  test("says so when the list can't be loaded", async () => {
    server.use(
      ...sessionFor(client),
      http.get("/api/requests/", () => apiError(503, "unavailable", "Down.")),
    );

    renderAt(<App />, "/requests");

    expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent(/couldn't load/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("new request", () => {
  async function fillIn(user: ReturnType<typeof userEvent.setup>) {
    await user.type(await screen.findByLabelText(/task/i), "pick cup");
    await user.clear(screen.getByLabelText(/episodes requested/i));
    await user.type(screen.getByLabelText(/episodes requested/i), "200");
    await user.type(screen.getByLabelText(/deadline/i), "2026-12-01");
  }

  test("checks the fields before sending", async () => {
    const create = vi.fn();
    server.use(...sessionFor(client), http.post("/api/requests/", create));
    renderAt(<App />, "/requests/new");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /submit request/i }));

    expect(await screen.findByText("Describe the task.")).toBeInTheDocument();
    expect(screen.getByText("Choose a deadline.")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  test("submits once, with an idempotency key, and opens the new request", async () => {
    let received: { body: unknown; key: string | null } | undefined;
    const created = makeRequest({ id: "aaaaaaaa-0000-4000-8000-0000000000ff", episodes_requested: 200 });
    server.use(
      ...sessionFor(client),
      http.post("/api/requests/", async ({ request }) => {
        received = { body: await request.json(), key: request.headers.get("Idempotency-Key") };
        return HttpResponse.json(created, { status: 201 });
      }),
      http.get(`/api/requests/${created.id}/`, () => HttpResponse.json(created)),
      http.get(`/api/requests/${created.id}/events/`, () => HttpResponse.json(page([]))),
      http.get(`/api/requests/${created.id}/assignments/`, () => HttpResponse.json(page([]))),
    );
    renderAt(<App />, "/requests/new");
    const user = userEvent.setup();

    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /submit request/i }));

    expect(await screen.findByRole("heading", { name: "pick cup" })).toBeInTheDocument();
    expect(received?.body).toMatchObject({ task_name: "pick cup", episodes_requested: 200, deadline: "2026-12-01" });
    expect(received?.key).toMatch(/^[0-9a-f-]{36}$/);
  });

  test("shows the API's field errors next to the fields", async () => {
    server.use(
      ...sessionFor(client),
      http.post("/api/requests/", () =>
        apiError(400, "invalid", "Some fields are invalid.", { deadline: ["The deadline can't be in the past."] }),
      ),
    );
    renderAt(<App />, "/requests/new");
    const user = userEvent.setup();

    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /submit request/i }));

    expect(await screen.findByText("The deadline can't be in the past.")).toBeInTheDocument();
  });
});

describe("request detail", () => {
  const events = page([
    {
      from_status: null,
      to_status: "submitted",
      changed_by: { full_name: "Carla Client", role: "client" },
      changed_at: "2026-09-20T09:00:00Z",
      comment: "",
    },
    {
      from_status: "submitted",
      to_status: "in_progress",
      changed_by: { full_name: "Olu Operator", role: "operator" },
      changed_at: "2026-09-21T09:00:00Z",
      comment: "",
    },
    {
      from_status: "in_progress",
      to_status: "delivered",
      changed_by: { full_name: "Olu Operator", role: "operator" },
      changed_at: "2026-09-28T09:00:00Z",
      comment: "",
    },
  ]);
  const assignments = page([
    {
      episode: {
        episode_id: "EP-00001",
        robot_id: "arm-01",
        task_name: "fold towel",
        recorded_at: "2026-08-01T10:00:00Z",
        duration_seconds: 30,
        quality: "good",
      },
      assigned_at: "2026-09-27T09:00:00Z",
    },
  ]);

  function detailOf(request: typeof delivered) {
    return [
      http.get(`/api/requests/${request.id}/`, () => HttpResponse.json(request)),
      http.get(`/api/requests/${request.id}/events/`, () => HttpResponse.json(events)),
      http.get(`/api/requests/${request.id}/assignments/`, () => HttpResponse.json(assignments)),
    ];
  }

  test("shows the history, oldest first, with who made each change", async () => {
    server.use(...sessionFor(client), ...detailOf(delivered));

    renderAt(<App />, `/requests/${delivered.id}`);

    const history = await screen.findByRole("list", { name: "History" });
    const items = within(history).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringMatching(/Submitted.*Carla Client/),
      expect.stringMatching(/In progress.*Olu Operator/),
      expect.stringMatching(/Delivered.*Olu Operator/),
    ]);
  });

  test("lists the delivered episodes", async () => {
    server.use(...sessionFor(client), ...detailOf(delivered));

    renderAt(<App />, `/requests/${delivered.id}`);

    expect(await screen.findByRole("cell", { name: "EP-00001" })).toBeInTheDocument();
  });

  test("a delivered request can be accepted", async () => {
    let sent: unknown;
    server.use(
      ...sessionFor(client),
      ...detailOf(delivered),
      http.post(`/api/requests/${delivered.id}/transitions/`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ ...delivered, status: "accepted" });
      }),
    );
    renderAt(<App />, `/requests/${delivered.id}`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Accept delivery" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Accept" }));

    await waitFor(() => expect(sent).toEqual({ to_status: "accepted", comment: "" }));
  });

  test("rejecting asks for a reason", async () => {
    let sent: unknown;
    server.use(
      ...sessionFor(client),
      ...detailOf(delivered),
      http.post(`/api/requests/${delivered.id}/transitions/`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ ...delivered, status: "rejected" });
      }),
    );
    renderAt(<App />, `/requests/${delivered.id}`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Reject delivery" }));
    expect(await within(dialog).findByText("Tell the team what to fix.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText(/reason/i), "Wrong cups.");
    await user.click(within(dialog).getByRole("button", { name: "Reject delivery" }));

    await waitFor(() => expect(sent).toEqual({ to_status: "rejected", comment: "Wrong cups." }));
  });

  test("offers no decision before the request is delivered", async () => {
    server.use(...sessionFor(client), ...detailOf(submitted));

    renderAt(<App />, `/requests/${submitted.id}`);

    await screen.findByRole("heading", { name: "pick cup" });
    expect(screen.queryByRole("button", { name: "Accept delivery" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });

  test("another client's request is not found", async () => {
    server.use(
      ...sessionFor(client),
      http.get("/api/requests/:id/", () => apiError(404, "not_found", "Not found.")),
      http.get("/api/requests/:id/events/", () => apiError(404, "not_found", "Not found.")),
      http.get("/api/requests/:id/assignments/", () => apiError(404, "not_found", "Not found.")),
    );

    renderAt(<App />, "/requests/bbbbbbbb-0000-4000-8000-000000000009");

    expect(await screen.findByRole("heading", { name: "Request not found" })).toBeInTheDocument();
  });
});

test("a large delivery can be reviewed in full, page by page", async () => {
  const large = makeRequest({ id: "aaaaaaaa-0000-4000-8000-000000000130", status: "delivered", episodes_requested: 130, assigned_count: 130 });
  const all = Array.from({ length: 130 }, (_, index) => ({
    episode: {
      episode_id: `EP-${String(index + 1).padStart(5, "0")}`,
      robot_id: "arm-01",
      task_name: "pick cup",
      recorded_at: "2026-08-01T10:00:00Z",
      duration_seconds: 30,
      quality: "good" as const,
    },
    assigned_at: "2026-09-27T09:00:00Z",
  }));
  server.use(
    ...sessionFor(client),
    http.get(`/api/requests/${large.id}/`, () => HttpResponse.json(large)),
    http.get(`/api/requests/${large.id}/events/`, () => HttpResponse.json(page([]))),
    // As the API: pages of at most 100.
    http.get(`/api/requests/${large.id}/assignments/`, ({ request }) => {
      const params = new URL(request.url).searchParams;
      const size = Number(params.get("page_size") ?? 25);
      const number = Number(params.get("page") ?? 1);
      if (size > 100) return apiError(400, "invalid", "page_size: A whole number from 1 to 100.");
      return HttpResponse.json(page(all.slice((number - 1) * size, number * size), all.length));
    }),
  );

  renderAt(<App />, `/requests/${large.id}`);

  expect(await screen.findByText("EP-00001")).toBeInTheDocument();
  expect(screen.queryByText("EP-00130")).not.toBeInTheDocument();
  const pages = screen.getByRole("navigation", { name: "Episode pages" });
  await userEvent.click(within(pages).getByRole("button", { name: "3" })); // 130 episodes, 50 a page
  expect(await screen.findByText("EP-00130")).toBeInTheDocument();
});
