import { http, HttpResponse } from "msw";

import { server } from "../test/server";
import { ApiError, api, buildUrl, setAccessToken, setSessionExpiredHandler } from "./client";

const error = (status: number, code: string, message = "x", details?: unknown) =>
  HttpResponse.json({ error: { code, message, details } }, { status });

test("sends the access token as a bearer token", async () => {
  setAccessToken("token-1");
  server.use(
    http.get("/api/auth/me/", ({ request }) =>
      HttpResponse.json({ auth: request.headers.get("Authorization") }),
    ),
  );

  expect(await api("/api/auth/me/")).toEqual({ auth: "Bearer token-1" });
});

test("on a 401 it refreshes the session once and retries with the new token", async () => {
  setAccessToken("expired");
  server.use(
    http.post("/api/auth/refresh/", () => HttpResponse.json({ access: "fresh" })),
    http.get("/api/requests/", ({ request }) =>
      request.headers.get("Authorization") === "Bearer fresh"
        ? HttpResponse.json({ count: 0 })
        : error(401, "token_not_valid"),
    ),
  );

  expect(await api("/api/requests/")).toEqual({ count: 0 });
});

test("simultaneous 401s share a single refresh", async () => {
  setAccessToken("expired");
  let refreshes = 0;
  server.use(
    http.post("/api/auth/refresh/", () => {
      refreshes += 1;
      return HttpResponse.json({ access: "fresh" });
    }),
    http.get("/api/*", ({ request }) =>
      request.headers.get("Authorization") === "Bearer fresh"
        ? HttpResponse.json({})
        : error(401, "token_not_valid"),
    ),
  );

  await Promise.all([api("/api/requests/"), api("/api/episodes/"), api("/api/analytics/")]);

  expect(refreshes).toBe(1);
});

test("when the refresh fails too, the session is over", async () => {
  const expired = vi.fn();
  setSessionExpiredHandler(expired);
  server.use(
    http.post("/api/auth/refresh/", () => error(401, "not_authenticated")),
    http.get("/api/requests/", () => error(401, "token_not_valid")),
  );

  await expect(api("/api/requests/")).rejects.toMatchObject({ status: 401 });
  expect(expired).toHaveBeenCalledOnce();
});

test("public auth endpoints never trigger a refresh", async () => {
  const refresh = vi.fn(() => HttpResponse.json({ access: "x" }));
  server.use(
    http.post("/api/auth/refresh/", refresh),
    http.post("/api/auth/login/", () => error(401, "invalid_credentials", "Email or password is incorrect.")),
  );

  await expect(api("/api/auth/login/", { method: "POST", body: {}, anonymous: true })).rejects.toThrow(
    "Email or password is incorrect.",
  );
  expect(refresh).not.toHaveBeenCalled();
});

test("errors keep the API's code and field details", async () => {
  server.use(
    http.post("/api/requests/", () =>
      error(400, "invalid", "Some fields are invalid.", { deadline: ["Can't be in the past.", "Required."] }),
    ),
  );

  const failure = await api("/api/requests/", { method: "POST", body: {} }).catch((e: unknown) => e);

  expect(failure).toBeInstanceOf(ApiError);
  expect((failure as ApiError).code).toBe("invalid");
  expect((failure as ApiError).fieldErrors()).toEqual({ deadline: "Can't be in the past. Required." });
});

test("an error that isn't JSON still becomes a readable ApiError", async () => {
  server.use(http.get("/api/requests/", () => new HttpResponse("<html>Bad gateway</html>", { status: 502 })));

  await expect(api("/api/requests/")).rejects.toMatchObject({ status: 502, code: "unexpected_response" });
});

test("query strings skip empty values and repeat lists", () => {
  expect(buildUrl("/api/episodes/", { quality: ["good", "usable"], task_name: "", page: 2 })).toBe(
    "/api/episodes/?quality=good&quality=usable&page=2",
  );
});
