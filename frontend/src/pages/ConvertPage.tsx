/**
 * Convert page:
 * - Upload PDF -> POST /api/convert
 * - Fetch markdown -> GET /api/jobs/{job_id}/result
 * - Toast for errors + global loading indicator
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  FormControl,
  FormHelperText,
  Grid,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography
} from "@mui/material";
import ReactMarkdown from "react-markdown";
import { apiFetch } from "../utils/api-client";
import { useUi } from "../components/providers/UiProvider";

type JobStatus = {
  job_id: string;
  stage: string;
  percent: number;
  ok: boolean | null;
  error: string | null;
  pdf_name: string;
  md_path: string | null;
  created_at: number;
  updated_at: number;
};

type JobEvent = {
  type?: string;
  job_id?: string;
  ts?: string;
  stage?: string;
  percent?: number;
  ok?: boolean | null;
  error?: string | null;
  md_path?: string | null;
  level?: string;
  message?: string;
  elapsed_ms?: number;
};

const ACTIVE_JOB_KEY = "fra.active_job_id";
const LAST_JOB_KEY = "fra.last_job_id";

function tryExtractDetail(message: string): string {
  const raw = String(message || "");
  try {
    const obj = JSON.parse(raw) as any;
    if (obj && typeof obj.detail === "string" && obj.detail.trim()) return obj.detail;
  } catch {
    return raw;
  }
  return raw;
}

function isResultNotReadyMessage(message: string): boolean {
  const m = String(message || "").toLowerCase();
  return m.includes("result not found");
}

function stageLabel(stage: string) {
  const s = (stage || "").toLowerCase();
  if (s === "queued") return "Queued";
  if (s === "prepare") return "Preparing";
  if (s === "convert") return "Converting";
  if (s === "collect_output") return "Collecting output";
  if (s === "done") return "Done";
  if (s === "error") return "Error";
  return stage || "-";
}

export default function ConvertPage() {
  const { setLoading, toast } = useUi();
  const [file, setFile] = useState<File | null>(null);
  const [backend, setBackend] = useState<string>("");
  const [mode, setMode] = useState<string>("auto");
  const [jobId, setJobId] = useState<string>("");
  const [job, setJob] = useState<JobStatus | null>(null);
  const [markdown, setMarkdown] = useState<string>("");
  const [logs, setLogs] = useState<JobEvent[]>([]);
  const [eventsConnected, setEventsConnected] = useState<boolean>(false);
  const resultFetchedRef = useRef(false);

  const isRunning = !!jobId && (job?.ok ?? null) === null;
  const canSubmit = useMemo(() => !!file && !isRunning, [file, isRunning]);

  const fetchResult = async (id: string) => {
    if (resultFetchedRef.current) return;
    const res = await apiFetch(`/api/jobs/${id}/result?download=false`);
    if (!res.ok) throw new Error(await res.text());
    const data = (await res.json()) as { markdown: string };
    setMarkdown(data.markdown || "");
    resultFetchedRef.current = true;
  };

  useEffect(() => {
    const saved = localStorage.getItem(ACTIVE_JOB_KEY);
    if (saved) setJobId(saved);
  }, []);

  useEffect(() => {
    if (!jobId) return;
    localStorage.setItem(LAST_JOB_KEY, jobId);
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return;

    let disposed = false;
    const ac = new AbortController();

    const appendLog = (evt: JobEvent) => {
      setLogs((prev) => {
        const next = [...prev, evt];
        if (next.length <= 400) return next;
        return next.slice(next.length - 400);
      });
    };

    const applyEvent = (evt: JobEvent) => {
      if (!evt || disposed) return;

      if (evt.type === "log") {
        appendLog(evt);
        if (typeof evt.percent === "number") {
          setJob((prev) =>
            prev
              ? {
                ...prev,
                stage: evt.stage || prev.stage,
                percent: evt.percent ?? prev.percent,
                updated_at: Date.now() / 1000
              }
              : prev
          );
        }
        return;
      }

      if (evt.type === "snapshot" || evt.type === "progress") {
        setJob((prev) => {
          const base: JobStatus =
            prev ||
            ({
              job_id: jobId,
              stage: "queued",
              percent: 0,
              ok: null,
              error: null,
              pdf_name: "",
              md_path: null,
              created_at: Date.now() / 1000,
              updated_at: Date.now() / 1000
            } as JobStatus);

          return {
            ...base,
            stage: evt.stage ?? base.stage,
            percent: typeof evt.percent === "number" ? evt.percent : base.percent,
            ok: typeof evt.ok === "boolean" ? evt.ok : evt.ok === null ? null : base.ok,
            error: evt.error ?? base.error,
            md_path: evt.md_path ?? base.md_path,
            updated_at: Date.now() / 1000
          };
        });
      }

      if (evt.type === "progress" && evt.ok === true) {
        localStorage.removeItem(ACTIVE_JOB_KEY);
        fetchResult(jobId).catch(() => undefined);
      }

      if (evt.type === "progress" && evt.ok === false) {
        localStorage.removeItem(ACTIVE_JOB_KEY);
      }
    };

    const pollOnce = async () => {
      try {
        const res = await apiFetch(`/api/jobs/${jobId}`);
        if (!res.ok) throw new Error(await res.text());
        const st = (await res.json()) as JobStatus;
        if (disposed) return;
        setJob(st);
        if (st.ok === true) {
          localStorage.removeItem(ACTIVE_JOB_KEY);
          await fetchResult(jobId);
        }
        if (st.ok === false) {
          localStorage.removeItem(ACTIVE_JOB_KEY);
        }
      } catch {
        if (!disposed) setEventsConnected(false);
      }
    };

    const startPolling = () => {
      pollOnce().catch(() => undefined);
      const t = window.setInterval(() => {
        pollOnce().catch(() => undefined);
      }, 4000);
      return () => window.clearInterval(t);
    };

    const streamEvents = async () => {
      try {
        const res = await apiFetch(`/api/jobs/${jobId}/events`, { signal: ac.signal });
        if (!res.ok) throw new Error(await res.text());
        if (!res.body) throw new Error("events stream not available");

        setEventsConnected(true);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        const flush = () => {
          let idx = buf.indexOf("\n\n");
          while (idx !== -1) {
            const block = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const dataLines = block
              .split("\n")
              .filter((l) => l.startsWith("data:"))
              .map((l) => l.slice("data:".length).trimStart());
            if (dataLines.length) {
              const raw = dataLines.join("\n");
              try {
                applyEvent(JSON.parse(raw) as JobEvent);
              } catch {
                appendLog({ type: "log", level: "WARN", stage: "client", message: raw });
              }
            }
            idx = buf.indexOf("\n\n");
          }
        };

        while (!disposed) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          flush();
        }
      } catch {
        if (!disposed) setEventsConnected(false);
      }
    };

    const stopPolling = startPolling();
    streamEvents().catch(() => undefined);

    return () => {
      disposed = true;
      stopPolling();
      ac.abort();
    };
  }, [jobId]);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!jobId) return;
      if ((job?.ok ?? null) !== null) return;
      e.preventDefault();
      e.returnValue = "";
    };

    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [jobId, job?.ok]);

  const clearTracking = () => {
    localStorage.removeItem(ACTIVE_JOB_KEY);
    setJobId("");
    setJob(null);
    setLogs([]);
    setMarkdown("");
    resultFetchedRef.current = false;
  };

  const copyJobId = async () => {
    if (!jobId) return;
    try {
      await navigator.clipboard.writeText(jobId);
      toast("Job id copied", "success");
    } catch {
      toast("Copy failed", "error");
    }
  };

  const submit = async () => {
    if (!file) return;
    setLoading(true);
    setMarkdown("");
    setLogs([]);
    resultFetchedRef.current = false;
    try {
      const fd = new FormData();
      fd.append("file", file);

      const qs = new URLSearchParams();
      if (backend.trim()) qs.set("backend", backend.trim());
      if (mode.trim()) qs.set("mode", mode.trim());
      qs.set("download", "false");

      const res = await apiFetch(`/api/convert?${qs.toString()}`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as { job_id: string; result_url: string };

      setJobId(data.job_id);
      localStorage.setItem(ACTIVE_JOB_KEY, data.job_id);
      setJob({
        job_id: data.job_id,
        stage: "queued",
        percent: 0,
        ok: null,
        error: null,
        pdf_name: file.name,
        md_path: null,
        created_at: Date.now() / 1000,
        updated_at: Date.now() / 1000
      });

      toast("Job created. Processing in background.", "info");
    } catch (e: any) {
      toast(`Convert failed: ${e?.message || String(e)}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const download = async () => {
    if (!jobId) return;
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

  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Typography variant="h4">API Call</Typography>
        <Typography variant="body2" color="text.secondary">
          Upload a PDF and get Markdown output.
        </Typography>
      </Grid>

      <Grid item xs={12} md={5}>
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="h6">Parameters</Typography>

              <Button variant="outlined" component="label" disabled={isRunning}>
                Choose PDF
                <input
                  hidden
                  type="file"
                  accept="application/pdf"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </Button>
              <Typography variant="body2">{file ? file.name : "No file selected"}</Typography>

              <FormControl fullWidth disabled={isRunning}>
                <InputLabel id="backend-label">Model / Backend</InputLabel>
                <Select
                  labelId="backend-label"
                  label="Model / Backend"
                  value={backend}
                  onChange={(e) => setBackend(e.target.value)}
                >
                  <MenuItem value=""><em>Default (Auto)</em></MenuItem>
                  <MenuItem value="pipeline">Pipeline (Fast, Rule-based + Layout)</MenuItem>
                  <MenuItem value="vlm-transformers">VLM Transformers (Accurate, Multi-modal)</MenuItem>
                </Select>
                <FormHelperText>
                  VLM is more accurate for complex layouts but requires more resources.
                </FormHelperText>
              </FormControl>

              {backend === "pipeline" && (
                <FormControl fullWidth disabled={isRunning}>
                  <InputLabel id="mineru-mode-label">OCR / Analysis Mode</InputLabel>
                  <Select
                    labelId="mineru-mode-label"
                    label="OCR / Analysis Mode"
                    value={mode}
                    onChange={(e) => setMode(String(e.target.value))}
                  >
                    <MenuItem value="auto">Auto (Smart detect)</MenuItem>
                    <MenuItem value="txt">Text-based (No OCR)</MenuItem>
                    <MenuItem value="ocr">OCR (Force OCR for all pages)</MenuItem>
                  </Select>
                  <FormHelperText>
                    Use OCR mode for scanned documents or images.
                  </FormHelperText>
                </FormControl>
              )}

              <Button variant="contained" disabled={!canSubmit} onClick={submit} sx={{ py: 1.25 }}>
                Convert
              </Button>

              <Divider />

              <Stack spacing={1.25}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                  <Typography variant="body2">job_id:</Typography>
                  <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                    {jobId || "-"}
                  </Typography>
                  {!!jobId && <Chip size="small" label={stageLabel(job?.stage || "-")} />}
                  {!!jobId && (
                    <Chip
                      size="small"
                      variant="outlined"
                      label={eventsConnected ? "events: connected" : "events: polling"}
                    />
                  )}
                </Stack>

                {!!jobId && (
                  <Stack spacing={0.75}>
                    <LinearProgress
                      variant={typeof job?.percent === "number" ? "determinate" : "indeterminate"}
                      value={Math.max(0, Math.min(100, job?.percent ?? 0))}
                    />
                    <Typography variant="caption" color="text.secondary">
                      {(job?.percent ?? 0).toFixed(0)}% • {(job?.ok ?? null) === null ? "running" : job?.ok ? "done" : "error"}
                    </Typography>
                  </Stack>
                )}

                {job?.ok === false && (
                  <Alert severity="error" sx={{ mt: 1 }}>
                    {job.error || "Convert failed"}
                  </Alert>
                )}
              </Stack>

              <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
                <Button variant="outlined" disabled={!jobId || job?.ok !== true} onClick={download}>
                  Download .md
                </Button>
                <Button variant="outlined" disabled={!jobId} onClick={copyJobId}>
                  Copy job id
                </Button>
                <Button variant="text" disabled={!jobId} onClick={clearTracking}>
                  Clear
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={7}>
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="h6">Result</Typography>
              <Typography variant="body2" color="text.secondary">
                Markdown preview
              </Typography>
              <div style={{ maxHeight: 340, overflow: "auto" }}>
                <ReactMarkdown>{markdown || "No result yet."}</ReactMarkdown>
              </div>

              <Divider />

              <Typography variant="h6">Logs</Typography>
              <Typography variant="body2" color="text.secondary">
                Live progress/log stream (falls back to polling)
              </Typography>
              <Paper variant="outlined" sx={{ maxHeight: 220, overflow: "auto", p: 1 }}>
                {logs.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No logs yet.
                  </Typography>
                ) : (
                  <Stack spacing={0.5}>
                    {logs.map((l, idx) => (
                      <Typography
                        key={`${l.ts || ""}-${idx}`}
                        variant="caption"
                        sx={{ fontFamily: "monospace", whiteSpace: "pre-wrap" }}
                      >
                        [{l.level || "INFO"}] {l.stage ? `${l.stage}: ` : ""}
                        {l.message || ""}
                      </Typography>
                    ))}
                  </Stack>
                )}
              </Paper>
            </Stack>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}