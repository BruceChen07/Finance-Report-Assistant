/**
 * History page:
 * - Fetches recent events from /api/history
 * - Displays raw JSON lines (simple & robust starter)
 */
import React, { useEffect, useState } from "react";
import { Card, CardContent, Grid, Stack, Typography } from "@mui/material";
import { apiFetch } from "../utils/api-client";
import { useUi } from "../components/providers/UiProvider";

export default function HistoryPage() {
  const { setLoading, toast } = useUi();
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      try {
        const res = await apiFetch("/api/history?limit=200");
        if (!res.ok) throw new Error(await res.text());
        const data = (await res.json()) as { items: any[] };
        setItems(data.items || []);
      } catch (e: any) {
        toast(`History failed: ${e?.message || String(e)}`, "error");
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []);

  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Typography variant="h4">History</Typography>
      </Grid>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Stack spacing={1}>
              <Typography variant="h6">Latest events</Typography>
              <div style={{ overflow: "auto", maxHeight: 560 }}>
                <pre style={{ margin: 0, fontSize: 12, lineHeight: 1.5 }}>
                  {items.map((x) => JSON.stringify(x)).join("\n")}
                </pre>
              </div>
            </Stack>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}