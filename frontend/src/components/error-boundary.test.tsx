import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, Route, Routes } from "react-router";

import { renderAt } from "../test/render";
import { AppErrorBoundary, PageErrorBoundary } from "./ErrorBoundary";

function Broken(): never {
  throw new Error("secret internal detail");
}

function Frame() {
  return (
    <>
      <Link to="/fine">Somewhere else</Link>
      <PageErrorBoundary>
        <Routes>
          <Route path="/broken" element={<Broken />} />
          <Route path="/fine" element={<p>All good here</p>} />
        </Routes>
      </PageErrorBoundary>
    </>
  );
}

beforeEach(() => vi.spyOn(console, "error").mockImplementation(() => undefined)); // React logs the caught error

test("a page that crashes shows a way out, without the internal details", async () => {
  renderAt(<Frame />, "/broken");

  expect(await screen.findByRole("heading", { name: "Something went wrong on this page" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reload the page" })).toBeInTheDocument();
  expect(screen.queryByText(/secret internal detail/)).not.toBeInTheDocument();
});

test("going to another page clears the error", async () => {
  renderAt(<Frame />, "/broken");
  await screen.findByRole("heading", { name: "Something went wrong on this page" });

  await userEvent.click(screen.getByRole("link", { name: "Somewhere else" }));

  expect(await screen.findByText("All good here")).toBeInTheDocument();
});

test("the last-resort boundary offers a reload", async () => {
  const reload = vi.fn();
  vi.stubGlobal("location", { ...window.location, reload });
  renderAt(
    <AppErrorBoundary>
      <Broken />
    </AppErrorBoundary>,
  );

  await userEvent.click(await screen.findByRole("button", { name: "Reload" }));

  expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
  expect(reload).toHaveBeenCalled();
  vi.unstubAllGlobals();
});
