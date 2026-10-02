import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { App } from "../App";
import { admin, apiError, operator, page, sessionFor } from "../test/fixtures";
import { renderAt } from "../test/render";
import { server } from "../test/server";

const managed = (overrides = {}) => ({
  id: "44444444-4444-4444-8444-444444444444",
  email: "client-a@example.com",
  full_name: "Carla Client",
  role: "client",
  organisation: "Acme Robotics",
  is_active: true,
  last_login: "2026-10-01T09:00:00Z",
  created_at: "2026-09-01T09:00:00Z",
  ...overrides,
});
const me = managed({ id: admin.id, email: admin.email, full_name: admin.full_name, role: "admin", organisation: "" });

function usersApi(users = [managed(), me]) {
  const state = { queries: [] as URLSearchParams[], created: [] as unknown[], patched: [] as unknown[], keys: [] as (string | null)[] };
  server.use(
    ...sessionFor(admin),
    http.get("/api/users/", ({ request }) => {
      state.queries.push(new URL(request.url).searchParams);
      return HttpResponse.json(page(users));
    }),
    http.post("/api/users/", async ({ request }) => {
      state.created.push(await request.json());
      state.keys.push(request.headers.get("Idempotency-Key"));
      return HttpResponse.json(managed({ id: "55555555-5555-4555-8555-555555555555", email: "new@example.com" }), { status: 201 });
    }),
    http.patch("/api/users/:id/", async ({ request, params }) => {
      const body = (await request.json()) as Record<string, unknown>;
      state.patched.push(body);
      return HttpResponse.json({ ...managed({ id: params.id }), ...body });
    }),
  );
  return state;
}

test("lists accounts with their role and status", async () => {
  usersApi([managed(), managed({ id: "6", email: "old@example.com", full_name: "Old Op", role: "operator", is_active: false }), me]);

  renderAt(<App />, "/users");

  const rows = within(await screen.findByRole("table")).getAllByRole("row");
  expect(rows[1]).toHaveTextContent(/Carla Client.*client-a@example.com.*Acme Robotics.*Client.*Active/);
  expect(rows[2]).toHaveTextContent(/Old Op.*Operator.*Deactivated/);
});

test("searches by name or email", async () => {
  const api = usersApi();
  renderAt(<App />, "/users");
  const user = userEvent.setup();

  await user.type(await screen.findByRole("searchbox", { name: /search/i }), "carla");

  await waitFor(() => expect(api.queries.at(-1)?.get("search")).toBe("carla"));
});

test("creates an account, sending it once", async () => {
  const api = usersApi();
  renderAt(<App />, "/users");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "New user" }));
  const dialog = await screen.findByRole("dialog");
  await user.type(within(dialog).getByLabelText(/email/i), "new@example.com");
  await user.type(within(dialog).getByLabelText(/full name/i), "Nia New");
  await user.selectOptions(within(dialog).getByLabelText(/role/i), "operator");
  await user.type(within(dialog).getByLabelText(/^password/i, { selector: "input" }), "a-long-enough-password");
  await user.click(within(dialog).getByRole("button", { name: "Create user" }));

  await waitFor(() =>
    expect(api.created).toEqual([
      { email: "new@example.com", full_name: "Nia New", role: "operator", organisation: "", password: "a-long-enough-password" },
    ]),
  );
  expect(api.keys[0]).toMatch(/^[0-9a-f-]{36}$/);
});

test("the password policy's reasons appear on the password field", async () => {
  usersApi();
  server.use(
    http.post("/api/users/", () =>
      apiError(400, "invalid", "Some fields are invalid.", { password: ["This password is too common."] }),
    ),
  );
  renderAt(<App />, "/users");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "New user" }));
  const dialog = await screen.findByRole("dialog");
  await user.type(within(dialog).getByLabelText(/email/i), "new@example.com");
  await user.type(within(dialog).getByLabelText(/full name/i), "Nia New");
  await user.type(within(dialog).getByLabelText(/^password/i, { selector: "input" }), "password1234");
  await user.click(within(dialog).getByRole("button", { name: "Create user" }));

  expect(await within(dialog).findByText("This password is too common.")).toBeInTheDocument();
});

test("editing sends only what changed", async () => {
  const api = usersApi();
  renderAt(<App />, "/users");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Edit Carla Client" }));
  const dialog = await screen.findByRole("dialog");
  await user.selectOptions(within(dialog).getByLabelText(/role/i), "operator");
  await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

  await waitFor(() => expect(api.patched).toEqual([{ role: "operator" }]));
});

test("an account can be deactivated", async () => {
  const api = usersApi();
  renderAt(<App />, "/users");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Edit Carla Client" }));
  const dialog = await screen.findByRole("dialog");
  await user.click(within(dialog).getByRole("switch", { name: /active/i }));
  await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

  await waitFor(() => expect(api.patched).toEqual([{ is_active: false }]));
});

test("the API's protection of the last admin is explained", async () => {
  usersApi();
  server.use(
    http.patch("/api/users/:id/", () =>
      apiError(409, "last_active_admin", "This is the last active admin; make someone else an admin first."),
    ),
  );
  renderAt(<App />, "/users");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Edit Carla Client" }));
  const dialog = await screen.findByRole("dialog");
  await user.selectOptions(within(dialog).getByLabelText(/role/i), "operator");
  await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent("make someone else an admin first");
});

test("your own role and access can't be changed here", async () => {
  usersApi();
  renderAt(<App />, "/users");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: `Edit ${admin.full_name}` }));
  const dialog = await screen.findByRole("dialog");

  expect(within(dialog).getByLabelText(/role/i)).toBeDisabled();
  expect(within(dialog).getByRole("switch", { name: /active/i })).toBeDisabled();
  expect(within(dialog).getByText(/ask another admin/i)).toBeInTheDocument();
});

test("operators can't open user management", async () => {
  server.use(...sessionFor(operator));

  renderAt(<App />, "/users");

  expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
});
