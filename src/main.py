import argparse
import logging
import os
import sys
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

# Fix for ModuleNotFoundError when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings, ensure_dir
from src.converter import convert_pdf
from src.jobs import perform_cleanup
from src.db.connection import init_db

def _disable_vlm_transformers_when_missing() -> None:
    """Disable MinerU VLM transformers backend when `transformers` isn't installed."""
    try:
        import transformers  # noqa: F401
    except Exception:
        # Converter may try a VLM backend that requires `transformers`.
        os.environ.setdefault("FRA_DISABLE_VLM_TRANSFORMERS", "1")

def configure_logging() -> None:
    try:
        from src.utils.logger.config_loader import init_logging
        init_logging()
    except Exception:
        logging.basicConfig(
            level=logging.INFO,
            stream=sys.stdout,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

def start_background_tasks():
    def cleanup_loop():
        time.sleep(10)
        while True:
            try:
                perform_cleanup()
            except Exception as e:
                logging.getLogger("fra.cleanup").error(f"Cleanup error: {e}")
            time.sleep(3600)

    def backup_loop():
        time.sleep(15)
        while True:
            try:
                s = get_settings()
                chroma_dir = Path(os.getenv("FRA_CHROMA_DIR", str((s.output_root / "chroma").resolve())))
                if chroma_dir.exists() and chroma_dir.is_dir():
                    backups_dir = (s.output_root / "backups").resolve()
                    ensure_dir(backups_dir)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    out = backups_dir / f"chroma_{ts}.zip"
                    with zipfile.ZipFile(str(out), "w", compression=zipfile.ZIP_DEFLATED) as zf:
                        for p in chroma_dir.rglob("*"):
                            if p.is_file():
                                rel = p.relative_to(chroma_dir)
                                zf.write(str(p), arcname=str(rel))

                    keep = int(os.getenv("FRA_CHROMA_BACKUP_KEEP", "10"))
                    all_baks = sorted([x for x in backups_dir.glob("chroma_*.zip") if x.is_file()], key=lambda x: x.stat().st_mtime, reverse=True)
                    for old in all_baks[keep:]:
                        try:
                            old.unlink()
                        except Exception:
                            pass
            except Exception as e:
                logging.getLogger("fra.backup").error(f"Backup error: {e}")

            interval = int(os.getenv("FRA_CHROMA_BACKUP_INTERVAL_SECONDS", "86400"))
            time.sleep(max(60, interval))

    t1 = threading.Thread(target=cleanup_loop, name="fra-cleanup", daemon=True)
    t1.start()

    t2 = threading.Thread(target=backup_loop, name="fra-chroma-backup", daemon=True)
    t2.start()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--host", default=os.getenv("FRA_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("FRA_PORT", "8000")))
    ap.add_argument("--input", default=str(Path("data").resolve()))
    ap.add_argument("--output", default=str(get_settings().output_root.resolve()))
    args = ap.parse_args()

    configure_logging()
    _disable_vlm_transformers_when_missing()
    try:
        init_db()
    except Exception as e:
        logging.getLogger("fra.db").error(f"Failed to init SQLite DB: {e}")

    if args.serve:
        try:
            import uvicorn
            from src.api import app
        except ImportError as e:
            print(f"Missing dependencies for server: {e}")
            return 2
        
        start_background_tasks()
        s = get_settings()
        uvicorn.run(app, host=args.host, port=args.port, log_level=s.log_level.lower(), log_config=None, access_log=True)
        return 0

    # CLI Batch Mode
    in_dir, out_dir = Path(args.input), Path(args.output)
    if not in_dir.exists():
        print(f"Input dir not found: {in_dir}")
        return 2
    
    pdfs = [p for p in in_dir.rglob("*.pdf") if p.is_file()]
    if not pdfs:
        print(f"No PDFs found in {in_dir}")
        return 0

    ensure_dir(out_dir)
    success_count = 0
    for pdf in pdfs:
        try:
            md = convert_pdf(pdf, out_dir)
            print(f"DONE: {pdf.name} -> {md.name}")
            success_count += 1
        except Exception as e:
            print(f"FAIL: {pdf.name} -> {e}")
    
    print(f"Finished | {success_count}/{len(pdfs)} succeeded")
    return 0 if success_count > 0 else 1

if __name__ == "__main__":
    sys.exit(main())