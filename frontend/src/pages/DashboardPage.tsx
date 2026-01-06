/**
 * Dashboard page:
 * - Shows backend status and key path information via /api/status
 */
import React, { useEffect, useState } from "react";
import { Card, CardContent, Grid, Stack, Typography } from "@mui/material";
import { apiFetch } from "../utils/api-client";
import { useUi } from "../components/providers/UiProvider";

export default function DashboardPage() {
  const { setLoading, toast } = useUi();
  const [status, setStatus] = useState<any>(null);
  const [storage, setStorage] = useState<any>(null);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      try {
        const [resStatus, resStorage] = await Promise.all([
          apiFetch("/api/status"),
          apiFetch("/api/storage/status"),
        ]);
        if (!resStatus.ok) throw new Error(await resStatus.text());
        if (!resStorage.ok) throw new Error(await resStorage.text());
        setStatus(await resStatus.json());
        setStorage(await resStorage.json());
      } catch (e: any) {
        toast(`Status failed: ${e?.message || String(e)}`, "error");
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []);

  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Typography variant="h4">Dashboard</Typography>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Stack spacing={1}>
              <Typography variant="h6">Backend Status</Typography>
              <Typography variant="body2">MinerU: {status ? String(status.mineru) : "-"}</Typography>
              <Typography variant="body2">magic-pdf: {status ? String(status.magic_pdf) : "-"}</Typography>
            </Stack>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Stack spacing={1}>
              <Typography variant="h6">Paths</Typography>
              <Typography variant="body2">output_root: {status?.output_root || "-"}</Typography>
              <Typography variant="body2">static_dist_dir: {status?.static_dist_dir || "-"}</Typography>
              <Typography variant="body2">SQLite: {storage?.sqlite_path || "-"}</Typography>
              <Typography variant="body2">SQLite size: {storage?.sqlite_size_bytes ?? "-"} bytes</Typography>
              <Typography variant="body2">Chroma dir: {storage?.chroma_dir || "-"}</Typography>
              <Typography variant="body2">Chroma size: {storage?.chroma_size_bytes ?? "-"} bytes</Typography>
              <Typography variant="body2">Vectors: {storage?.chroma_vector_count ?? "-"}</Typography>
              <Typography variant="body2">Reports: {storage?.reports_count ?? "-"}</Typography>
              <Typography variant="body2">Last indexed: {storage?.last_indexed_at || "-"}</Typography>
              <Typography variant="body2">Latest backup: {storage?.latest_backup || "-"}</Typography>
            </Stack>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}