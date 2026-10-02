import { screen } from "@testing-library/react";

import { App } from "./App";
import { renderAt } from "./test/render";

test("the home page names the product", () => {
  renderAt(<App />);

  expect(screen.getByRole("heading", { name: "Dataset Request Desk" })).toBeInTheDocument();
});

test("an unknown address shows a not-found page", () => {
  renderAt(<App />, "/no/such/page");

  expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
});
