import { screen } from "@testing-library/react";

import { App } from "./App";
import { noSession, sessionFor, client } from "./test/fixtures";
import { renderAt } from "./test/render";
import { server } from "./test/server";

test("the start page asks a visitor to sign in", async () => {
  server.use(noSession());

  renderAt(<App />, "/");

  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  expect(screen.getByText("Dataset Request Desk")).toBeInTheDocument();
});

test("an unknown address shows a not-found page", async () => {
  server.use(...sessionFor(client));

  renderAt(<App />, "/no/such/page");

  expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
});
