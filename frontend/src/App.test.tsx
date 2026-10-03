import { screen } from "@testing-library/react";

import { App } from "./App";
import { noSession, sessionFor, client } from "./test/fixtures";
import { renderAt } from "./test/render";
import { server } from "./test/server";

test("a visitor first sees what the platform is, and how to sign in", async () => {
  server.use(noSession());

  renderAt(<App />, "/");

  expect(
    await screen.findByRole("heading", { name: "Request, assign and deliver robot training data in one place." }),
  ).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Who it's for" })).toBeInTheDocument();
  expect(screen.getByText(/there is no public sign-up/)).toBeInTheDocument();
  for (const link of screen.getAllByRole("link", { name: "Sign in" })) expect(link).toHaveAttribute("href", "/login");
});

test("a signed-in user skips the landing page", async () => {
  server.use(...sessionFor(client));

  renderAt(<App />, "/");

  expect(await screen.findByRole("heading", { name: "My requests" })).toBeInTheDocument();
});

test("the sign-in page says what it signs in to, and how to get an account", async () => {
  server.use(noSession());

  renderAt(<App />, "/login");

  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  expect(screen.getByText(/No account\? Your administrator creates accounts/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "About the platform" })).toHaveAttribute("href", "/");
});

test("an unknown address shows a not-found page", async () => {
  server.use(...sessionFor(client));

  renderAt(<App />, "/no/such/page");

  expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
});
