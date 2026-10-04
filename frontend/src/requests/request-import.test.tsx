import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { App } from "../App";
import type { RequestImportReport } from "../api/requestImports";
import { admin, apiError, operator, sessionFor } from "../test/fixtures";
import { renderAt } from "../test/render";
import { server } from "../test/server";

const preview: RequestImportReport = {
  create: 2,
  unchanged: 0,
  skip: 1,
  rows: [
    { row: 2, reference: "SR-001", action: "create", reason_code: "", message: "", client_email: "buyer@acme.example", task_name: "pick cup", status: "submitted" },
    { row: 3, reference: "SR-002", action: "create", reason_code: "", message: "", client_email: "buyer@acme.example", task_name: "fold towel", status: "accepted" },
    {
      row: 4,
      reference: "SR-003",
      action: "skip",
      reason_code: "unknown_client",
      message: "No account for nobody@example.com. Create it first.",
      client_email: "nobody@example.com",
      task_name: "open drawer",
      status: "submitted",
    },
  ],
};
const imported: RequestImportReport = { ...preview, rows: preview.rows };

function spreadsheet(name = "requests.csv") {
  return new File(["reference,client_email\n"], name, { type: "text/csv" });
}

/** Mantine's FileInput keeps the real <input type="file"> hidden next to its button. Throws until it exists,
 * so `waitFor(fileInput)` waits for the page to render. */
function fileInput() {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("no file input");
  return input;
}

test("an admin previews the spreadsheet, sees each row's outcome, then imports it once", async () => {
  const commits: (string | null)[] = [];
  server.use(
    ...sessionFor(admin),
    http.post("/api/request-imports/preview/", () => HttpResponse.json(preview)),
    http.post("/api/request-imports/", ({ request }) => {
      commits.push(request.headers.get("Idempotency-Key"));
      return HttpResponse.json(imported, { status: 201 });
    }),
  );
  renderAt(<App />, "/request-imports");
  const user = userEvent.setup();

  await user.upload(await waitFor(fileInput), spreadsheet());
  await user.click(screen.getByRole("button", { name: "Preview" }));

  expect(await screen.findByText("2 requests to create")).toBeInTheDocument();
  expect(screen.getByText("1 skipped")).toBeInTheDocument();
  const skipped = screen.getByRole("row", { name: /SR-003/ });
  expect(within(skipped).getByText("Skipped")).toBeInTheDocument();
  expect(within(skipped).getByText(/No account for nobody@example.com/)).toBeInTheDocument();
  expect(commits).toEqual([]); // the preview saved nothing

  await user.click(screen.getByRole("button", { name: "Import 2 requests" }));

  expect(await screen.findByText("Import finished")).toBeInTheDocument();
  expect(screen.getByText("2 requests created")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "request queue" })).toHaveAttribute("href", "/requests");
  expect(commits).toEqual([expect.stringMatching(/^[0-9a-f-]{36}$/)]);
});

test("nothing can be imported when every row is skipped or imported before", async () => {
  server.use(
    ...sessionFor(admin),
    http.post("/api/request-imports/preview/", () =>
      HttpResponse.json({ ...preview, create: 0, unchanged: 2, rows: preview.rows.map((row) => ({ ...row, action: "unchanged" })) }),
    ),
  );
  renderAt(<App />, "/request-imports");
  const user = userEvent.setup();

  await user.upload(await waitFor(fileInput), spreadsheet());
  await user.click(screen.getByRole("button", { name: "Preview" }));

  expect(await screen.findByRole("button", { name: "Nothing to import" })).toBeDisabled();
  expect(screen.getAllByText("Imported before").length).toBeGreaterThan(0);
});

test("a file the server refuses explains why", async () => {
  server.use(
    ...sessionFor(admin),
    http.post("/api/request-imports/preview/", () =>
      apiError(400, "invalid_file", "Missing required columns: status."),
    ),
  );
  renderAt(<App />, "/request-imports");
  const user = userEvent.setup();

  await user.upload(await waitFor(fileInput), spreadsheet());
  await user.click(screen.getByRole("button", { name: "Preview" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Missing required columns: status.");
});

test("choosing another file clears the old preview", async () => {
  server.use(...sessionFor(admin), http.post("/api/request-imports/preview/", () => HttpResponse.json(preview)));
  renderAt(<App />, "/request-imports");
  const user = userEvent.setup();

  await user.upload(await waitFor(fileInput), spreadsheet());
  await user.click(screen.getByRole("button", { name: "Preview" }));
  await screen.findByText("2 requests to create");

  await user.upload(fileInput(), spreadsheet("other.xlsx"));

  expect(screen.queryByText("2 requests to create")).not.toBeInTheDocument();
});

test("only admins have the page", async () => {
  server.use(...sessionFor(operator));

  renderAt(<App />, "/request-imports");

  expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Migrate requests" })).not.toBeInTheDocument();
});
