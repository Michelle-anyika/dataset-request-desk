import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";

import { Providers } from "../Providers";

/** Render with the app's own providers, at the given URL. */
export function renderAt(ui: ReactElement, url = "/") {
  return render(
    <Providers>
      <MemoryRouter initialEntries={[url]}>{ui}</MemoryRouter>
    </Providers>,
  );
}
