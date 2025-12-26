/**
 * MUI theme:
 * - <= 3 primary tones (primary/secondary/background)
 * - Typography hierarchy for title/body/helper text
 * - Animation duration capped at 300ms
 */
import React, { PropsWithChildren } from "react";
import { ThemeProvider, createTheme } from "@mui/material/styles";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#3949ab" },
    secondary: { main: "#00897b" },
    background: { default: "#f5f7fb" }
  },
  typography: {
    h4: { fontWeight: 700 },
    h5: { fontWeight: 700 }
  },
  transitions: {
    duration: {
      shortest: 120,
      shorter: 160,
      short: 200,
      standard: 240,
      complex: 300
    }
  }
});

export function AppThemeProvider({ children }: PropsWithChildren) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}