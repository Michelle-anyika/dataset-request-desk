import { setupServer } from "msw/node";

/** Fake API for tests: each test adds the handlers it needs with `server.use(...)`. */
export const server = setupServer();
