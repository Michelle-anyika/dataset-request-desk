import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { App } from "../App";
import { renderAt } from "../test/render";
import { server } from "../test/server";
import { admin, apiError, client, noSession, operator, page, sessionFor } from "../test/fixtures";

// The pages behind sign-in load their data; these tests are about getting there.
beforeEach(() => server.use(http.get("/api/requests/", () => HttpResponse.json(page([])))));

async function signIn(email: string, password = "a-good-password") {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText(/email/i), email);
  await user.type(screen.getByLabelText(/^password/i, { selector: "input" }), password);
  await user.click(screen.getByRole("button", { name: /sign in/i }));
  return user;
}

describe("signing in", () => {
  test("a protected page sends a visitor without a session to the sign-in page", async () => {
    server.use(noSession());

    renderAt(<App />, "/requests");

    expect(await screen.findByRole("heading", { name: /sign in/i })).toBeInTheDocument();
  });

  test("a client lands on their requests", async () => {
    server.use(noSession(), http.post("/api/auth/login/", () => HttpResponse.json({ access: "a", user: client })));
    renderAt(<App />, "/login");

    await signIn(client.email);

    expect(await screen.findByRole("heading", { name: "My requests" })).toBeInTheDocument();
  });

  test("a slow check for an earlier session can't undo a sign-in that finished first", async () => {
    let answerSessionCheck: () => void = () => undefined;
    server.use(
      // The page's first question, "is there still a session?", answers only after the user has signed in.
      http.post("/api/auth/refresh/", async () => {
        await new Promise<void>((resolve) => (answerSessionCheck = resolve));
        return apiError(401, "not_authenticated", "No active session.");
      }),
      http.post("/api/auth/login/", () => HttpResponse.json({ access: "a", user: client })),
    );
    renderAt(<App />, "/login");

    await signIn(client.email);
    expect(await screen.findByRole("heading", { name: "My requests" })).toBeInTheDocument();
    answerSessionCheck();

    // Still signed in: the late "no session" answer is about the time before signing in.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByRole("heading", { name: "My requests" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument();
  });

  test("operators and admins land on the request queue", async () => {
    server.use(noSession(), http.post("/api/auth/login/", () => HttpResponse.json({ access: "a", user: operator })));
    renderAt(<App />, "/login");

    await signIn(operator.email);

    expect(await screen.findByRole("heading", { name: "Request queue" })).toBeInTheDocument();
  });

  test("after signing in, the page that was asked for opens", async () => {
    server.use(noSession(), http.post("/api/auth/login/", () => HttpResponse.json({ access: "a", user: client })));
    renderAt(<App />, "/requests?status=delivered");
    await screen.findByRole("heading", { name: /sign in/i });

    await signIn(client.email);

    expect(await screen.findByRole("heading", { name: "My requests" })).toBeInTheDocument();
  });

  test("wrong credentials show the API's message", async () => {
    server.use(
      noSession(),
      http.post("/api/auth/login/", () => apiError(401, "invalid_credentials", "Email or password is incorrect.")),
    );
    renderAt(<App />, "/login");

    await signIn(client.email, "wrong-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
  });

  test("too many attempts say how long to wait", async () => {
    server.use(
      noSession(),
      http.post("/api/auth/login/", () =>
        apiError(429, "throttled", "Request was throttled. Expected available in 540 seconds."),
      ),
    );
    renderAt(<App />, "/login");

    await signIn(client.email);

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many attempts.*9 minutes/i);
  });

  test("the form checks the fields before calling the API", async () => {
    const login = vi.fn();
    server.use(noSession(), http.post("/api/auth/login/", login));
    renderAt(<App />, "/login");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });
});

describe("an existing session", () => {
  test("survives a page reload through the refresh cookie", async () => {
    server.use(...sessionFor(client));

    renderAt(<App />, "/requests");

    expect(await screen.findByRole("heading", { name: "My requests" })).toBeInTheDocument();
  });

  test("an already signed-in user skips the sign-in page", async () => {
    server.use(...sessionFor(operator));

    renderAt(<App />, "/login");

    expect(await screen.findByRole("heading", { name: "Request queue" })).toBeInTheDocument();
  });
});

describe("navigation", () => {
  test("shows only the pages for the user's role", async () => {
    server.use(...sessionFor(client));
    renderAt(<App />, "/requests");

    const nav = await screen.findByRole("navigation", { name: "Main" });

    expect(nav).toHaveTextContent("My requests");
    expect(nav).not.toHaveTextContent("Users");
  });

  test("admins also see user management", async () => {
    server.use(...sessionFor(admin));
    renderAt(<App />, "/requests");

    expect(await screen.findByRole("navigation", { name: "Main" })).toHaveTextContent("Users");
  });

  test("a page for another role is not available", async () => {
    server.use(...sessionFor(client));

    renderAt(<App />, "/users");

    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});

describe("signing out", () => {
  test("ends the session and returns to the sign-in page", async () => {
    const logout = vi.fn(() => new HttpResponse(null, { status: 204 }));
    server.use(...sessionFor(client), http.post("/api/auth/logout/", logout));
    renderAt(<App />, "/requests");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /account menu/i }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    expect(logout).toHaveBeenCalledOnce();
  });

  test("can end the sessions on every device", async () => {
    const logoutAll = vi.fn(() => new HttpResponse(null, { status: 204 }));
    server.use(...sessionFor(client), http.post("/api/auth/logout-all/", logoutAll));
    renderAt(<App />, "/requests");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /account menu/i }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out of all devices" }));

    await waitFor(() => expect(logoutAll).toHaveBeenCalledOnce());
    expect(await screen.findByRole("heading", { name: /sign in/i })).toBeInTheDocument();
  });

  test("after signing out, the next person starts on their own home page", async () => {
    // Not on the page the previous user was on: an admin signing out of /users must not send a client there.
    server.use(
      ...sessionFor(admin),
      http.get("/api/users/", () => HttpResponse.json(page([]))),
      http.post("/api/auth/logout/", () => new HttpResponse(null, { status: 204 })),
      http.post("/api/auth/login/", () => HttpResponse.json({ access: "a", user: client })),
    );
    renderAt(<App />, "/users");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /account menu/i }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));
    await signIn(client.email);

    expect(await screen.findByRole("heading", { name: "My requests" })).toBeInTheDocument();
  });
});
