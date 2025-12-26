/**
 * Login page:
 * - Username/password form
 * - Calls /api/auth/login and stores JWT
 * - Uses toast for errors and global loading indicator
 */
import React, { useState } from "react";
import { Box, Button, Card, CardContent, Stack, TextField, Typography } from "@mui/material";
import { useAuth } from "../components/providers/AuthProvider";
import { useUi } from "../components/providers/UiProvider";

export default function LoginPage() {
  const { login } = useAuth();
  const { setLoading, toast } = useUi();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin");

  const submit = async () => {
    setLoading(true);
    try {
      await login(username, password);
      toast("Login success", "success");
      window.location.href = "/";
    } catch (e: any) {
      toast(`Login failed: ${e?.message || String(e)}`, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ display: "grid", placeItems: "center", minHeight: "70vh" }}>
      <Card sx={{ width: "100%", maxWidth: 420 }}>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h5">Sign in</Typography>
            <Typography variant="body2" color="text.secondary">
              Use the server credentials configured by FRA_USERNAME / FRA_PASSWORD.
            </Typography>
            <TextField label="Username" value={username} onChange={(e) => setUsername(e.target.value)} fullWidth />
            <TextField
              label="Password"
              value={password}
              type="password"
              onChange={(e) => setPassword(e.target.value)}
              fullWidth
            />
            <Button variant="contained" onClick={submit} sx={{ py: 1.25 }}>
              Login
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}