import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ApiError } from "./api/client";
import { cssVariablesResolver, theme } from "./theme";

/** A 4xx won't succeed on a retry, and a timeout already waited long enough; only network blips and 5xx are
 * worth one more try. */
export function shouldRetry(failureCount: number, error: unknown) {
  if (error instanceof ApiError && (error.code === "timeout" || (error.status > 0 && error.status < 500))) return false;
  return failureCount < 1;
}

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, staleTime: 30_000, refetchOnWindowFocus: true },
      mutations: { retry: false }, // writes are retried by the user, with the same idempotency key
    },
  });
}

/** Everything the app needs around it: theme, notifications and the server-state cache. The router is
 * added by the caller: the browser's history in the app, an in-memory one in tests. */
export function Providers({ children, env }: { children: ReactNode; env?: "test" }) {
  const [queryClient] = useState(createQueryClient);
  return (
    <MantineProvider theme={theme} cssVariablesResolver={cssVariablesResolver} defaultColorScheme="auto" env={env}>
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MantineProvider>
  );
}
