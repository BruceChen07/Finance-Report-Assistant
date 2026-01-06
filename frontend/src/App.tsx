/**
 * Root application shell:
 * - Top AppBar + Drawer navigation
 * - Route definitions (pages)
 * - Auth gate (RequireAuth)
 */
import React, { Suspense, useMemo } from "react";
import { Navigate, Route, Routes, useLocation, Link } from "react-router-dom";
import {
  AppBar,
  Box,
  Button,
  Container,
  Divider,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import HistoryIcon from "@mui/icons-material/History";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import LogoutIcon from "@mui/icons-material/Logout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import ConvertPage from "./pages/ConvertPage";
import ResultsPage from "./pages/ResultsPage";
import HistoryPage from "./pages/HistoryPage";
import HelpPage from "./pages/HelpPage";
import { useAuth } from "./components/providers/AuthProvider";
import QaPage from "./pages/QaPage";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const loc = useLocation();
  if (!token)
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return <>{children}</>;
}

export default function App() {
  const { token, username, logout } = useAuth();
  const drawerWidth = 260;

  const navItems = useMemo(
    () => [
      { to: "/", label: "Dashboard", icon: <DashboardIcon /> },
      { to: "/convert", label: "API Call", icon: <UploadFileIcon /> },
      { to: "/results", label: "Results", icon: <CheckCircleOutlineIcon /> },
      { to: "/history", label: "History", icon: <HistoryIcon /> },
      { to: "/qa", label: "Q&A", icon: <HelpOutlineIcon /> },
      { to: "/help", label: "Help", icon: <HelpOutlineIcon /> },
    ],
    []
  );

  return (
    <Box sx={{ display: "flex" }}>
      <AppBar position="fixed" sx={{ zIndex: (t) => t.zIndex.drawer + 1 }}>
        <Toolbar sx={{ gap: 2 }}>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            Finance Report Assistant
          </Typography>
          {token ? (
            <Typography variant="body2">{username || "Signed in"}</Typography>
          ) : null}
          {token ? (
            <Button color="inherit" startIcon={<LogoutIcon />} onClick={logout}>
              Logout
            </Button>
          ) : null}
        </Toolbar>
      </AppBar>

      {token ? (
        <Drawer
          variant="permanent"
          sx={{
            width: drawerWidth,
            flexShrink: 0,
            "& .MuiDrawer-paper": {
              width: drawerWidth,
              boxSizing: "border-box",
            },
          }}
        >
          <Toolbar />
          <Divider />
          <List>
            {navItems.map((it) => (
              <ListItemButton
                key={it.to}
                component={Link}
                to={it.to}
                sx={{ px: 2 }}
              >
                <ListItemIcon>{it.icon}</ListItemIcon>
                <ListItemText primary={it.label} />
              </ListItemButton>
            ))}
          </List>
        </Drawer>
      ) : null}

      <Box
        component="main"
        sx={{ flexGrow: 1, bgcolor: "background.default", minHeight: "100vh" }}
      >
        <Toolbar />
        <Container maxWidth="lg" sx={{ py: 3 }}>
          <Suspense fallback={<Typography>Loading...</Typography>}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/"
                element={
                  <RequireAuth>
                    <DashboardPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/convert"
                element={
                  <RequireAuth>
                    <ConvertPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/results"
                element={
                  <RequireAuth>
                    <ResultsPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/history"
                element={
                  <RequireAuth>
                    <HistoryPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/qa"
                element={
                  <RequireAuth>
                    <QaPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/help"
                element={
                  <RequireAuth>
                    <HelpPage />
                  </RequireAuth>
                }
              />
              <Route
                path="*"
                element={<Navigate to={token ? "/" : "/login"} replace />}
              />
            </Routes>
          </Suspense>
        </Container>
      </Box>
    </Box>
  );
}
