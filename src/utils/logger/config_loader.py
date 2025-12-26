import json
import logging
import logging.config
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # py>=3.11
except Exception:
    tomllib = None

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


_ALLOWED_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_config_dir() -> Path:
    return _project_root() / "config" / "logging"


def _parse_bool(v: str | None, default: bool) -> bool:
    if v is None:
        return default
    s = v.strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _load_config_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    raw: dict[str, Any]

    if suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
    elif suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is not installed")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))  # type: ignore[assignment]
        if not isinstance(raw, dict):
            raise ValueError("yaml root must be an object")
    elif suffix == ".toml":
        if tomllib is None:
            raise RuntimeError("tomllib is not available")
        raw = tomllib.loads(path.read_text(encoding="utf-8"))  # type: ignore[assignment]
        if not isinstance(raw, dict):
            raise ValueError("toml root must be an object")
    else:
        raise ValueError(f"unsupported config file format: {suffix}")

    if "logging" in raw and isinstance(raw["logging"], dict):
        return raw
    if "version" in raw and "handlers" in raw and "root" in raw:
        return {"fra_config_version": 1, "adapter": "python", "logging": raw}
    raise ValueError("invalid config: missing logging section")


def _validate_config(raw: dict[str, Any]) -> None:
    v = raw.get("fra_config_version", 1)
    if not isinstance(v, int) or v < 1:
        raise ValueError("fra_config_version must be a positive int")

    adapter = raw.get("adapter", "python")
    if adapter not in {"python", "winston", "log4j"}:
        raise ValueError("adapter must be one of: python, winston, log4j")

    cfg = raw.get("logging")
    if not isinstance(cfg, dict):
        raise ValueError("logging must be an object")

    if cfg.get("version") != 1:
        raise ValueError("logging.version must be 1 (Python dictConfig requirement)")

    root = cfg.get("root")
    handlers = cfg.get("handlers")
    if not isinstance(root, dict) or not isinstance(handlers, dict):
        raise ValueError("logging.root and logging.handlers must be objects")

    level = str(root.get("level", "INFO")).upper()
    if level not in _ALLOWED_LEVELS:
        raise ValueError("root.level must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL")


def _ensure_log_dir_exists(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(raw)
    logging_cfg = dict(cfg["logging"])
    cfg["logging"] = logging_cfg

    root = dict(logging_cfg.get("root", {}))
    logging_cfg["root"] = root

    env_level = os.getenv("FRA_LOG_LEVEL")
    if env_level:
        root["level"] = env_level.strip().upper()

    log_dir = Path(os.getenv("FRA_LOG_DIR", str((_project_root() / "output" / "logs").resolve())))
    _ensure_log_dir_exists(log_dir)

    max_bytes = os.getenv("FRA_LOG_MAX_BYTES")
    backup_count = os.getenv("FRA_LOG_BACKUP_COUNT")

    handlers = dict(logging_cfg.get("handlers", {}))
    logging_cfg["handlers"] = handlers

    for hname, hcfg_any in list(handlers.items()):
        if not isinstance(hcfg_any, dict):
            continue
        hcfg = dict(hcfg_any)

        if "filename" in hcfg:
            fn = str(hcfg["filename"])
            p = Path(fn)
            if not p.is_absolute():
                hcfg["filename"] = str((log_dir / p.name).resolve())

        cls = str(hcfg.get("class", ""))
        if max_bytes and cls.endswith("RotatingFileHandler"):
            try:
                hcfg["maxBytes"] = int(max_bytes)
            except Exception:
                pass
        if backup_count and (cls.endswith("RotatingFileHandler") or cls.endswith("TimedRotatingFileHandler")):
            try:
                hcfg["backupCount"] = int(backup_count)
            except Exception:
                pass

        handlers[hname] = hcfg

    return cfg


def _default_dict_config() -> dict[str, Any]:
    log_dir = Path(os.getenv("FRA_LOG_DIR", str((_project_root() / "output" / "logs").resolve())))
    _ensure_log_dir_exists(log_dir)

    level = os.getenv("FRA_LOG_LEVEL", "INFO").upper()
    max_bytes = int(os.getenv("FRA_LOG_MAX_BYTES", "10485760"))
    backup_count = int(os.getenv("FRA_LOG_BACKUP_COUNT", "10"))

    return {
        "fra_config_version": 1,
        "adapter": "python",
        "logging": {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": level,
                    "formatter": "standard",
                    "stream": "ext://sys.stdout",
                },
                "app_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": level,
                    "formatter": "standard",
                    "filename": str((log_dir / "fra.log").resolve()),
                    "maxBytes": max_bytes,
                    "backupCount": backup_count,
                    "encoding": "utf-8",
                },
                "access_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": level,
                    "formatter": "standard",
                    "filename": str((log_dir / "fra-access.log").resolve()),
                    "maxBytes": max_bytes,
                    "backupCount": backup_count,
                    "encoding": "utf-8",
                },
            },
            "root": {"level": level, "handlers": ["console", "app_file"]},
            "loggers": {
                "uvicorn.error": {"level": level, "handlers": ["console", "app_file"], "propagate": False},
                "uvicorn.access": {"level": level, "handlers": ["console", "access_file"], "propagate": False},
                "fra.job": {"level": level, "handlers": ["console", "app_file"], "propagate": False},
            },
        },
    }


@dataclass
class LoggingManager:
    config_path: Path | None
    reload_enabled: bool
    reload_interval_seconds: float
    _stop: threading.Event
    _thread: threading.Thread | None

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def _apply_python_logging(raw: dict[str, Any]) -> None:
    logging.config.dictConfig(raw["logging"])


def _resolve_config_path(profile: str | None, config_path: str | None) -> Path | None:
    explicit = config_path or os.getenv("FRA_LOG_CONFIG_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()

    p = (profile or os.getenv("FRA_LOG_PROFILE") or os.getenv("FRA_ENV") or "development").strip().lower()
    base = _default_config_dir()
    for ext in (".json", ".yaml", ".yml", ".toml"):
        candidate = base / f"{p}{ext}"
        if candidate.exists():
            return candidate.resolve()
    return (base / f"{p}.json").resolve()


def init_logging(profile: str | None = None, config_path: str | None = None) -> LoggingManager:
    path = _resolve_config_path(profile, config_path)

    reload_enabled = _parse_bool(os.getenv("FRA_LOG_HOT_RELOAD"), default=True)
    interval = float(os.getenv("FRA_LOG_RELOAD_INTERVAL_SECONDS", "2.0"))

    raw: dict[str, Any]
    try:
        if path is None or not path.exists():
            raw = _default_dict_config()
        else:
            raw = _load_config_file(path)
    except Exception:
        raw = _default_dict_config()

    try:
        _validate_config(raw)
    except Exception:
        raw = _default_dict_config()

    raw2 = _apply_env_overrides(raw)
    _apply_python_logging(raw2)

    stop_evt = threading.Event()
    mgr = LoggingManager(config_path=path if path and path.exists() else None, reload_enabled=reload_enabled, reload_interval_seconds=interval, _stop=stop_evt, _thread=None)

    if not reload_enabled or mgr.config_path is None:
        return mgr

    def watcher() -> None:
        last_mtime = 0.0
        while not stop_evt.is_set():
            try:
                st = mgr.config_path.stat()
                mtime = st.st_mtime
                if mtime != last_mtime:
                    last_mtime = mtime
                    new_raw = _load_config_file(mgr.config_path)
                    _validate_config(new_raw)
                    new_raw2 = _apply_env_overrides(new_raw)
                    _apply_python_logging(new_raw2)
                    logging.getLogger("fra.logging").info("logging config reloaded: %s", str(mgr.config_path))
            except Exception as e:
                logging.getLogger("fra.logging").warning("logging config reload failed: %s", str(e))
            stop_evt.wait(interval)

    t = threading.Thread(target=watcher, name="fra-log-reloader", daemon=True)
    mgr._thread = t
    t.start()
    return mgr