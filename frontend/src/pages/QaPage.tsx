import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  FormControlLabel,
  Grid,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
  Checkbox,
} from "@mui/material";
import { apiFetch } from "../utils/api-client";

type QaSource = {
  kind: "chunk" | "sql_row";
  title?: string | null;
  snippet?: string | null;
  metadata?: Record<string, unknown>;
};

type QaResponse = {
  answer: string;
  sources: QaSource[];
};

type FileItem = {
  id: number;
  job_id: string;
  file_name: string;
  file_type: string;
  size_bytes: number;
  created_at?: string | null;
  indexed_at?: string | null;
  company_code?: string | null;
  company_name?: string | null;
  report_year?: number | null;
  report_type?: string | null;
};

const STORAGE_KEY = "fra.qa.selected_file_ids";

function splitCommaList(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function extractImagePaths(meta?: Record<string, unknown>): string[] {
  if (!meta) return [];
  const out: string[] = [];

  const p1 = meta["img_path"];
  if (typeof p1 === "string" && p1.trim()) out.push(p1.trim());

  const p2 = meta["img_paths"];
  if (Array.isArray(p2)) {
    for (const x of p2) {
      if (typeof x === "string" && x.trim()) out.push(x.trim());
    }
  } else if (typeof p2 === "string" && p2.trim()) {
    out.push(...splitCommaList(p2));
  }

  return Array.from(new Set(out));
}

function extractPageLabel(meta?: Record<string, unknown>): string | null {
  if (!meta) return null;

  const ps = meta["page_start"];
  const pe = meta["page_end"];
  const pi = meta["page_idx"];

  if (typeof ps === "number" && typeof pe === "number") {
    if (ps === pe) return `page ${ps + 1}`;
    return `pages ${ps + 1}-${pe + 1}`;
  }

  if (typeof pi === "number") {
    return `page ${pi + 1}`;
  }

  return null;
}

export default function QaPage() {
  const [question, setQuestion] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [reportYear, setReportYear] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [strict, setStrict] = useState(true);
  const [result, setResult] = useState<QaResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selectionMode, setSelectionMode] = useState<"single" | "multi" | "all">("multi");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const [evidenceUrls, setEvidenceUrls] = useState<Record<string, string>>({});
  const evidenceObjectUrlsRef = useRef<string[]>([]);

  const wantedEvidence = useMemo(() => {
    const items: { key: string; jobId: string; path: string }[] = [];
    if (!result?.sources?.length) return items;

    let total = 0;
    for (const s of result.sources) {
      const meta = s.metadata;
      if (!meta) continue;
      const jobId = typeof meta["job_id"] === "string" ? meta["job_id"] : "";
      if (!jobId) continue;

      const paths = extractImagePaths(meta).slice(0, 2);
      for (const p of paths) {
        const key = `${jobId}|${p}`;
        items.push({ key, jobId, path: p });
        total += 1;
        if (total >= 6) return items;
      }
    }

    return items;
  }, [result]);

  const clearEvidence = () => {
    for (const u of evidenceObjectUrlsRef.current) {
      try {
        URL.revokeObjectURL(u);
      } catch {
        // ignore
      }
    }
    evidenceObjectUrlsRef.current = [];
    setEvidenceUrls({});
  };

  useEffect(() => {
    return () => {
      clearEvidence();
    };
  }, []);

  useEffect(() => {
    clearEvidence();
    if (!wantedEvidence.length) return;

    const ac = new AbortController();

    const run = async () => {
      for (const it of wantedEvidence) {
        if (ac.signal.aborted) return;
        try {
          const url = `/api/jobs/${encodeURIComponent(it.jobId)}/asset?path=${encodeURIComponent(it.path)}`;
          const resp = await apiFetch(url, { signal: ac.signal });
          if (!resp.ok) continue;
          const blob = await resp.blob();
          const objUrl = URL.createObjectURL(blob);
          evidenceObjectUrlsRef.current.push(objUrl);
          setEvidenceUrls((prev) => ({ ...prev, [it.key]: objUrl }));
        } catch {
          // ignore
        }
      }
    };

    run();
    return () => {
      ac.abort();
    };
  }, [wantedEvidence]);

  useEffect(() => {
    const run = async () => {
      try {
        const resp = await apiFetch("/api/files");
        if (!resp.ok) return;
        const data = (await resp.json()) as { items: FileItem[] };
        setFiles(data.items || []);
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (raw) {
          const ids = JSON.parse(raw) as number[];
          const valid = ids.filter((id) => data.items.some((f) => f.id === id));
          setSelectedIds(valid);
        }
      } catch {
        // ignore
      }
    };
    run();
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedIds));
    } catch {
      // ignore
    }
  }, [selectedIds]);

  const toggleFile = (id: number) => {
    if (selectionMode === "single") {
      setSelectedIds([id]);
      return;
    }
    if (selectionMode === "multi") {
      setSelectedIds((prev) =>
        prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
      );
    }
  };

  const handleSelectAll = () => {
    setSelectionMode("all");
    setSelectedIds(files.map((f) => f.id));
  };

  const handleAsk = async () => {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const body: any = {
        question: question.trim(),
        strict,
        top_k: 8,
      };
      if (companyId.trim()) body.company_id = companyId.trim();
      if (reportYear.trim())
        body.report_year = Number(reportYear.trim()) || undefined;
      if (selectionMode !== "all" && selectedIds.length > 0) {
        body.file_ids = selectedIds;
      }

      const resp = await apiFetch("/api/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt}`);
      }

      const data = (await resp.json()) as QaResponse;
      setResult(data);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Grid container spacing={3}>
      <Grid item xs={12} md={5}>
        <Paper sx={{ p: 3, mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            File Selection
          </Typography>
          <Stack spacing={1}>
            <FormControl component="fieldset">
              <RadioGroup
                row
                value={selectionMode}
                onChange={(e) =>
                  setSelectionMode(e.target.value as "single" | "multi" | "all")
                }
              >
                <FormControlLabel value="single" control={<Radio size="small" />} label="Single" />
                <FormControlLabel value="multi" control={<Radio size="small" />} label="Multi" />
                <FormControlLabel value="all" control={<Radio size="small" />} label="All" />
              </RadioGroup>
            </FormControl>
            <Box sx={{ maxHeight: 220, overflow: "auto", border: 1, borderColor: "divider", borderRadius: 1 }}>
              <List dense>
                {files.map((f) => {
                  const checked = selectionMode === "all" || selectedIds.includes(f.id);
                  const indexed = !!f.indexed_at;
                  const secondary = [
                    f.company_code ? `${f.company_code}${f.company_name ? " " + f.company_name : ""}` : undefined,
                    f.report_year ? String(f.report_year) : undefined,
                    indexed ? undefined : "Indexing...",
                  ]
                    .filter(Boolean)
                    .join(" / ");
                  return (
                    <ListItem key={f.id} disablePadding>
                      <ListItemButton
                        dense
                        disabled={!indexed}
                        onClick={() => {
                          if (selectionMode === "all" || !indexed) return;
                          toggleFile(f.id);
                        }}
                      >
                        {selectionMode !== "all" && (
                          <Checkbox
                            edge="start"
                            tabIndex={-1}
                            disableRipple
                            checked={checked}
                            disabled={!indexed}
                            onChange={() => {
                              if (!indexed) return;
                              toggleFile(f.id);
                            }}
                          />
                        )}
                        <ListItemText
                          primary={
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                              <span>{f.file_name}</span>
                              {!indexed && (
                                <CircularProgress size={14} color="inherit" />
                              )}
                            </Box>
                          }
                          secondary={secondary || undefined}
                        />
                      </ListItemButton>
                    </ListItem>
                  );
                })}
                {!files.length && (
                  <ListItem>
                    <ListItemText primary="No files available yet." />
                  </ListItem>
                )}
              </List>
            </Box>
            <Box>
              <Button size="small" onClick={handleSelectAll} disabled={!files.length}>
                Select All
              </Button>
            </Box>
          </Stack>
        </Paper>

        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>
            Financial Q&A
          </Typography>
          <Stack spacing={2}>
            <TextField
              label="Question"
              multiline
              minRows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. What was the 2024 revenue and year-over-year growth?"
            />
            <TextField
              label="Company ID (optional)"
              value={companyId}
              onChange={(e) => setCompanyId(e.target.value)}
              placeholder="e.g. 600519"
            />
            <TextField
              label="Report Year (optional)"
              value={reportYear}
              onChange={(e) => setReportYear(e.target.value)}
              placeholder="e.g. 2024"
            />
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="body2">Mode:</Typography>
              <Chip
                label="Strict"
                color={strict ? "primary" : "default"}
                size="small"
                onClick={() => setStrict(true)}
              />
              <Chip
                label="Flexible"
                color={!strict ? "primary" : "default"}
                size="small"
                onClick={() => setStrict(false)}
              />
            </Stack>
            <Box>
              <Button
                variant="contained"
                onClick={handleAsk}
                disabled={loading || !question.trim()}
              >
                {loading ? (
                  <>
                    <CircularProgress size={18} sx={{ mr: 1 }} /> Asking...
                  </>
                ) : (
                  "Ask"
                )}
              </Button>
            </Box>
            {error ? (
              <Typography variant="body2" color="error">
                {error}
              </Typography>
            ) : null}
          </Stack>
        </Paper>
      </Grid>

      <Grid item xs={12} md={7}>
        <Paper sx={{ p: 3, minHeight: 300 }}>
          <Typography variant="h6" gutterBottom>
            Answer
          </Typography>
          {!result && !loading ? (
            <Typography variant="body2" color="text.secondary">
              Ask a question to see the answer here.
            </Typography>
          ) : null}
          {loading ? (
            <Box sx={{ display: "flex", alignItems: "center", mt: 2 }}>
              <CircularProgress size={20} sx={{ mr: 2 }} />
              <Typography variant="body2">Generating answer...</Typography>
            </Box>
          ) : null}
          {result ? (
            <Stack spacing={2}>
              <Typography variant="body1" sx={{ whiteSpace: "pre-wrap" }}>
                {result.answer}
              </Typography>
              {result.sources?.length ? (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Sources
                  </Typography>
                  <Stack spacing={1}>
                    {result.sources.map((s, idx) => {
                      const meta = s.metadata || {};
                      const pageLabel = extractPageLabel(meta);
                      const sourceKind =
                        typeof meta["source_kind"] === "string" ? meta["source_kind"] : null;
                      const jobId = typeof meta["job_id"] === "string" ? meta["job_id"] : "";
                      const paths = extractImagePaths(meta);

                      return (
                        <Box key={idx}>
                          <Typography variant="body2" sx={{ fontWeight: 500 }}>
                            [{idx + 1}] {s.title || "Chunk"}
                          </Typography>
                          {(pageLabel || sourceKind) && (
                            <Typography variant="caption" color="text.secondary">
                              {[pageLabel, sourceKind].filter(Boolean).join(" • ")}
                            </Typography>
                          )}
                          {s.snippet ? (
                            <Typography
                              variant="body2"
                              color="text.secondary"
                              sx={{ whiteSpace: "pre-wrap" }}
                            >
                              {s.snippet}
                            </Typography>
                          ) : null}

                          {!!jobId && paths.length > 0 && (
                            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mt: 1 }}>
                              {paths.slice(0, 2).map((p) => {
                                const k = `${jobId}|${p}`;
                                const u = evidenceUrls[k];
                                if (!u) return null;
                                return (
                                  <Box
                                    key={k}
                                    component="a"
                                    href={u}
                                    target="_blank"
                                    rel="noreferrer"
                                    sx={{ display: "inline-flex" }}
                                  >
                                    <Box
                                      component="img"
                                      src={u}
                                      alt={p}
                                      sx={{
                                        width: 220,
                                        maxWidth: "100%",
                                        height: "auto",
                                        borderRadius: 1,
                                        border: "1px solid",
                                        borderColor: "divider",
                                      }}
                                    />
                                  </Box>
                                );
                              })}
                            </Box>
                          )}
                        </Box>
                      );
                    })}
                  </Stack>
                </Box>
              ) : null}
            </Stack>
          ) : null}
        </Paper>
      </Grid>
    </Grid>
  );
}
