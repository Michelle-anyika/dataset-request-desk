import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";

import { Providers } from "../Providers";

/** Render with the app's own providers, at the given URL. */
export function renderAt(ui: ReactElement, url = "/") {
  return render(
    // Mantine's test mode: no transitions, and no hiding popovers whose trigger looks off-screen (in jsdom
    // every element has a zero-size box, so menus would close a moment after opening).
    <Providers env="test">
      <MemoryRouter initialEntries={[url]}>{ui}</MemoryRouter>
    </Providers>,
  );
}
