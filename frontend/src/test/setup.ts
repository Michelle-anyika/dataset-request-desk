import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";

import { setAccessToken } from "../api/client";
import { server } from "./server";

// Coverage instrumentation and CI runners are slower than a laptop: wait up to 3 s for elements to appear.
configure({ asyncUtilTimeout: 3000 });

// Any request without a handler fails the test: nothing reaches a real network.
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  setAccessToken(null);
});
afterAll(() => server.close());

// jsdom lacks the browser APIs Mantine uses for colour scheme and responsive layout.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});
window.HTMLElement.prototype.scrollIntoView = () => {};
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverStub;
