import { createTheme, type MantineColorsTuple } from "@mantine/core";

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
});
