/**
 * Help page:
 * - Embeds FastAPI Swagger UI via iframe (/docs)
 * - In dev, Vite proxy forwards /docs to backend.
 */
import React from "react";
import { Card, CardContent, Grid, Typography } from "@mui/material";

export default function HelpPage() {
  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Typography variant="h4">Help</Typography>
        <Typography variant="body2" color="text.secondary">
          Swagger UI is embedded below.
        </Typography>
      </Grid>
      <Grid item xs={12}>
        <Card>
          <CardContent sx={{ p: 0 }}>
            <iframe title="swagger" src="/docs" style={{ width: "100%", height: 720, border: "none" }} />
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}