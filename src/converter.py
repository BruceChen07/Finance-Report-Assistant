import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple
from src.config import get_settings, ensure_dir

MINERU_MODES: Tuple[str, ...] = ("auto", "ocr", "txt")

def find_pdfs(input_dir: Path) -> List[Path]:
    return [p for p in input_dir.rglob("*.pdf") if p.is_file()]

def resolve_cli(name: str) -> str:
    py_bin = Path(sys.executable).parent
    candidates: List[Path] = []
    if sys.platform == "win32":
        candidates.extend([py_bin / f"{name}.exe", py_bin / name])
    else:
        candidates.append(py_bin / name)

    for p in candidates:
        if p.exists():
            return str(p)

    found = shutil.which(name)
    return found or name

def run_cmd(cmd: List[str]) -> Tuple[bool, str, str]:
    try:
        if cmd and cmd[0] and ("\\" not in cmd[0]) and ("/" not in cmd[0]):
            cmd = [resolve_cli(cmd[0])] + cmd[1:]
        
        s = get_settings()
        env = os.environ.copy()
        if s.use_modelscope:
            env["MODELSCOPE_SAMESITE"] = "True"
        env_device = getattr(s, "device", "cpu")
        env["FRA_DEVICE"] = env_device
        if env_device == "cuda":
            if "CUDA_VISIBLE_DEVICES" not in env and os.getenv("CUDA_VISIBLE_DEVICES"):
                env["CUDA_VISIBLE_DEVICES"] = os.getenv("CUDA_VISIBLE_DEVICES")
            vram_limit = getattr(s, "vram_limit", 0)
            if vram_limit and vram_limit > 0 and "PYTORCH_CUDA_ALLOC_CONF" not in env:
                env["PYTORCH_CUDA_ALLOC_CONF"] = f"max_split_size_mb:{vram_limit}"
            
        cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False, env=env)
        return cp.returncode == 0, cp.stdout, cp.stderr
    except FileNotFoundError:
        return False, "", "command not found"

def normalize_mineru_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    m = str(mode).strip().lower()
    if not m:
        return None
    if m not in MINERU_MODES:
        return None
    return m

def candidate_commands(pdf: Path, out_dir: Path, mode: str | None = None) -> List[List[str]]:
    m = normalize_mineru_mode(mode) or "auto"
    mineru_cli = resolve_cli("mineru")
    s = get_settings()
    
    # Build GPU configuration arguments
    gpu_args: List[str] = []
    if s.device and s.device.lower() != "auto":
        gpu_args.extend(["-d", s.device])
    if s.vram_limit > 0:
        gpu_args.extend(["--vram", str(s.vram_limit)])
    
    # Build base command with GPU args
    base_cmd = [mineru_cli, "-p", str(pdf), "-o", str(out_dir)] + gpu_args
    pipeline_cmd = [mineru_cli, "-p", str(pdf), "-o", str(out_dir), "-b", "pipeline", "-m", m] + gpu_args
    vlm_cmd = [mineru_cli, "-p", str(pdf), "-o", str(out_dir), "-b", "vlm-transformers"] + gpu_args
    
    return [base_cmd, pipeline_cmd, vlm_cmd]

def search_md(out_dir: Path, pdf_basename: str) -> Path | None:
    md_files = list(out_dir.rglob("*.md"))
    md_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in md_files:
        if pdf_basename.lower() in p.name.lower():
            return p
    return md_files[0] if md_files else None

def search_default_md(pdf_basename: str) -> Path | None:
    tmp = Path(tempfile.gettempdir())
    candidates = [tmp / "magic-pdf", tmp / "mineru", Path("/tmp/magic-pdf")] if sys.platform != "win32" else [tmp / "magic-pdf", tmp / "mineru"]
    for base in candidates:
        if base.exists():
            md_files = list(base.rglob("*.md"))
            md_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for p in md_files:
                if pdf_basename.lower() in p.name.lower():
                    return p
            if md_files:
                return md_files[0]
    return None

def convert_pdf(pdf: Path, out_dir: Path) -> Path:
    ensure_dir(out_dir)
    tried = []
    for cmd in candidate_commands(pdf, out_dir):
        ok, out, err = run_cmd(cmd)
        tried.append((cmd, ok, out, err))
        if ok:
            break
    md_path = search_md(out_dir, pdf.stem)
    if md_path is None:
        md_path = search_default_md(pdf.stem)
    if md_path is None:
        reason = "; ".join([f"{' '.join(c)} => {'ok' if o else 'fail'}" for c, o, _, _ in tried])
        raise RuntimeError(f"Failed to convert {pdf.name} with MinerU/magic-pdf. Tried: {reason}")
    target = out_dir / f"{pdf.stem}.md"
    if md_path.resolve() != target.resolve():
        ensure_dir(target.parent)
        shutil.copy2(md_path, target)
    return target
