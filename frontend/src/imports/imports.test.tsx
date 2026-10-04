import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { App } from "../App";
import { apiError, client, operator, page, sessionFor } from "../test/fixtures";
import { renderAt } from "../test/render";
import { server } from "../test/server";

function batch(overrides = {}) {
  return {
    id: 7,
    file_name: "episodes.csv",
    status: "completed",
    total_rows: 190,
    created_count: 173,
    updated_count: 0,
    unchanged_count: 0,
    skipped_count: 17,
    fixed_count: 9,
    error_message: "",
    previously_imported: false,
    uploaded_by: { full_name: "Olu Operator" },
    started_at: "2026-10-01T10:00:00Z",
    finished_at: "2026-10-01T10:00:02Z",
    ...overrides,
  };
}

const issues = [
  { row_number: 50, episode_id: "EP-00038", severity: "skipped", reason_code: "duplicate_in_file", message: "Same episode as line 38.", raw_row: {} },
  { row_number: 12, episode_id: "EP-00011", severity: "fixed", reason_code: "task_name_normalised", message: "'  Pick Cup ' became 'pick cup'.", raw_row: {} },
];

function fileInput() {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("no file input");
  return input;
}

test("lists previous imports with their results", async () => {
  server.use(
    ...sessionFor(operator),
    http.get("/api/imports/", () =>
      HttpResponse.json(page([batch(), batch({ id: 8, created_count: 0, unchanged_count: 173, previously_imported: true })])),
    ),
  );

  renderAt(<App />, "/imports");

  const rows = within(await screen.findByRole("table")).getAllByRole("row");
  expect(rows[1]).toHaveTextContent("episodes.csv");
  expect(rows[1]).toHaveTextContent("173 created");
  expect(rows[1]).toHaveTextContent("17 skipped");
  expect(rows[2]).toHaveTextContent("Same file as before");
});

test("uploads a CSV with an idempotency key and opens its report", async () => {
  let sent: { type: string | null; key: string | null } | undefined;
  server.use(
    ...sessionFor(operator),
    http.get("/api/imports/", () => HttpResponse.json(page([]))),
    // jsdom's File can't be read back from a multipart body under Node's fetch, so the test checks the
    // request's form, not its bytes (the real upload is covered by the end-to-end tests).
    http.post("/api/imports/", ({ request }) => {
      sent = { type: request.headers.get("Content-Type"), key: request.headers.get("Idempotency-Key") };
      return HttpResponse.json(batch(), { status: 201 });
    }),
    http.get("/api/imports/7/", () => HttpResponse.json(batch())),
    http.get("/api/imports/7/issues/", () => HttpResponse.json(page(issues))),
  );
  renderAt(<App />, "/imports");
  const user = userEvent.setup();

  await screen.findByText("No imports yet");
  await user.upload(fileInput(), new File(["episode_id\n"], "export.csv", { type: "text/csv" }));
  await user.click(screen.getByRole("button", { name: "Import" }));

  expect(await screen.findByRole("heading", { name: "episodes.csv" })).toBeInTheDocument();
  expect(sent?.type).toMatch(/^multipart\/form-data; boundary=/);
  expect(sent?.key).toMatch(/^[0-9a-f-]{36}$/);
});

test("refuses a file that isn't a CSV before uploading it", async () => {
  const upload = vi.fn();
  server.use(...sessionFor(operator), http.get("/api/imports/", () => HttpResponse.json(page([]))), http.post("/api/imports/", upload));
  renderAt(<App />, "/imports");
  const user = userEvent.setup({ applyAccept: false });

  await screen.findByText("No imports yet");
  await user.upload(fileInput(), new File(["x"], "photo.png", { type: "image/png" }));
  await user.click(screen.getByRole("button", { name: "Import" }));

  expect(await screen.findByText("Choose the export as a .csv or .xlsx file.")).toBeInTheDocument();
  expect(upload).not.toHaveBeenCalled();
});

test("shows why the API refused the file", async () => {
  server.use(
    ...sessionFor(operator),
    http.get("/api/imports/", () => HttpResponse.json(page([]))),
    http.post("/api/imports/", () => apiError(400, "invalid_import_file", "The header is missing the column 'quality'.")),
  );
  renderAt(<App />, "/imports");
  const user = userEvent.setup();

  await screen.findByText("No imports yet");
  await user.upload(fileInput(), new File(["x"], "export.csv", { type: "text/csv" }));
  await user.click(screen.getByRole("button", { name: "Import" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("The header is missing the column 'quality'.");
});

describe("an import's report", () => {
  test("shows the counts and every skipped or fixed row with its reason", async () => {
    server.use(
      ...sessionFor(operator),
      http.get("/api/imports/7/", () => HttpResponse.json(batch())),
      http.get("/api/imports/7/issues/", () => HttpResponse.json(page(issues))),
    );

    renderAt(<App />, "/imports/7");

    expect(await screen.findByText("173")).toBeInTheDocument();
    const rows = within(await screen.findByRole("table")).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("50");
    expect(rows[1]).toHaveTextContent("Duplicate in file");
    expect(rows[1]).toHaveTextContent("Same episode as line 38.");
  });

  test("can show only the skipped rows", async () => {
    const severities: (string | null)[] = [];
    server.use(
      ...sessionFor(operator),
      http.get("/api/imports/7/", () => HttpResponse.json(batch())),
      http.get("/api/imports/7/issues/", ({ request }) => {
        severities.push(new URL(request.url).searchParams.get("severity"));
        return HttpResponse.json(page(issues));
      }),
    );
    renderAt(<App />, "/imports/7");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("radio", { name: "Skipped" }));

    await waitFor(() => expect(severities).toContain("skipped"));
  });

  test("a failed import says why", async () => {
    server.use(
      ...sessionFor(operator),
      http.get("/api/imports/9/", () =>
        HttpResponse.json(batch({ id: 9, status: "failed", error_message: "The file is not UTF-8 text." })),
      ),
      http.get("/api/imports/9/issues/", () => HttpResponse.json(page([]))),
    );

    renderAt(<App />, "/imports/9");

    expect(await screen.findByRole("alert")).toHaveTextContent("The file is not UTF-8 text.");
  });
});

test("clients can't open imports", async () => {
  server.use(...sessionFor(client));

  renderAt(<App />, "/imports");

  expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
});

test("an Excel export is accepted and sent as it is", async () => {
  let sent: string | null = null;
  server.use(
    ...sessionFor(operator),
    http.get("/api/imports/", () => HttpResponse.json(page([]))),
    // As above: the multipart body can't be read back here; the backend tests cover parsing the workbook.
    http.post("/api/imports/", ({ request }) => {
      sent = request.headers.get("Content-Type");
      return HttpResponse.json(batch({ file_name: "episodes.xlsx" }), { status: 201 });
    }),
    http.get("/api/imports/7/", () => HttpResponse.json(batch({ file_name: "episodes.xlsx" }))),
    http.get("/api/imports/7/issues/", () => HttpResponse.json(page([]))),
  );
  renderAt(<App />, "/imports");
  const user = userEvent.setup();

  await screen.findByText("No imports yet");
  const xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  await user.upload(fileInput(), new File(["PK"], "episodes.xlsx", { type: xlsx }));
  await user.click(screen.getByRole("button", { name: "Import" }));

  expect(await screen.findByRole("heading", { name: "episodes.xlsx" })).toBeInTheDocument();
  expect(sent).toMatch(/^multipart\/form-data; boundary=/);
});
