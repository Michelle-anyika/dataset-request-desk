import { MantineProvider } from "@mantine/core";
import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";

import { createQueryClient } from "../Providers";
import { theme } from "../theme";

/** Render with the app's providers, at the given URL. */
export function renderAt(ui: ReactElement, url = "/") {
  return render(
    <MantineProvider theme={theme}>
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={[url]}>{ui}</MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}
