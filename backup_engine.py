"""
Meraki Backup & Restore — RSITServices
BackupEngine: Full organization backup with progress tracking
"""

import os
import json
import time
import shutil
from datetime import datetime
from pathlib import Path
from api_client import MerakiAPIClient
from log_manager import log_manager


class BackupEngine:
    """Backup engine for full Meraki organization configuration"""

    def __init__(self, api_key, backup_destination=None, continue_on_error=True):
        self.api_key = api_key
        self.backup_destination = backup_destination or os.path.join(Path.home(), "meraki_backups")
        self.continue_on_error = continue_on_error
        self.client = MerakiAPIClient(api_key)
        self.log = log_manager
        self.errors = []
        self.warnings = []
        self._backup_start_time = None
        self._progress_callback = None

    def set_progress_callback(self, callback):
        """Set callback for progress updates: callback(step, total, message)"""
        self._progress_callback = callback

    def _report(self, step, total, message):
        if self._progress_callback:
            self._progress_callback(step, total, message)

    def backup_organization(self):
        """Perform full organization backup"""
        self._backup_start_time = datetime.now()
        timestamp = self._backup_start_time.strftime("%Y-%m-%d_%H-%M%S")
        backup_root = Path(self.backup_destination) / f"backup_{timestamp}"
        backup_root.mkdir(parents=True, exist_ok=True)

        self.log.info(f"Starting organization backup → {backup_root}")
        self._report(0, 100, "Initializing backup...")

        # ── Test connection first ──────────────────────────────────
        self.log.info("Testing API connection...")
        ok, err = self.client.test_connection()
        if not ok:
            self.log.error(f"API connection failed: {err}")
            return None, [f"Connection failed: {err}"]

        orgs, _ = self.client.get_organizations()
        if not orgs:
            return None, ["No organizations found"]

        org = orgs[0]
        org_id = org['id']
        org_name = org.get('name', 'unknown')
        self.log.info(f"Connected to organization: {org_name} (ID: {org_id})")

        # ── Save org metadata ─────────────────────────────────────
        meta = {
            "backup_timestamp": timestamp,
            "organization_id": org_id,
            "organization_name": org_name,
            "backup_version": "1.0",
            "meraki_api_version": "v1",
            "backup_date": self._backup_start_time.isoformat()
        }
        self._write_json(backup_root / "organization_meta.json", meta)

        # ── Fetch organization-level configs ─────────────────────
        self._backup_org_level(backup_root, org_id)

        # ── Fetch all networks ────────────────────────────────────
        networks, err = self.client.get_organization_networks(org_id)
        if err:
            self.errors.append(f"Failed to list networks: {err}")
            if not self.continue_on_error:
                return backup_root, self.errors

        if not networks:
            self.log.warning("No networks found in organization")
            self._write_summary(backup_root)
            return backup_root, self.errors

        total = len(networks)
        self.log.info(f"Found {total} networks to backup")

        # ── Backup each network ────────────────────────────────────
        for idx, network in enumerate(networks):
            net_id = network['id']
            net_name = network.get('name', 'unnamed')
            net_type = network.get('productTypes', [])

            self.log.info(f"[{idx+1}/{total}] Backing up network: {net_name} ({net_type})")
            self._report(int((idx / total) * 100), 100, f"Network {idx+1}/{total}: {net_name}")

            try:
                self._backup_network(backup_root, network)
            except Exception as e:
                self.log.log_exception(f"Failed to backup network {net_name}", e)
                self.errors.append(f"Network {net_name}: {str(e)}")
                if not self.continue_on_error:
                    break

        self._report(100, 100, "Backup complete")
        self._write_summary(backup_root)
        self.log.info(f"Backup complete. Errors: {len(self.errors)}, Warnings: {len(self.warnings)}")
        return backup_root, self.errors

    def _backup_org_level(self, backup_root, org_id):
        """Backup organization-level configs (admins, templates, etc.)"""
        self.log.debug("Backing up organization-level configs")

        # Admins
        self._backup_item(
            backup_root / "organization" / "admins.json",
            lambda: self.client.get_organization_admins(org_id),
            "organization_admins"
        )

        # SAML roles
        self._backup_item(
            backup_root / "organization" / "saml_roles.json",
            lambda: self.client.get_organization_saml_roles(org_id),
            "organization_saml_roles"
        )

        # Config templates
        self._backup_item(
            backup_root / "organization" / "config_templates.json",
            lambda: self.client.get_organization_config_templates(org_id),
            "config_templates"
        )

    def _backup_network(self, backup_root, network):
        """Backup a single network with all product configs"""
        net_id = network['id']
        net_name = self._safe_filename(network.get('name', net_id))
        net_dir = backup_root / "networks" / net_name
        net_dir.mkdir(parents=True, exist_ok=True)

        # Network metadata
        self._write_json(net_dir / "network_meta.json", network)

        product_types = network.get('productTypes', [])

        # ── MX Appliance ─────────────────────────────────────────
        if 'appliance' in product_types:
            self._backup_appliance(net_dir, net_id)

        # ── Switch ───────────────────────────────────────────────
        if 'switch' in product_types:
            self._backup_switch(net_dir, net_id)

        # ── Wireless ─────────────────────────────────────────────
        if 'wireless' in product_types:
            self._backup_wireless(net_dir, net_id)

        # ── Camera ───────────────────────────────────────────────
        if 'camera' in product_types:
            self._backup_camera(net_dir, net_id)

        # ── Cellular Gateway ─────────────────────────────────────
        if 'cellularGateway' in product_types:
            self._backup_cellular_gateway(net_dir, net_id)

        # ── Sensor ───────────────────────────────────────────────
        if 'sensor' in product_types:
            self._backup_sensor(net_dir, net_id)

        # ── SM (Systems Manager) ─────────────────────────────────
        if 'sm' in product_types:
            self._backup_sm(net_dir, net_id)

        # ── Devices ─────────────────────────────────────────────
        self._backup_devices(net_dir, net_id)

        # ── Clients (summary only) ───────────────────────────────
        self._backup_clients(net_dir, net_id)

        # ── Webhooks ─────────────────────────────────────────────
        self._backup_webhooks(net_dir, net_id)

    def _backup_appliance(self, net_dir, net_id):
        """Backup MX security appliance configs"""
        self.log.debug(f"  [MX] Backing up appliance config for {net_id}")

        # Firewall inbound rules
        self._backup_item(
            net_dir / "appliance" / "firewall_inbound_rules.json",
            lambda: self.client.get_appliance_firewall_inbound_rules(net_id),
            "firewall_inbound_rules"
        )

        # Firewall outbound rules
        self._backup_item(
            net_dir / "appliance" / "firewall_outbound_rules.json",
            lambda: self.client.get_appliance_firewall_outbound_rules(net_id),
            "firewall_outbound_rules"
        )

        # L3 firewall rules
        self._backup_item(
            net_dir / "appliance" / "firewall_l3_rules.json",
            lambda: self.client.get_appliance_firewall_l3_rules(net_id),
            "firewall_l3_rules"
        )

        # Traffic shaping
        self._backup_item(
            net_dir / "appliance" / "firewall_traffic_shaping.json",
            lambda: self.client.get_appliance_firewall_traffic_shaping(net_id),
            "traffic_shaping"
        )

        # VPN site-to-site
        self._backup_item(
            net_dir / "appliance" / "vpn_site_to_site.json",
            lambda: self.client.get_appliance_vpn(net_id),
            "vpn_site_to_site"
        )

        # Client VPN (IPsec)
        self._backup_item(
            net_dir / "appliance" / "vpn_client_ipsec.json",
            lambda: self.client.get_appliance_vpn_one_ipsec(net_id),
            "vpn_client_ipsec"
        )

        # Intrusion detection/prevention
        self._backup_item(
            net_dir / "appliance" / "security_intrusion.json",
            lambda: self.client.get_appliance_security_intrusion(net_id),
            "intrusion_detection"
        )

        # Content filtering
        self._backup_item(
            net_dir / "appliance" / "security_content_filtering.json",
            lambda: self.client.get_appliance_security_content_filtering(net_id),
            "content_filtering"
        )

        # Malware protection
        self._backup_item(
            net_dir / "appliance" / "security_malware.json",
            lambda: self.client.get_appliance_security_malware(net_id),
            "malware_protection"
        )

        # DHCP subnets
        self._backup_item(
            net_dir / "appliance" / "dhcp_subnets.json",
            lambda: self.client.get_appliance_dhcp(net_id),
            "dhcp_subnets"
        )

        # DNS settings
        self._backup_item(
            net_dir / "appliance" / "dns_settings.json",
            lambda: self.client.get_appliance_dns(net_id),
            "dns_settings"
        )

        # VLANs
        self._backup_item(
            net_dir / "appliance" / "vlans.json",
            lambda: self.client.get_appliance_vlans(net_id),
            "vlans"
        )

        # Warm spare
        self._backup_item(
            net_dir / "appliance" / "warm_spare.json",
            lambda: self.client.get_appliance_warm_spare(net_id),
            "warm_spare"
        )

        # Radio settings
        self._backup_item(
            net_dir / "appliance" / "radio_settings.json",
            lambda: self.client.get_appliance_radio_settings(net_id),
            "radio_settings"
        )

    def _backup_switch(self, net_dir, net_id):
        """Backup switch configs"""
        self.log.debug(f"  [MS] Backing up switch config for {net_id}")

        # Switch stacks
        self._backup_item(
            net_dir / "switch" / "stacks.json",
            lambda: self.client.get_switch_stacks(net_id),
            "switch_stacks"
        )

        # Storm control
        self._backup_item(
            net_dir / "switch" / "storm_control.json",
            lambda: self.client.get_switch_storm_control(net_id),
            "storm_control"
        )

        # Port mirroring
        self._backup_item(
            net_dir / "switch" / "mirror.json",
            lambda: self.client.get_switch_mirror(net_id),
            "port_mirroring"
        )

        # POE settings
        self._backup_item(
            net_dir / "switch" / "poe.json",
            lambda: self.client.get_switch_poe(net_id),
            "poe"
        )

        # QoS rules
        self._backup_item(
            net_dir / "switch" / "qos_rules.json",
            lambda: self.client.get_switch_qos_rules(net_id),
            "qos_rules"
        )

        # DSCP tagging
        self._backup_item(
            net_dir / "switch" / "dscp_tagging.json",
            lambda: self.client.get_switch_dscp_tagging(net_id),
            "dscp_tagging"
        )

        # ACLs
        self._backup_item(
            net_dir / "switch" / "access_control_lists.json",
            lambda: self.client.get_switch_access_control_lists(net_id),
            "access_lists"
        )

        # Port schedules
        self._backup_item(
            net_dir / "switch" / "port_schedules.json",
            lambda: self.client.get_switch_port_schedules(net_id),
            "port_schedules"
        )

        # Switch settings
        self._backup_item(
            net_dir / "switch" / "settings.json",
            lambda: self.client.get_switch_settings(net_id),
            "switch_settings"
        )

        # DHCP server policy
        self._backup_item(
            net_dir / "switch" / "dhcp_server_policy.json",
            lambda: self.client.get_switch_dhcp_server_policy(net_id),
            "dhcp_server_policy"
        )

    def _backup_wireless(self, net_dir, net_id):
        """Backup wireless configs"""
        self.log.debug(f"  [MR] Backing up wireless config for {net_id}")

        # SSIDs
        self._backup_item(
            net_dir / "wireless" / "ssids.json",
            lambda: self.client.get_wireless_ssids(net_id),
            "ssids"
        )

        # BSSIDs
        self._backup_item(
            net_dir / "wireless" / "bssids.json",
            lambda: self.client.get_wireless_bssid(net_id),
            "bssids"
        )

        # Wireless clients
        self._backup_item(
            net_dir / "wireless" / "clients.json",
            lambda: self.client.get_wireless_clients(net_id),
            "wireless_clients"
        )

        # Failed connections
        self._backup_item(
            net_dir / "wireless" / "failed_connections.json",
            lambda: self.client.get_wireless_failed_connections(net_id),
            "failed_connections"
        )

        # RF profiles
        self._backup_item(
            net_dir / "wireless" / "rf_profiles.json",
            lambda: self.client.get_wireless_rf_profiles(net_id),
            "rf_profiles"
        )

        # Air Marshal
        self._backup_item(
            net_dir / "wireless" / "air_marshal.json",
            lambda: self.client.get_wireless_air_marshal(net_id),
            "air_marshal"
        )

        # Wireless settings
        self._backup_item(
            net_dir / "wireless" / "settings.json",
            lambda: self.client.get_wireless_settings(net_id),
            "wireless_settings"
        )

        # Alternate management interface
        self._backup_item(
            net_dir / "wireless" / "alternate_mgmt_interface.json",
            lambda: self.client.get_wireless_alternate_management_interface(net_id),
            "alt_mgmt_interface"
        )

    def _backup_camera(self, net_dir, net_id):
        """Backup camera configs"""
        self.log.debug(f"  [MV] Backing up camera config for {net_id}")

        self._backup_item(
            net_dir / "camera" / "cameras.json",
            lambda: self.client.get_camera_sensors(net_id),
            "cameras"
        )

        self._backup_item(
            net_dir / "camera" / "quality_limits.json",
            lambda: self.client.get_camera_quality(net_id),
            "camera_quality"
        )

        self._backup_item(
            net_dir / "camera" / "sense.json",
            lambda: self.client.get_camera_sense(net_id),
            "camera_sense"
        )

        self._backup_item(
            net_dir / "camera" / "zones.json",
            lambda: self.client.get_camera_zones(net_id),
            "camera_zones"
        )

        self._backup_item(
            net_dir / "camera" / "schedules.json",
            lambda: self.client.get_camera_schedules(net_id),
            "camera_schedules"
        )

    def _backup_cellular_gateway(self, net_dir, net_id):
        """Backup cellular gateway configs"""
        self.log.debug(f"  [MG] Backing up cellular gateway config for {net_id}")

        self._backup_item(
            net_dir / "cellular_gateway" / "settings.json",
            lambda: self.client.get_cellular_gateway_settings(net_id),
            "cellular_settings"
        )

        self._backup_item(
            net_dir / "cellular_gateway" / "connectivity_tracking.json",
            lambda: self.client.get_cellular_gateway_connectivity(net_id),
            "connectivity_tracking"
        )

    def _backup_sensor(self, net_dir, net_id):
        """Backup sensor configs"""
        self.log.debug(f"  [MT] Backing up sensor config for {net_id}")

        self._backup_item(
            net_dir / "sensor" / "sensors.json",
            lambda: self.client.get_sensor_sensors(net_id),
            "sensors"
        )

        self._backup_item(
            net_dir / "sensor" / "alerts.json",
            lambda: self.client.get_sensor_alerts(net_id),
            "sensor_alerts"
        )

        self._backup_item(
            net_dir / "sensor" / "mqtt_broker.json",
            lambda: self.client.get_sensor_mqtt_broker(net_id),
            "mqtt_broker"
        )

    def _backup_sm(self, net_dir, net_id):
        """Backup Systems Manager configs"""
        self.log.debug(f"  [SM] Backing up SM config for {net_id}")

        self._backup_item(
            net_dir / "sm" / "profiles.json",
            lambda: self.client.get_sm_profiles(net_id),
            "sm_profiles"
        )

        self._backup_item(
            net_dir / "sm" / "devices.json",
            lambda: self.client.get_sm_device_certificates(net_id),
            "sm_devices"
        )

    def _backup_devices(self, net_dir, net_id):
        """Backup network devices"""
        self.log.debug(f"  [*] Backing up devices for {net_id}")

        self._backup_item(
            net_dir / "devices" / "devices.json",
            lambda: self.client.get_network_devices(net_id),
            "devices"
        )

    def _backup_clients(self, net_dir, net_id):
        """Backup client summary (not full history)"""
        self._backup_item(
            net_dir / "clients" / "clients_summary.json",
            lambda: self.client.get_network_clients(net_id, total_pages=1),
            "clients_summary"
        )

    def _backup_webhooks(self, net_dir, net_id):
        """Backup webhook configs"""
        self._backup_item(
            net_dir / "webhooks" / "webhooks.json",
            lambda: self.client.get_webhooks(net_id),
            "webhooks"
        )

        self._backup_item(
            net_dir / "webhooks" / "payload_templates.json",
            lambda: self.client.get_webhook_payload_templates(net_id),
            "webhook_templates"
        )

    # ── Utility methods ─────────────────────────────────────────

    def _backup_item(self, file_path, fetch_func, label):
        """Fetch and save a single config item"""
        try:
            data, err = fetch_func()
            if err:
                self.warnings.append(f"{label}: {err}")
                self._write_json(file_path, {"error": err, "label": label})
            else:
                self._write_json(file_path, data if data is not None else {})
        except Exception as e:
            self.log.log_exception(f"Backup item failed: {label}", e)
            self.warnings.append(f"{label}: {str(e)}")
            self._write_json(file_path, {"error": str(e), "label": label})

    def _write_json(self, file_path, data):
        """Write JSON data to file"""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log.error(f"Failed to write {file_path}: {e}")

    def _write_summary(self, backup_root):
        """Write backup summary after completion"""
        summary = {
            "backup_timestamp": self._backup_start_time.isoformat() if self._backup_start_time else "",
            "errors": self.errors,
            "warnings": self.warnings,
            "total_errors": len(self.errors),
            "total_warnings": len(self.warnings)
        }
        self._write_json(backup_root / "backup_summary.json", summary)

    def _safe_filename(self, name):
        """Convert network name to safe directory name"""
        keep = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_')
        return ''.join(c if c in keep else '_' for c in name)[:100]

    # ── Static analysis ─────────────────────────────────────────

    @staticmethod
    def list_available_backups(backup_destination):
        """List all backups in the backup directory"""
        backup_dir = Path(backup_destination)
        if not backup_dir.exists():
            return []
        backups = []
        for item in sorted(backup_dir.iterdir(), reverse=True):
            if item.is_dir() and item.name.startswith("backup_"):
                meta_file = item / "organization_meta.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text())
                        backups.append({
                            "path": str(item),
                            "timestamp": item.name.replace("backup_", ""),
                            "org_name": meta.get("organization_name", "Unknown"),
                            "org_id": meta.get("organization_id", ""),
                            "backup_date": meta.get("backup_date", "")
                        })
                    except Exception:
                        backups.append({
                            "path": str(item),
                            "timestamp": item.name.replace("backup_", ""),
                            "org_name": "Unknown",
                            "org_id": "",
                            "backup_date": ""
                        })
        return backups

    @staticmethod
    def inspect_backup(backup_path):
        """Return structure and contents summary of a backup"""
        root = Path(backup_path)
        if not root.exists():
            return None

        result = {
            "timestamp": root.name,
            "networks": [],
            "organization": None,
            "total_files": 0
        }

        # Organization meta
        org_meta = root / "organization_meta.json"
        if org_meta.exists():
            result["organization"] = json.loads(org_meta.read_text())

        # Networks
        networks_dir = root / "networks"
        if networks_dir.exists():
            for net_dir in sorted(networks_dir.iterdir()):
                if net_dir.is_dir():
                    net_meta_file = net_dir / "network_meta.json"
                    net_meta = json.loads(net_meta_file.read_text()) if net_meta_file.exists() else {}

                    # Count files in network backup
                    file_count = sum(1 for _ in net_dir.rglob("*") if _.is_file())

                    result["networks"].append({
                        "name": net_meta.get("name", net_dir.name),
                        "id": net_meta.get("id", ""),
                        "product_types": net_meta.get("productTypes", []),
                        "files": file_count
                    })
                    result["total_files"] += file_count

        return result