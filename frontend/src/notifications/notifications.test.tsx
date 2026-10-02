import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { App } from "../App";
import { client, makeRequest, page, sessionFor } from "../test/fixtures";
import { renderAt } from "../test/render";
import { server } from "../test/server";

const request = makeRequest({ status: "delivered" });

function note(id: number, overrides = {}) {
  return {
    id,
    kind: "request_delivered",
    message: `Your “pick cup” request has been delivered (${id})`,
    request: { id: request.id, task_name: "pick cup", status: "delivered" },
    created_at: new Date(Date.now() - id * 60_000).toISOString(),
    read_at: null as string | null,
    ...overrides,
  };
}

function inboxApi(notes = [note(1), note(2), note(3, { read_at: "2026-10-01T10:00:00Z" })]) {
  const state = { notes, read: [] as string[], readAll: 0, listQueries: [] as URLSearchParams[] };
  server.use(
    ...sessionFor(client),
    http.get("/api/requests/", () => HttpResponse.json(page([]))),
    http.get("/api/notifications/summary/", () =>
      HttpResponse.json({ unread: state.notes.filter((n) => !n.read_at).length }),
    ),
    http.get("/api/notifications/", ({ request: http }) => {
      const query = new URL(http.url).searchParams;
      state.listQueries.push(query);
      const notes = query.get("unread") === "true" ? state.notes.filter((n) => !n.read_at) : state.notes;
      return HttpResponse.json(page(notes));
    }),
    http.post("/api/notifications/:id/read/", ({ params }) => {
      state.read.push(String(params.id));
      state.notes = state.notes.map((n) => (String(n.id) === params.id ? { ...n, read_at: new Date().toISOString() } : n));
      return new HttpResponse(null, { status: 204 });
    }),
    http.post("/api/notifications/read-all/", () => {
      state.readAll += 1;
      state.notes = state.notes.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() }));
      return new HttpResponse(null, { status: 204 });
    }),
    http.get(`/api/requests/${request.id}/`, () => HttpResponse.json(request)),
    http.get(`/api/requests/${request.id}/events/`, () => HttpResponse.json(page([]))),
    http.get(`/api/requests/${request.id}/assignments/`, () => HttpResponse.json(page([]))),
  );
  return state;
}

test("the bell shows how many notifications are unread", async () => {
  inboxApi();

  renderAt(<App />, "/requests");

  expect(await screen.findByRole("button", { name: "Notifications, 2 unread" })).toBeInTheDocument();
});

test("opening the bell lists recent notifications, unread first marked", async () => {
  inboxApi();
  renderAt(<App />, "/requests");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: /^Notifications/ }));

  const items = within(await screen.findByRole("list", { name: "Recent notifications" })).getAllByRole("listitem");
  expect(items).toHaveLength(3);
  expect(items[0]).toHaveTextContent(/delivered \(1\)/);
  expect(within(items[0] as HTMLElement).getByText("Unread")).toBeInTheDocument();
  expect(within(items[2] as HTMLElement).queryByText("Unread")).not.toBeInTheDocument();
});

test("choosing a notification marks it read and opens its request", async () => {
  const api = inboxApi();
  renderAt(<App />, "/requests");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: /^Notifications/ }));
  await user.click(await screen.findByRole("link", { name: /delivered \(1\)/ }));

  expect(await screen.findByRole("heading", { name: "pick cup" })).toBeInTheDocument();
  expect(api.read).toEqual(["1"]);
  expect(await screen.findByRole("button", { name: "Notifications, 1 unread" })).toBeInTheDocument();
});

test("all can be marked as read at once", async () => {
  const api = inboxApi();
  renderAt(<App />, "/requests");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: /^Notifications/ }));
  await user.click(await screen.findByRole("button", { name: "Mark all as read" }));

  await waitFor(() => expect(api.readAll).toBe(1));
  expect(await screen.findByRole("button", { name: "Notifications, none unread" })).toBeInTheDocument();
});

test("with nothing new, the bell says so", async () => {
  inboxApi([]);
  renderAt(<App />, "/requests");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Notifications, none unread" }));

  expect(await screen.findByText("You're all caught up.")).toBeInTheDocument();
});

test("the notifications page can show only unread ones", async () => {
  const api = inboxApi();
  renderAt(<App />, "/notifications");
  const user = userEvent.setup();

  await screen.findByRole("heading", { name: "Notifications" });
  await user.click(screen.getByRole("radio", { name: "Unread" }));

  await waitFor(() => expect(api.listQueries.at(-1)?.get("unread")).toBe("true"));
});
