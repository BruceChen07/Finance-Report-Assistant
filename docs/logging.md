# Configurable Logging System

## Overview
This project uses Python `logging.config.dictConfig` as the runtime logging engine and supports config files under `config/logging/` with hot reload.

## Config Directory
- `config/logging/development.json`
- `config/logging/production.json`
- `config/logging/test.json`

Default selection:
- `FRA_LOG_PROFILE` or `FRA_ENV` controls profile name (default: `development`)
- If no matching file exists, the system falls back to a built-in default config.

## Supported Formats
- JSON: `.json` (default)
- YAML: `.yaml` / `.yml` (requires `PyYAML`)
- TOML: `.toml` (requires Python 3.11+ `tomllib`)

## Config Schema
Top-level wrapper:
- `fra_config_version`: integer, default 1
- `adapter`: `python` (runtime), `winston` / `log4j` reserved for export use
- `logging`: a standard Python `dictConfig` object with required fields:
  - `version`: must be `1`
  - `formatters`
  - `handlers`
  - `root`
  - optional `loggers`

## Environment Variable Overrides
- `FRA_LOG_CONFIG_PATH`: absolute path to a config file (overrides profile selection)
- `FRA_LOG_PROFILE`: `development` / `production` / `test` (default `development`)
- `FRA_LOG_LEVEL`: overrides `root.level`
- `FRA_LOG_DIR`: directory for file handlers with relative `filename`
- `FRA_LOG_MAX_BYTES`: overrides RotatingFileHandler `maxBytes`
- `FRA_LOG_BACKUP_COUNT`: overrides `backupCount` for rotating handlers
- `FRA_LOG_HOT_RELOAD`: `true/false` (default `true`)
- `FRA_LOG_RELOAD_INTERVAL_SECONDS`: polling interval for config reload (default `2.0`)

## Log Files
With default templates and `FRA_LOG_DIR` unset, files are written to:
- `output/logs/fra.log`
- `output/logs/fra-access.log`

Rotation:
- development: size-based rotation
- production: time-based rotation (daily)

## How Hot Reload Works
When `FRA_LOG_HOT_RELOAD=true`, the server polls the config file mtime and re-applies `dictConfig` if changes are detected.

## Test Plan (Integration)
- Start backend with `FRA_LOG_PROFILE=development`, verify both console and file logs are produced.
- Trigger requests and confirm `fra-access.log` records HTTP access.
- Modify `config/logging/development.json` level from `INFO` to `DEBUG`, verify the change takes effect without restart.
- Run conversion job and confirm mineru output lines appear in `fra.log` under logger `fra.job`.