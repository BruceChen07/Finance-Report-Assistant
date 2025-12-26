/**
 * Results page:
 * - Lists successful conversion jobs based on /api/history events.
 * - Lets users preview or download previous markdown outputs.
 */
import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  Stack,
  TextField,
  Typography,
  Box
} from "@mui/material";
import ReactMarkdown from "react-markdown";
import { apiFetch } from "../utils/api-client";
import { useUi } from "../components/providers/UiProvider";

type HistoryEvent = {
  ts?: string;
  type?: string;
  user?: string;
  job_id?: string;
  ok?: boolean;
  error?: string;
  pdf?: string;
  backend?: string | null;
  md?: string;
};

type ResultRow = {
  job_id: string;
  ts: string;
  user: string;
  pdf: string;
  backend: string;
  md: string;
};

function toLocalTime(ts: string) {
  if (!ts) return "-";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

export default function ResultsPage() {
  const { setLoading, toast } = useUi();

  const [events, setEvents] = useState<HistoryEvent[]>([]);
  const [query, setQuery] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewJobId, setPreviewJobId] = useState<string>("");
  const [previewMarkdown, setPreviewMarkdown] = useState<string>("");
  const [previewPdfUrl, setPreviewPdfUrl] = useState<string>("");
  const [previewError, setPreviewError] = useState<string>("");
  const [splitView, setSplitView] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await apiFetch("/api/history?limit=2000");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as { items: HistoryEvent[] };
      setEvents(data.items || []);
    } catch (e: any) {
      toast(`Results load failed: ${e?.message || String(e)}`, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const rows = useMemo(() => {
    const byJob = new Map<string, ResultRow>();

    for (const e of events) {
      if (e?.type === "convert.done" && e.ok === true && typeof e.job_id === "string") {
        const jobId = e.job_id;
        if (!byJob.has(jobId)) {
          byJob.set(jobId, {
            job_id: jobId,
            ts: typeof e.ts === "string" ? e.ts : "",
            user: typeof e.user === "string" ? e.user : "",
            pdf: "",
            backend: "",
            md: typeof e.md === "string" ? e.md : ""
          });
        }
      }
    }

    for (const e of events) {
      if (e?.type === "convert.start" && typeof e.job_id === "string") {
        const r = byJob.get(e.job_id);
        if (!r) continue;
        if (!r.pdf && typeof e.pdf === "string") r.pdf = e.pdf;
        if (!r.backend && typeof e.backend === "string") r.backend = e.backend;
        if (!r.user && typeof e.user === "string") r.user = e.user;
      }
    }

    const list = Array.from(byJob.values());
    list.sort((a, b) => (b.ts || "").localeCompare(a.ts || ""));

    const q = query.trim().toLowerCase();
    if (!q) return list;

    return list.filter((r) => {
      const hay = `${r.job_id} ${r.pdf} ${r.backend} ${r.user} ${r.md}`.toLowerCase();
      return hay.includes(q);
    });
  }, [events, query]);

  const preview = async (jobId: string) => {
    setPreviewJobId(jobId);
    setPreviewMarkdown("");
    setPreviewError("");
    setPreviewOpen(true);

    setLoading(true);
    try {
      // Fetch Markdown
      const resMd = await apiFetch(`/api/jobs/${jobId}/result?download=false`);
      if (!resMd.ok) throw new Error(await resMd.text());
      const dataMd = (await resMd.json()) as { markdown: string };
      setPreviewMarkdown(dataMd.markdown || "");

      // Fetch PDF
      const resPdf = await apiFetch(`/api/jobs/${jobId}/pdf`);
      if (resPdf.ok) {
        const blob = await resPdf.blob();
        setPreviewPdfUrl(URL.createObjectURL(blob));
      }
    } catch (e: any) {
      setPreviewError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const closePreview = () => {
    setPreviewOpen(false);
    if (previewPdfUrl) {
      URL.revokeObjectURL(previewPdfUrl);
      setPreviewPdfUrl("");
    }
  };

  const download = async (jobId: string) => {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/jobs/${jobId}/result?download=true`);
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${jobId}.md`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e: any) {
      toast(`Download failed: ${e?.message || String(e)}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const copyJobId = async (jobId: string) => {
    try {
      await navigator.clipboard.writeText(jobId);
      toast("Job id copied", "success");
    } catch {
      toast("Copy failed", "error");
    }
  };

  return (
    <>
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Stack spacing={0.75}>
            <Typography variant="h4">Results</Typography>
            <Typography variant="body2" color="text.secondary">
              Only successful conversions are shown here.
            </Typography>
          </Stack>
        </Grid>

        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Stack spacing={1.5}>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: { sm: "center" } }}>
                  <TextField
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    label="Search"
                    placeholder="job id / pdf / backend / user"
                    fullWidth
                  />
                  <Button variant="outlined" onClick={load} sx={{ whiteSpace: "nowrap" }}>
                    Refresh
                  </Button>
                </Stack>

                <Divider />

                {rows.length === 0 ? (
                  <Alert severity="info" variant="outlined">
                    No successful results found yet.
                  </Alert>
                ) : (
                  <div style={{ overflow: "auto", maxHeight: 560 }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>Time</th>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>PDF</th>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>Backend</th>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>Job ID</th>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((r) => (
                          <tr key={r.job_id} style={{ borderTop: "1px solid rgba(0,0,0,0.08)" }}>
                            <td style={{ padding: "8px 6px", whiteSpace: "nowrap" }}>{toLocalTime(r.ts)}</td>
                            <td style={{ padding: "8px 6px" }}>{r.pdf || "-"}</td>
                            <td style={{ padding: "8px 6px" }}>{r.backend || "-"}</td>
                            <td style={{ padding: "8px 6px", fontFamily: "Consolas, monospace" }}>{r.job_id}</td>
                            <td style={{ padding: "8px 6px" }}>
                              <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
                                <Button size="small" variant="outlined" onClick={() => preview(r.job_id)}>
                                  Preview
                                </Button>
                                <Button size="small" variant="outlined" onClick={() => download(r.job_id)}>
                                  Download
                                </Button>
                                <Button size="small" variant="text" onClick={() => copyJobId(r.job_id)}>
                                  Copy id
                                </Button>
                              </Stack>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Dialog open={previewOpen} onClose={closePreview} fullWidth maxWidth="xl">
        <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}>
          <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexGrow: 1 }}>
            <Typography variant="h6">
              Preview: {previewJobId || "-"}
            </Typography>
            <Button
              size="small"
              variant={splitView ? "contained" : "outlined"}
              onClick={() => setSplitView(!splitView)}
              disabled={!previewPdfUrl}
            >
              {splitView ? "Single View" : "Split View"}
            </Button>
          </Stack>
          <Button variant="outlined" onClick={() => (previewJobId ? download(previewJobId) : null)} disabled={!previewJobId}>
            Download .md
          </Button>
        </DialogTitle>
        <DialogContent dividers sx={{ p: 0 }}>
          {previewError ? (
            <Box sx={{ p: 3 }}>
              <Alert severity="error">{previewError}</Alert>
            </Box>
          ) : (
            <Grid container sx={{ height: "80vh" }}>
              {(splitView && previewPdfUrl) && (
                <Grid item xs={12} md={6} sx={{ borderRight: "1px solid rgba(0,0,0,0.12)", height: "100%" }}>
                  <iframe
                    src={`${previewPdfUrl}#toolbar=0`}
                    width="100%"
                    height="100%"
                    style={{ border: "none" }}
                    title="Original PDF"
                  />
                </Grid>
              )}
              <Grid item xs={12} md={(splitView && previewPdfUrl) ? 6 : 12} sx={{ height: "100%", overflow: "auto", p: 3 }}>
                <ReactMarkdown>{previewMarkdown || "No content."}</ReactMarkdown>
              </Grid>
            </Grid>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}