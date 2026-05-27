"""
Meraki Backup & Restore — RSITServices
Config Manager: Settings persistence
"""

import os
import json
import shutil
from pathlib import Path

DEFAULT_CONFIG = {
    "organizations": {},      # {org_id: {name, api_key, backup_destination, enabled}}
    "active_org_id": None,   # currently selected org_id
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

    # ─── Multi-org helpers ─────────────────────────────────────────

    def get_active_org(self):
        """Returns (org_id, org_config) for the active org, or (None, None)."""
        org_id = self._config.get("active_org_id")
        orgs = self._config.get("organizations", {})
        if org_id and org_id in orgs:
            return org_id, orgs[org_id]
        return None, None

    def get_active_api_key(self):
        _, org = self.get_active_org()
        return org.get("api_key", "") if org else ""

    def get_active_destination(self):
        _, org = self.get_active_org()
        return org.get("backup_destination", "") if org else ""

    def set_active_org(self, org_id):
        if org_id in self._config.get("organizations", {}):
            self._config["active_org_id"] = org_id
            self.save()

    def add_organization(self, org_id, name, api_key, backup_destination=""):
        orgs = self._config.setdefault("organizations", {})
        orgs[org_id] = {
            "name": name,
            "api_key": api_key,
            "backup_destination": backup_destination,
            "enabled": True,
        }
        if not self._config.get("active_org_id"):
            self._config["active_org_id"] = org_id
        self.save()

    def remove_organization(self, org_id):
        orgs = self._config.get("organizations", {})
        if org_id in orgs:
            del orgs[org_id]
            if self._config.get("active_org_id") == org_id:
                self._config["active_org_id"] = next(iter(orgs), None)
            self.save()

    def update_organization(self, org_id, **fields):
        orgs = self._config.setdefault("organizations", {})
        if org_id in orgs:
            orgs[org_id].update(fields)
            self.save()

    def list_organizations(self):
        return list(self._config.get("organizations", {}).keys())

    def mask_api_key(self, org_id=None):
        if org_id is None:
            org_id = self._config.get("active_org_id")
        org = self._config.get("organizations", {}).get(org_id, {})
        key = org.get("api_key", "")
        if len(key) >= 8:
            return key[:4] + "****" + key[-4:]
        return "****" if key else ""

    def is_configured(self):
        _, org = self.get_active_org()
        return bool(org and org.get("api_key", "").strip())