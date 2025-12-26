#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Finance Report Assistant - Start Services (Linux)
# - Starts backend (FastAPI/Uvicorn) and frontend (Vite) from any working folder
# - Writes startup logs under: <project_root>/output/logs/
# - Performs basic dependency checks and prints status
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"

LOG_DIR="${ROOT_DIR}/output/logs"
mkdir -p "${LOG_DIR}"

DATE_STAMP="$(date +%Y%m%d_%H%M%S)"
BACKEND_LOG="${LOG_DIR}/backend_${DATE_STAMP}.log"
FRONTEND_LOG="${LOG_DIR}/frontend_${DATE_STAMP}.log"
BACKEND_PID_FILE="${LOG_DIR}/backend.pid"
FRONTEND_PID_FILE="${LOG_DIR}/frontend.pid"

echo "[INFO] Project root: ${ROOT_DIR}"
echo "[INFO] Logs:"
echo "       ${BACKEND_LOG}"
echo "       ${FRONTEND_LOG}"

# Warn if path contains non-ASCII characters (best-effort)
if ! printf '%s' "${ROOT_DIR}" | LC_ALL=C grep -q '^[ -~]*$'; then
  echo "[WARN] Project path contains non-ASCII characters. Some tools may misbehave:"
  echo "       ${ROOT_DIR}"
fi

# ---- Dependency checks ----
PY="${ROOT_DIR}/.venv/bin/python"
if [[ ! -x "${PY}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY="python3"
  elif command -v python >/dev/null 2>&1; then
    PY="python"
  else
    echo "[ERROR] Python not found. Install Python or create .venv under project root."
    exit 2
  fi
fi

if ! command -v node >/dev/null 2>&1; then
  echo "[ERROR] Node.js not found. Install Node.js (LTS recommended)."
  exit 2
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm not found. Ensure Node.js installation includes npm."
  exit 2
fi

if [[ ! -f "${FRONTEND_DIR}/package.json" ]]; then
  echo "[ERROR] Frontend package.json not found: ${FRONTEND_DIR}/package.json"
  exit 2
fi

if [[ ! -f "${ROOT_DIR}/src/main.py" ]]; then
  echo "[ERROR] Backend entry not found: ${ROOT_DIR}/src/main.py"
  exit 2
fi

echo "[INFO] Checking backend Python deps..."
if ! "${PY}" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "[ERROR] Missing backend deps. Run: pip install -r requirements.txt"
  exit 2
fi

echo "[INFO] Checking frontend deps..."
if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
  echo "[WARN] frontend/node_modules not found. Run npm install under frontend/ first."
fi

# ---- Environment variables ----
export FRA_HOST="${FRA_HOST:-127.0.0.1}"
export FRA_PORT="${FRA_PORT:-8000}"
export FRA_LOG_PROFILE="${FRA_LOG_PROFILE:-development}"
export FRA_LOG_DIR="${FRA_LOG_DIR:-${LOG_DIR}}"
export FRA_LOG_HOT_RELOAD="${FRA_LOG_HOT_RELOAD:-true}"
export FRA_LOG_RELOAD_INTERVAL_SECONDS="${FRA_LOG_RELOAD_INTERVAL_SECONDS:-2.0}"

# ---- Start backend ----
echo "[INFO] Starting backend on http://${FRA_HOST}:${FRA_PORT} ..."
(
  cd "${ROOT_DIR}"
  nohup "${PY}" -m src.main --serve >>"${BACKEND_LOG}" 2>&1 &
  echo $! > "${BACKEND_PID_FILE}"
)

# ---- Start frontend ----
echo "[INFO] Starting frontend (Vite dev server) on http://localhost:5173 ..."
(
  cd "${FRONTEND_DIR}"
  nohup npm run dev >>"${FRONTEND_LOG}" 2>&1 &
  echo $! > "${FRONTEND_PID_FILE}"
)

echo "[OK] Services started."
echo "[OK] Backend PID:  $(cat "${BACKEND_PID_FILE}")"
echo "[OK] Frontend PID: $(cat "${FRONTEND_PID_FILE}")"
echo "[OK] Backend logs:  ${BACKEND_LOG}"
echo "[OK] Frontend logs: ${FRONTEND_LOG}"
echo "[HINT] Stop with: kill \$(cat \"${BACKEND_PID_FILE}\") ; kill \$(cat \"${FRONTEND_PID_FILE}\")"