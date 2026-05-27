"""
Meraki Backup & Restore — RSITServices
Config Manager: Settings persistence
"""

import os
import json
import shutil
from pathlib import Path

DEFAULT_CONFIG = {
    "api_key": "",
    "backup_destination": "",
    "log_level": "DEBUG",
    "auto_backup_enabled": False,
    "auto_backup_cron": "0 2 * * *",
    "confirm_before_restore": True,
    "dry_run_by_default": False,
    "continue_on_error": True,
    "max_log_size_mb": 10,
    "log_backup_count": 5
}

class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / ".meraki_backup_restore"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self._config = self._load()

    def _load(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    loaded = json.load(f)
                # Merge with defaults for any missing keys
                cfg = dict(DEFAULT_CONFIG)
                cfg.update(loaded)
                return cfg
            except Exception:
                pass
        return dict(DEFAULT_CONFIG)

    def save(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            print(f"[CONFIG] Failed to save config: {e}")

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value
        self.save()

    def mask_api_key(self):
        key = self._config.get("api_key", "")
        if len(key) >= 8:
            return key[:4] + "****" + key[-4:]
        return "****" if key else ""

    def is_configured(self):
        return bool(self._config.get("api_key", "").strip())