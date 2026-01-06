import os
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

@dataclass(frozen=True)
class Settings:
    output_root: Path
    history_path: Path
    jwt_secret: str
    jwt_ttl_seconds: int
    username: str
    password: str
    cors_origins: List[str]
    static_dist_dir: Path
    log_dir: Path
    log_level: str
    log_max_bytes: int
    log_backup_count: int
    job_ttl_hours: int = 24
    use_modelscope: bool = True
    device: str = "auto"
    vram_limit: int = 0

_SETTINGS: Settings | None = None

def get_settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is not None:
        return _SETTINGS
    
    output_root = Path(os.getenv("FRA_OUTPUT_ROOT", str(Path("output").resolve())))
    history_path = Path(os.getenv("FRA_HISTORY_PATH", str((output_root / "history.jsonl").resolve())))
    cors_origins_raw = os.getenv("FRA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
    log_dir = Path(os.getenv("FRA_LOG_DIR", str((output_root / "logs").resolve())))
    
    device_env = os.getenv("FRA_DEVICE", "auto").lower()
    if device_env == "auto":
        device = "cuda" if is_cuda_available() else "cpu"
    else:
        device = device_env
    vram_limit = int(os.getenv("FRA_VRAM_LIMIT", "0"))
    _SETTINGS = Settings(
        output_root=output_root,
        history_path=history_path,
        jwt_secret=os.getenv("FRA_JWT_SECRET", "change-me-in-production"),
        jwt_ttl_seconds=int(os.getenv("FRA_JWT_TTL_SECONDS", "86400")),
        username=os.getenv("FRA_USERNAME", "admin"),
        password=os.getenv("FRA_PASSWORD", "admin"),
        cors_origins=cors_origins,
        static_dist_dir=Path(os.getenv("FRA_STATIC_DIST_DIR", str((Path(__file__).resolve().parents[1] / "frontend" / "dist").resolve()))),
        log_dir=log_dir,
        log_level=os.getenv("FRA_LOG_LEVEL", "INFO").upper(),
        log_max_bytes=int(os.getenv("FRA_LOG_MAX_BYTES", "10485760")),
        log_backup_count=int(os.getenv("FRA_LOG_BACKUP_COUNT", "10")),
        job_ttl_hours=int(os.getenv("FRA_JOB_TTL_HOURS", "24")),
        use_modelscope=os.getenv("FRA_USE_MODELSCOPE", "True").lower() == "true",
        device=device,
        vram_limit=vram_limit,
    )
    return _SETTINGS

def is_cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False

def ensure_dir(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
