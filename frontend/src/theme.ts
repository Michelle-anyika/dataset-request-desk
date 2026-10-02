import { createTheme, Modal, Notification, type CSSVariablesResolver, type MantineColorsTuple } from "@mantine/core";

// Brand: a deep red. Errors and destructive actions keep Mantine's brighter `red`, always with an icon and
// text, so the brand colour is never mistaken for "something went wrong".
const brand: MantineColorsTuple = [
  "#fcebec",
  "#f4d4d6",
  "#e8a7ab",
  "#dc777d",
  "#d14f56",
  "#c9363e",
  "#b52a31",
  "#9f2129",
  "#8a1c23",
  "#6f141a",
];

// Neutral blacks for dark mode (Mantine's default dark palette has a blue tint).
const dark: MantineColorsTuple = [
  "#c9c9c9",
  "#b8b8b8",
  "#828282",
  "#696969",
  "#424242",
  "#3b3b3b",
  "#2e2e2e",
  "#242424",
  "#1c1c1c",
  "#121212",
];

export const theme = createTheme({
  primaryColor: "brand",
  // White text on these shades passes WCAG AA comfortably (about 9:1 in light mode, 6:1 in dark mode).
  primaryShade: { light: 8, dark: 6 },
  colors: { brand, dark },
  fontFamily:
    "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  headings: { fontWeight: "650" },
  defaultRadius: "md",
  cursorType: "pointer",
  components: {
    Modal: Modal.extend({ defaultProps: { closeButtonProps: { "aria-label": "Close dialog" } } }),
    // Toasts: a named close button, and description text at full contrast.
    Notification: Notification.extend({
      defaultProps: { closeButtonProps: { "aria-label": "Close notification" } },
      styles: { description: { color: "var(--mantine-color-text)" } },
    }),
  },
});

// WCAG AA contrast (4.5:1 for text). Mantine's defaults for dimmed text (3.3:1) and for the text of light
// badges (as low as 1.7:1 for yellow) fail it; these pass, measured on the badge's own tinted background.
// Found by the axe checks in the end-to-end tests (e2e/).
export const ACCESSIBLE_TEXT = {
  gray: "#495057",
  teal: "#06694b",
  blue: "#1864ab",
  violet: "#5f3dc4",
  orange: "#9a3412",
  yellow: "#8a5a00",
  red: "#c92a2a",
  brand: "#8a1c23",
} as const;

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {},
  light: {
    "--mantine-color-dimmed": ACCESSIBLE_TEXT.gray,
    "--mantine-color-placeholder": "#6b7280", // 4.8:1 on white
    ...Object.fromEntries(
      Object.entries(ACCESSIBLE_TEXT).map(([color, text]) => [`--mantine-color-${color}-light-color`, text]),
    ),
  },
  dark: { "--mantine-color-dimmed": "#b8b8b8", "--mantine-color-placeholder": "#9ca3af" }, // 7.8:1 and 6:1
});
