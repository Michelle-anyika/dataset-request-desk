import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { theme } from "./theme";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      // A 4xx will not succeed on retry; only network blips and 5xx are worth one more try.
      queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: true },
      mutations: { retry: false },
    },
  });
}

/** Everything the app needs around it: theme, notifications and the server-state cache. The router is
 * added by the caller: the browser's history in the app, an in-memory one in tests. */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);
  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MantineProvider>
  );
}
