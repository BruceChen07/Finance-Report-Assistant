/**
 * Results page:
 * - Lists successful conversion jobs based on /api/history events.
 * - Lets users preview or download previous markdown outputs.
 */
import React, { useEffect, useMemo, useState } from "react";
import rehypeRaw from "rehype-raw";
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
  Box,
  ToggleButton,
  ToggleButtonGroup,
  FormControlLabel,
  Switch,
} from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css"; // Ensure you have this import if you want math styling
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
  const [viewMode, setViewMode] = useState<"rendered" | "text">("rendered");
  const [showLineNumbers, setShowLineNumbers] = useState(false);

  useEffect(() => {
    const savedMode = localStorage.getItem("fra.preview.viewMode");
    if (savedMode === "text" || savedMode === "rendered") {
      setViewMode(savedMode);
    }
  }, []);

  const handleViewModeChange = (
    event: React.MouseEvent<HTMLElement>,
    newMode: "rendered" | "text" | null
  ) => {
    if (newMode !== null) {
      setViewMode(newMode);
      localStorage.setItem("fra.preview.viewMode", newMode);
    }
  };

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
      if (
        e?.type === "convert.done" &&
        e.ok === true &&
        typeof e.job_id === "string"
      ) {
        const jobId = e.job_id;
        if (!byJob.has(jobId)) {
          byJob.set(jobId, {
            job_id: jobId,
            ts: typeof e.ts === "string" ? e.ts : "",
            user: typeof e.user === "string" ? e.user : "",
            pdf: "",
            backend: "",
            md: typeof e.md === "string" ? e.md : "",
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
      const hay =
        `${r.job_id} ${r.pdf} ${r.backend} ${r.user} ${r.md}`.toLowerCase();
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

  const downloadAuto = async (jobId: string) => {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/jobs/${jobId}/auto-bundle`);
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      const cd = res.headers.get("Content-Disposition") || "";
      let filename = `${jobId}_auto.zip`;
      const match = /filename="?([^";]+)"?/i.exec(cd);
      if (match && match[1]) {
        filename = match[1];
      }
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e: any) {
      toast(`Download bundle failed: ${e?.message || String(e)}`, "error");
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
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={1}
                  sx={{ alignItems: { sm: "center" } }}
                >
                  <TextField
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    label="Search"
                    placeholder="job id / pdf / backend / user"
                    fullWidth
                  />
                  <Button
                    variant="outlined"
                    onClick={load}
                    sx={{ whiteSpace: "nowrap" }}
                  >
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
                    <table
                      style={{ width: "100%", borderCollapse: "collapse" }}
                    >
                      <thead>
                        <tr>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>
                            Time
                          </th>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>
                            PDF
                          </th>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>
                            Backend
                          </th>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>
                            Job ID
                          </th>
                          <th style={{ textAlign: "left", padding: "8px 6px" }}>
                            Actions
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((r) => (
                          <tr
                            key={r.job_id}
                            style={{ borderTop: "1px solid rgba(0,0,0,0.08)" }}
                          >
                            <td
                              style={{
                                padding: "8px 6px",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {toLocalTime(r.ts)}
                            </td>
                            <td style={{ padding: "8px 6px" }}>
                              {r.pdf || "-"}
                            </td>
                            <td style={{ padding: "8px 6px" }}>
                              {r.backend || "-"}
                            </td>
                            <td
                              style={{
                                padding: "8px 6px",
                                fontFamily: "Consolas, monospace",
                              }}
                            >
                              {r.job_id}
                            </td>
                            <td style={{ padding: "8px 6px" }}>
                              <Stack
                                direction="row"
                                spacing={1}
                                sx={{
                                  flexWrap: "nowrap",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                <Button
                                  size="small"
                                  variant="outlined"
                                  onClick={() => preview(r.job_id)}
                                  sx={{ minWidth: "auto" }}
                                >
                                  Preview
                                </Button>
                                <Button
                                  size="small"
                                  variant="outlined"
                                  onClick={() => download(r.job_id)}
                                  sx={{ minWidth: "auto" }}
                                >
                                  Download
                                </Button>
                                <Button
                                  size="small"
                                  variant="outlined"
                                  onClick={() => downloadAuto(r.job_id)}
                                  sx={{ minWidth: "auto" }}
                                >
                                  Bundle
                                </Button>
                                <Button
                                  size="small"
                                  variant="text"
                                  onClick={() => copyJobId(r.job_id)}
                                  sx={{ minWidth: "auto" }}
                                >
                                  Copy ID
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
        <DialogTitle
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 2,
          }}
        >
          <Stack
            direction="row"
            spacing={2}
            sx={{ alignItems: "center", flexGrow: 1 }}
          >
            <Typography variant="h6">Preview: {previewJobId || "-"}</Typography>
            <Button
              size="small"
              variant={splitView ? "contained" : "outlined"}
              onClick={() => setSplitView(!splitView)}
              disabled={!previewPdfUrl}
            >
              {splitView ? "Single View" : "Split View"}
            </Button>

            <ToggleButtonGroup
              value={viewMode}
              exclusive
              onChange={handleViewModeChange}
              size="small"
              aria-label="view mode"
            >
              <ToggleButton value="rendered" aria-label="rendered">
                Rendered
              </ToggleButton>
              <ToggleButton value="text" aria-label="text">
                Text
              </ToggleButton>
            </ToggleButtonGroup>

            {viewMode === "text" && (
              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={showLineNumbers}
                    onChange={(e) => setShowLineNumbers(e.target.checked)}
                  />
                }
                label={<Typography variant="caption">Line Nums</Typography>}
              />
            )}
          </Stack>
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              onClick={() => (previewJobId ? download(previewJobId) : null)}
              disabled={!previewJobId}
            >
              Download .md
            </Button>
            <Button
              variant="outlined"
              onClick={() => (previewJobId ? downloadAuto(previewJobId) : null)}
              disabled={!previewJobId}
            >
              Download auto.zip
            </Button>
          </Stack>
        </DialogTitle>
        <DialogContent dividers sx={{ p: 0 }}>
          {previewError ? (
            <Box sx={{ p: 3 }}>
              <Alert severity="error">{previewError}</Alert>
            </Box>
          ) : (
            <Grid container sx={{ height: "80vh" }}>
              {splitView && previewPdfUrl && (
                <Grid
                  item
                  xs={12}
                  md={6}
                  sx={{
                    borderRight: "1px solid rgba(0,0,0,0.12)",
                    height: "100%",
                  }}
                >
                  <iframe
                    src={`${previewPdfUrl}#toolbar=0`}
                    width="100%"
                    height="100%"
                    style={{ border: "none" }}
                    title="Original PDF"
                  />
                </Grid>
              )}
              <Grid
                item
                xs={12}
                md={splitView && previewPdfUrl ? 6 : 12}
                sx={{ height: "100%", overflow: "auto", p: 3 }}
              >
                {viewMode === "rendered" ? (
                  <Box
                    className="markdown-body"
                    sx={{
                      "& table": {
                        width: "100%",
                        borderCollapse: "collapse",
                        tableLayout: "auto",
                      },
                      "& th, & td": {
                        verticalAlign: "top",
                      },
                      "& td:first-of-type": {
                        whiteSpace: "pre-wrap",
                      },
                      "& td:nth-of-type(n+2), & th:nth-of-type(n+2)": {
                        textAlign: "right",
                        whiteSpace: "nowrap",
                        fontVariantNumeric: "tabular-nums",
                      },
                    }}
                  >
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[rehypeRaw, rehypeKatex]}
                      components={{
                        table: ({ node, ...props }) => (
                          <div style={{ overflowX: "auto" }}>
                            <table
                              style={{
                                borderCollapse: "collapse",
                                width: "100%",
                                marginBottom: "1em",
                              }}
                              {...props}
                            />
                          </div>
                        ),
                        th: ({ node, ...props }) => (
                          <th
                            style={{
                              border: "1px solid #ddd",
                              padding: "8px",
                              backgroundColor: "#f2f2f2",
                              verticalAlign: "top",
                            }}
                            {...props}
                          />
                        ),
                        td: ({ node, ...props }) => (
                          <td
                            style={{
                              border: "1px solid #ddd",
                              padding: "8px",
                              verticalAlign: "top",
                            }}
                            {...props}
                          />
                        ),
                        img: ({ node, ...props }) => (
                          <img
                            style={{ maxWidth: "100%", height: "auto" }}
                            {...props}
                          />
                        ),
                      }}
                    >
                      {previewMarkdown || "No content."}
                    </ReactMarkdown>
                  </Box>
                ) : (
                  <Box
                    component="pre"
                    sx={{
                      m: 0,
                      p: 2,
                      fontFamily: "Consolas, monospace",
                      fontSize: "0.875rem",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      backgroundColor: "#f5f5f5",
                      borderRadius: 1,
                      minHeight: "100%",
                      counterReset: showLineNumbers ? "line" : "none",
                    }}
                  >
                    {showLineNumbers
                      ? previewMarkdown.split("\n").map((line, i) => (
                          <div key={i} style={{ display: "flex" }}>
                            <span
                              style={{
                                display: "inline-block",
                                width: "3em",
                                textAlign: "right",
                                marginRight: "1em",
                                color: "#999",
                                userSelect: "none",
                                borderRight: "1px solid #ddd",
                                paddingRight: "0.5em",
                              }}
                            >
                              {i + 1}
                            </span>
                            <span>{line}</span>
                          </div>
                        ))
                      : previewMarkdown}
                  </Box>
                )}
              </Grid>
            </Grid>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
