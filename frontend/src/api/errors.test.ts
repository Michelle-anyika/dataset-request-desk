import { http, HttpResponse, delay } from "msw";

import { server } from "../test/server";
import { api, ApiError } from "./client";
import { describeError, loadErrorHint } from "./errors";

test.each([
  [new ApiError(0, "network", "x"), /couldn't reach the server/],
  [new ApiError(0, "timeout", "x"), /took too long/],
  [new ApiError(403, "permission_denied", "x"), /account isn't allowed/],
  [new ApiError(429, "throttled", "Request was throttled. Expected available in 61 seconds."), /Too many requests\. Try again in 2 minutes\./],
  [new ApiError(500, "server_error", "Traceback (most recent call last) ..."), /went wrong on our side/],
  [new ApiError(409, "invalid_transition", "This request was already delivered."), /^This request was already delivered\.$/],
  [new Error("anything else"), /couldn't reach the server/],
])("%s is described for people", (error, expected) => {
  expect(describeError(error)).toMatch(expected);
});

test("a server error never shows its internal message", () => {
  expect(describeError(new ApiError(502, "bad_gateway", "upstream connect error"))).not.toMatch(/upstream/);
});

test("a failed load says what to do, by cause", () => {
  expect(loadErrorHint(new ApiError(0, "network", "x"))).toMatch(/connection/);
  expect(loadErrorHint(new ApiError(403, "permission_denied", "x"))).toMatch(/access/);
  expect(loadErrorHint(new ApiError(503, "unavailable", "x"))).toMatch(/moment/);
});

test("a request with no answer gives up after its timeout", async () => {
  server.use(http.get("/api/slow/", async () => {
    await delay("infinite");
    return HttpResponse.json({});
  }));

  const failure = await api("/api/slow/", { timeoutMs: 50 }).catch((error: unknown) => error);

  expect(failure).toBeInstanceOf(ApiError);
  expect(failure).toMatchObject({ status: 0, code: "timeout" });
});

test("no connection at all becomes a network ApiError", async () => {
  server.use(http.get("/api/offline/", () => HttpResponse.error()));

  await expect(api("/api/offline/")).rejects.toMatchObject({ status: 0, code: "network" });
});
