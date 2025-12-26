import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from src.utils.logger.config_loader import init_logging


class TestLoggingConfigLoader(unittest.TestCase):
    def setUp(self):
        self._old = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old)

    def test_load_json_and_env_override_level(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "dev.json"
            cfg = {
                "fra_config_version": 1,
                "adapter": "python",
                "logging": {
                    "version": 1,
                    "disable_existing_loggers": False,
                    "formatters": {"f": {"format": "%(levelname)s %(name)s %(message)s"}},
                    "handlers": {"c": {"class": "logging.StreamHandler", "level": "INFO", "formatter": "f", "stream": "ext://sys.stdout"}},
                    "root": {"level": "INFO", "handlers": ["c"]},
                },
            }
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

            os.environ["FRA_LOG_CONFIG_PATH"] = str(cfg_path)
            os.environ["FRA_LOG_LEVEL"] = "ERROR"
            mgr = init_logging()
            self.assertIsNotNone(mgr)

    def test_hot_reload(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "dev.json"
            cfg1 = {
                "fra_config_version": 1,
                "adapter": "python",
                "logging": {
                    "version": 1,
                    "disable_existing_loggers": False,
                    "formatters": {"f": {"format": "%(levelname)s %(name)s %(message)s"}},
                    "handlers": {"c": {"class": "logging.StreamHandler", "level": "INFO", "formatter": "f", "stream": "ext://sys.stdout"}},
                    "root": {"level": "INFO", "handlers": ["c"]},
                },
            }
            cfg2 = {
                "fra_config_version": 1,
                "adapter": "python",
                "logging": {
                    "version": 1,
                    "disable_existing_loggers": False,
                    "formatters": {"f": {"format": "%(levelname)s %(name)s %(message)s"}},
                    "handlers": {"c": {"class": "logging.StreamHandler", "level": "DEBUG", "formatter": "f", "stream": "ext://sys.stdout"}},
                    "root": {"level": "DEBUG", "handlers": ["c"]},
                },
            }

            cfg_path.write_text(json.dumps(cfg1), encoding="utf-8")
            os.environ["FRA_LOG_CONFIG_PATH"] = str(cfg_path)
            os.environ["FRA_LOG_HOT_RELOAD"] = "true"
            os.environ["FRA_LOG_RELOAD_INTERVAL_SECONDS"] = "0.1"

            mgr = init_logging()
            time.sleep(0.2)

            cfg_path.write_text(json.dumps(cfg2), encoding="utf-8")
            time.sleep(0.4)

            mgr.stop()


if __name__ == "__main__":
    unittest.main()