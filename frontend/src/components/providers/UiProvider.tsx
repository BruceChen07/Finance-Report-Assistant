/**
 * UI provider:
 * - Global loading indicator (Backdrop)
 * - Toast notifications (Snackbar + Alert)
 */
import React, { PropsWithChildren, createContext, useContext, useMemo, useState } from "react";
import { Alert, Backdrop, CircularProgress, Snackbar } from "@mui/material";

type Toast = { open: boolean; message: string; severity: "success" | "info" | "warning" | "error" };

type UiCtx = {
  loading: boolean;
  setLoading: (v: boolean) => void;
  toast: (message: string, severity?: Toast["severity"]) => void;
};

const Ctx = createContext<UiCtx | null>(null);

export function UiProvider({ children }: PropsWithChildren) {
  const [loading, setLoading] = useState(false);
  const [toastState, setToastState] = useState<Toast>({ open: false, message: "", severity: "info" });

  const toast = (message: string, severity: Toast["severity"] = "info") => {
    setToastState({ open: true, message, severity });
  };

  const value = useMemo(() => ({ loading, setLoading, toast }), [loading]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <Backdrop open={loading} sx={{ zIndex: (t) => t.zIndex.modal + 1 }}>
        <CircularProgress color="secondary" />
      </Backdrop>
      <Snackbar
        open={toastState.open}
        autoHideDuration={2500}
        onClose={() => setToastState((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          onClose={() => setToastState((s) => ({ ...s, open: false }))}
          severity={toastState.severity}
          variant="filled"
          sx={{ width: "100%" }}
        >
          {toastState.message}
        </Alert>
      </Snackbar>
    </Ctx.Provider>
  );
}

export function useUi(): UiCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("UiProvider missing");
  return v;
}