import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { App } from "../App";
import type { DatasetRequest } from "../api/types";
import { apiError, client, makeRequest, operator, page, sessionFor } from "../test/fixtures";
import { renderAt } from "../test/render";
import { server } from "../test/server";

const request = makeRequest({ status: "in_progress", task_name: "pick cup", episodes_requested: 8, assigned_count: 3 });
const url = `/requests/${request.id}/assign`;

function episode(n: number, overrides = {}) {
  return {
    id: n,
    episode_id: `EP-${String(n).padStart(5, "0")}`,
    robot_id: "arm-01",
    task_name: "pick cup",
    recorded_at: "2026-09-01T10:00:00Z",
    duration_seconds: 30,
    operator_name: "Aline",
    quality: "good",
    assigned_request: null,
    ...overrides,
  };
}

function assigned(n: number) {
  const { episode_id, robot_id, task_name, recorded_at, duration_seconds, quality } = episode(n);
  return {
    episode: { episode_id, robot_id, task_name, recorded_at, duration_seconds, quality },
    assigned_at: "2026-09-30T10:00:00Z",
    assigned_by: { full_name: "Olu Operator", role: "operator" },
    released_at: null,
    released_by: { full_name: "", role: "operator" },
  };
}

/** A small in-memory API: assigning and removing change what the next reads return. */
function fakeApi(current: DatasetRequest = request) {
  const state = { request: { ...current }, assigned: [assigned(91), assigned(92), assigned(93)], episodeQueries: [] as URLSearchParams[], posted: [] as { ids: string[]; key: string | null }[], removed: [] as string[] };
  server.use(
    ...sessionFor(operator),
    http.get(`/api/requests/${current.id}/`, () => HttpResponse.json(state.request)),
    http.get(`/api/requests/${current.id}/assignments/`, () => HttpResponse.json(page(state.assigned))),
    http.get("/api/episodes/", ({ request: http }) => {
      state.episodeQueries.push(new URL(http.url).searchParams);
      return HttpResponse.json(page([episode(1), episode(2), episode(3, { quality: "usable", robot_id: "arm-02" })]));
    }),
    http.post(`/api/requests/${current.id}/assignments/`, async ({ request: http }) => {
      const { episode_ids } = (await http.json()) as { episode_ids: string[] };
      state.posted.push({ ids: episode_ids, key: http.headers.get("Idempotency-Key") });
      state.assigned.push(...episode_ids.map((id) => assigned(Number(id.slice(3)))));
      state.request.assigned_count += episode_ids.length;
      return HttpResponse.json(
        { assigned: episode_ids, assigned_count: state.request.assigned_count, episodes_requested: 8 },
        { status: 201 },
      );
    }),
    http.delete(`/api/requests/${current.id}/assignments/:episodeId/`, ({ params }) => {
      state.removed.push(String(params.episodeId));
      state.assigned = state.assigned.filter((row) => row.episode.episode_id !== params.episodeId);
      state.request.assigned_count -= 1;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return state;
}

test("offers only episodes that can be assigned: this task, good or usable, not held elsewhere", async () => {
  const api = fakeApi();

  renderAt(<App />, url);

  expect(await screen.findByRole("cell", { name: "EP-00001" })).toBeInTheDocument();
  const query = api.episodeQueries.at(-1);
  expect(query?.get("task_name")).toBe("pick cup");
  expect(query?.getAll("quality")).toEqual(["good", "usable"]);
  expect(query?.get("available")).toBe("true");
  expect(screen.getByText("3 of 8 assigned")).toBeInTheDocument();
});

test("assigns the selected episodes in one call, and the progress follows", async () => {
  const api = fakeApi();
  renderAt(<App />, url);
  const user = userEvent.setup();

  await user.click(await screen.findByRole("checkbox", { name: "Select EP-00001" }));
  await user.click(screen.getByRole("checkbox", { name: "Select EP-00003" }));
  await user.click(screen.getByRole("button", { name: "Assign 2 episodes" }));

  expect(await screen.findByText("5 of 8 assigned")).toBeInTheDocument();
  expect(api.posted).toHaveLength(1);
  expect(api.posted[0]?.ids).toEqual(["EP-00001", "EP-00003"]);
  expect(api.posted[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
});

test("can select just the number still needed", async () => {
  fakeApi(makeRequest({ ...request, assigned_count: 6 }));
  renderAt(<App />, url);
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Select the 2 still needed" }));

  expect(screen.getByRole("button", { name: "Assign 2 episodes" })).toBeEnabled();
});

test("explains episodes another request already holds", async () => {
  fakeApi();
  server.use(
    http.post(`/api/requests/${request.id}/assignments/`, () =>
      apiError(409, "episodes_already_assigned", "Some episodes are already assigned to a request. Nothing was assigned.", {
        "EP-00001": "bbbbbbbb-0000-4000-8000-000000000009",
      }),
    ),
  );
  renderAt(<App />, url);
  const user = userEvent.setup();

  await user.click(await screen.findByRole("checkbox", { name: "Select EP-00001" }));
  await user.click(screen.getByRole("button", { name: "Assign 1 episode" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Nothing was assigned");
  expect(alert).toHaveTextContent("EP-00001");
  expect(within(alert).getByRole("link", { name: /another request/i })).toHaveAttribute(
    "href",
    "/requests/bbbbbbbb-0000-4000-8000-000000000009",
  );
});

test("lists every reason an assignment was refused", async () => {
  fakeApi();
  server.use(
    http.post(`/api/requests/${request.id}/assignments/`, () =>
      apiError(400, "episodes_not_assignable", "Some episodes can't be assigned to this request. Nothing was assigned.", {
        bad_quality: ["EP-00002"],
        task_mismatch: ["EP-00003"],
      }),
    ),
  );
  renderAt(<App />, url);
  const user = userEvent.setup();

  await user.click(await screen.findByRole("checkbox", { name: "Select EP-00002" }));
  await user.click(screen.getByRole("checkbox", { name: "Select EP-00003" }));
  await user.click(screen.getByRole("button", { name: "Assign 2 episodes" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/bad quality.*EP-00002/i);
  expect(alert).toHaveTextContent(/recorded for another task.*EP-00003/i);
});

test("an assigned episode can be removed", async () => {
  const api = fakeApi();
  renderAt(<App />, url);
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Remove EP-00091" }));

  expect(await screen.findByText("2 of 8 assigned")).toBeInTheDocument();
  expect(api.removed).toEqual(["EP-00091"]);
});

test("the robot filter narrows the list", async () => {
  const api = fakeApi();
  renderAt(<App />, url);
  const user = userEvent.setup();
  await screen.findByRole("cell", { name: "EP-00001" });

  await user.selectOptions(screen.getByLabelText("Robot"), "arm-02");

  await waitFor(() => expect(api.episodeQueries.at(-1)?.get("robot_id")).toBe("arm-02"));
});

test("episodes can only change while the request is in progress", async () => {
  fakeApi(makeRequest({ ...request, status: "delivered" }));

  renderAt(<App />, url);

  expect(await screen.findByText(/only be changed while the request is in progress/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^assign/i })).not.toBeInTheDocument();
});

test("clients can't open it", async () => {
  server.use(...sessionFor(client));

  renderAt(<App />, url);

  expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
});

test("when another operator takes episodes first, the list refreshes and keeps the rest of the selection", async () => {
  const api = fakeApi();
  server.use(
    http.post(`/api/requests/${request.id}/assignments/`, () =>
      apiError(409, "episodes_already_assigned", "Some episodes are already assigned to a request. Nothing was assigned.", {
        "EP-00001": "bbbbbbbb-0000-4000-8000-000000000009",
      }),
    ),
  );
  renderAt(<App />, url);
  const user = userEvent.setup();

  await user.click(await screen.findByRole("checkbox", { name: "Select EP-00001" }));
  await user.click(screen.getByRole("checkbox", { name: "Select EP-00002" }));
  const loadsBefore = api.episodeQueries.length;
  await user.click(screen.getByRole("button", { name: "Assign 2 episodes" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/list is up to date/i);
  await waitFor(() => expect(api.episodeQueries.length).toBeGreaterThan(loadsBefore));
  expect(screen.getByRole("button", { name: "Assign 1 episode" })).toBeEnabled();
  expect(screen.getByRole("checkbox", { name: "Select EP-00002" })).toBeChecked();
});
