import { ApiError } from "../api/client";
import { looksLikeEmail, signInError } from "./LoginPage";

test.each([
  ["ops1@example.com", true],
  ["a@b.co", true],
  ["no-at-sign.example.com", false],
  ["@example.com", false],
  ["name@nodot", false],
  ["name@.com", false],
  ["name@example.", false],
  ["two words@example.com", false],
])("%s looks like an email: %s", (value, expected) => {
  expect(looksLikeEmail(value)).toBe(expected);
});

test("a hostile input is checked in linear time", () => {
  const started = performance.now();
  looksLikeEmail(`${"a@".repeat(50_000)}!`);
  expect(performance.now() - started).toBeLessThan(50);
});

test("throttling is said in minutes, rounded up", () => {
  const throttled = new ApiError(429, "throttled", "Request was throttled. Expected available in 61 seconds.");

  expect(signInError(throttled)).toBe("Too many attempts. Try again in 2 minutes.");
});

test("a server error doesn't leak its message", () => {
  expect(signInError(new ApiError(500, "server_error", "Traceback ..."))).toMatch(/couldn't reach the server/);
});
