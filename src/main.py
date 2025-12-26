import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

# Fix for ModuleNotFoundError when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings, ensure_dir
from src.converter import convert_pdf
from src.jobs import perform_cleanup

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
    t = threading.Thread(target=cleanup_loop, name="fra-cleanup", daemon=True)
    t.start()

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