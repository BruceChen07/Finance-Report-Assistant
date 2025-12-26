/**
 * Application entry:
 * - Mounts React.
 * - Wraps global providers: Theme, UI (loading/toast), Auth (JWT).
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline } from "@mui/material";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AppThemeProvider } from "./styles/app-theme";
import { AuthProvider } from "./components/providers/AuthProvider";
import { UiProvider } from "./components/providers/UiProvider";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppThemeProvider>
      <CssBaseline />
      <UiProvider>
        <AuthProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AuthProvider>
      </UiProvider>
    </AppThemeProvider>
  </React.StrictMode>
);