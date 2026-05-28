"""
Meraki Backup & Restore — RSITServices
RestoreEngine: Full organization/network restore with dry-run and rollback
"""

import os
import json
import time
from pathlib import Path
from api_client import MerakiAPIClient
from log_manager import log_manager


class RestoreEngine:
    """Restore engine with dry-run preview, validation, and rollback support"""

    def __init__(self, api_key, continue_on_error=True):
        self.api_key = api_key
        self.continue_on_error = continue_on_error
        self.client = MerakiAPIClient(api_key)
        self.log = log_manager
        self.errors = []
        self.warnings = []
        self.changes_preview = []
        self._restore_start_time = None
        self._progress_callback = None
        self._dry_run = False
        self._rollback_stack = []

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def _report(self, step, total, message):
        if self._progress_callback:
            self._progress_callback(step, total, message)

    # ── Load & Inspect ─────────────────────────────────────────

    def load_backup(self, backup_path):
        """Load and validate a backup directory"""
        root = Path(backup_path)
        if not root.exists():
            return None, [f"Backup path does not exist: {backup_path}"]

        meta_file = root / "organization_meta.json"
        if not meta_file.exists():
            return None, ["Invalid backup: no organization_meta.json found"]

        try:
            meta = json.loads(meta_file.read_text())
        except Exception as e:
            return None, [f"Failed to parse organization_meta.json: {e}"]

        # Validate required sections
        required = ["organization_id", "organization_name"]
        missing = [k for k in required if k not in meta]
        if missing:
            return None, [f"Missing required metadata fields: {missing}"]

        self.log.info(f"Backup loaded: {meta['organization_name']} ({meta['organization_id']})")
        return meta, []

    def preview_restore(self, backup_path, target_type="network", target_id=None):
        """Preview what changes will be made without applying them"""
        self._dry_run = True
        self.changes_preview = []
        self.changes_preview_by_net = {}  # net_id -> list of changes
        meta, errs = self.load_backup(backup_path)
        if errs:
            return [], errs

        root = Path(backup_path)
        networks_dir = root / "networks"

        if target_type == "full":
            # Full org restore — all networks
            if networks_dir.exists():
                for net_dir in sorted(networks_dir.iterdir()):
                    if net_dir.is_dir():
                        self._preview_network(net_dir)
        else:
            # Single network
            net_dir = networks_dir / target_id if target_id else None
            if net_dir and net_dir.exists():
                self._preview_network(net_dir)
            else:
                return [], [f"Network backup not found: {target_id}"]

        self._dry_run = False
        return self.changes_preview, []

    # Fields that are read-only / always differ between backup and live
    _IGNORE_FIELDS = frozenset({
        "id", "networkId", "organizationId",
        "creationTime", "lastUpdated", "updateTime", "createdAt", "updatedAt",
        "author", "人次",
    })

    def _normalize(self, data):
        """Strip dynamic/metadata fields from API response for stable comparison."""
        if data is None:
            return None
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                if k in self._IGNORE_FIELDS:
                    continue
                result[k] = self._normalize(v)
            return result
        if isinstance(data, list):
            # Normalize each item, then sort for stable comparison
            normalized = [self._normalize(item) for item in data]
            try:
                return sorted(normalized, key=lambda x: json.dumps(x, sort_keys=True))
            except TypeError:
                # Mixed types that can't be sorted together — compare as-is
                return normalized
        return data

    def _diff_values(self, backup_val, live_val):
        """Return True if values differ (needs restore), False if identical after normalization."""
        b = self._normalize(backup_val)
        l = self._normalize(live_val)
        # Treat [] and None as equivalent (empty list vs null)
        if isinstance(b, list) and len(b) == 0 and l is None:
            return False
        if isinstance(l, list) and len(l) == 0 and b is None:
            return False
        b_str = json.dumps(b, sort_keys=True) if isinstance(b, (dict, list)) else str(b) if b is not None else ""
        l_str = json.dumps(l, sort_keys=True) if isinstance(l, (dict, list)) else str(l) if l is not None else ""
        return b_str != l_str

    def _preview_network(self, net_dir):
        """Generate a preview of what will be restored for a network — compares live vs backup."""
        net_meta_file = net_dir / "network_meta.json"
        if not net_meta_file.exists():
            return

        net_meta = json.loads(net_meta_file.read_text())
        net_id = net_meta.get("id", "")
        net_name = net_meta.get("name", "unknown")
        net_id_key = str(net_id)

        # Track changes for this network
        net_changes = []

        # ── Appliance configs ─────────────────────────────────────
        appliance_dir = net_dir / "appliance"
        if appliance_dir.exists() and net_id:
            # Map file → (getter method name, display name)
            appliance_getters = [
                ("firewall_inbound_rules.json",  "get_appliance_firewall_inbound_rules",   "MX Inbound Firewall Rules"),
                ("firewall_outbound_rules.json", "get_appliance_firewall_outbound_rules",  "MX Outbound Firewall Rules"),
                ("firewall_l3_rules.json",       "get_appliance_firewall_l3_rules",        "MX L3 Firewall Rules"),
                ("firewall_traffic_shaping.json","get_appliance_firewall_traffic_shaping",  "MX Traffic Shaping"),
                ("vpn_site_to_site.json",        "get_appliance_vpn",                      "MX Site-to-Site VPN"),
                ("vpn_client_ipsec.json",        "get_appliance_vpn_one_ipsec",             "MX Client VPN (IPSec)"),
                ("security_intrusion.json",      "get_appliance_security_intrusion",        "MX IDS/IPS"),
                ("security_content_filtering.json","get_appliance_security_content_filtering","MX Content Filtering"),
                ("security_malware.json",         "get_appliance_security_malware",          "MX Malware Protection"),
                ("dhcp_subnets.json",            "get_appliance_dhcp",                      "MX DHCP Subnets"),
                ("dns_settings.json",             "get_appliance_dns",                       "MX DNS Settings"),
                ("vlans.json",                   "get_appliance_vlans",                     "MX VLANs"),
                ("warm_spare.json",              "get_appliance_warm_spare",                "MX Warm Spare"),
                ("radio_settings.json",          "get_appliance_radio_settings",            "MX Radio Settings"),
            ]

            for fname, getter_name, display_name in appliance_getters:
                fpath = appliance_dir / fname
                if not fpath.exists():
                    continue

                try:
                    backup_data = json.loads(fpath.read_text())
                except Exception:
                    continue

                # Skip error placeholders — these are API errors during backup, nothing to restore
                if isinstance(backup_data, dict) and "error" in backup_data:
                    net_changes.append({
                        "type": "appliance_config", "action": "skip",
                        "file": fname, "network": net_name,
                        "detail": f"{display_name} — backup returned error ({backup_data.get('error','?')[:60]})"
                    })
                    continue

                # Try to get live value
                live_data = None
                try:
                    getter = getattr(self.client, getter_name, None)
                    if getter and callable(getter):
                        live_data = getter(net_id)
                except Exception:
                    pass

                if live_data is None:
                    # No live value — would be created
                    net_changes.append({
                        "type": "appliance_config", "action": "create",
                        "file": fname, "network": net_name,
                        "detail": display_name
                    })
                elif self._diff_values(backup_data, live_data):
                    net_changes.append({
                        "type": "appliance_config", "action": "update",
                        "file": fname, "network": net_name,
                        "detail": display_name
                    })
                else:
                    # Identical — no change
                    net_changes.append({
                        "type": "appliance_config", "action": "no_change",
                        "file": fname, "network": net_name,
                        "detail": display_name
                    })

        # ── Switch configs ────────────────────────────────────────
        switch_dir = net_dir / "switch"
        if switch_dir.exists() and net_id:
            switch_files = [
                ("settings.json",       "_get_switch_settings",          "Switch Settings"),
                ("access_control_lists.json", "_get_switch_access_control_lists", "Switch ACLs"),
                ("poe.json",            "_get_switch_poe",               "Switch PoE"),
                ("qos_rules.json",      "_get_switch_qos_rules",         "Switch QoS Rules"),
                ("dscp_tagging.json",   "_get_switch_dscp_tagging",      "Switch DSCP Tagging"),
                ("port_schedules.json", "_get_switch_port_schedules",    "Switch Port Schedules"),
                ("storm_control.json",  "_get_switch_storm_control",     "Switch Storm Control"),
                ("mirror.json",         "_get_switch_mirror",            "Switch Mirror"),
            ]

            for fname, getter_name, display_name in switch_files:
                fpath = switch_dir / fname
                if not fpath.exists():
                    continue

                try:
                    backup_data = json.loads(fpath.read_text())
                except Exception:
                    continue

                if isinstance(backup_data, dict) and "error" in backup_data:
                    net_changes.append({
                        "type": "switch_config", "action": "skip",
                        "file": fname, "network": net_name,
                        "detail": f"{display_name} — backup returned error ({backup_data.get('error','?')[:60]})"
                    })
                    continue

                live_data = None
                try:
                    getter = getattr(self.client, getter_name, None)
                    if getter and callable(getter):
                        live_data = getter(net_id)
                except Exception:
                    pass

                if live_data is None:
                    net_changes.append({
                        "type": "switch_config", "action": "create",
                        "file": fname, "network": net_name,
                        "detail": display_name
                    })
                elif self._diff_values(backup_data, live_data):
                    net_changes.append({
                        "type": "switch_config", "action": "update",
                        "file": fname, "network": net_name,
                        "detail": display_name
                    })
                else:
                    net_changes.append({
                        "type": "switch_config", "action": "no_change",
                        "file": fname, "network": net_name,
                        "detail": display_name
                    })

        # ── Wireless configs ─────────────────────────────────────
        wireless_dir = net_dir / "wireless"
        if wireless_dir.exists() and net_id:
            wireless_files = [
                ("ssids.json",      "_get_wireless_ssids",                          "Wireless SSIDs"),
                ("rf_profiles.json","_get_wireless_rf_profiles",                     "Wireless RF Profiles"),
                ("settings.json",   "_get_wireless_settings",                       "Wireless Settings"),
                ("air_marshal.json","get_wireless_air_marshal",                     "Air Marshal"),
            ]

            for fname, getter_name, display_name in wireless_files:
                fpath = wireless_dir / fname
                if not fpath.exists():
                    continue

                try:
                    backup_data = json.loads(fpath.read_text())
                except Exception:
                    continue

                if isinstance(backup_data, dict) and "error" in backup_data:
                    net_changes.append({
                        "type": "wireless_config", "action": "skip",
                        "file": fname, "network": net_name,
                        "detail": f"{display_name} — backup returned error ({backup_data.get('error','?')[:60]})"
                    })
                    continue

                live_data = None
                try:
                    getter = getattr(self.client, getter_name, None)
                    if getter and callable(getter):
                        live_data = getter(net_id)
                except Exception:
                    pass

                if live_data is None:
                    net_changes.append({
                        "type": "wireless_config", "action": "create",
                        "file": fname, "network": net_name,
                        "detail": display_name
                    })
                elif self._diff_values(backup_data, live_data):
                    net_changes.append({
                        "type": "wireless_config", "action": "update",
                        "file": fname, "network": net_name,
                        "detail": display_name
                    })
                else:
                    net_changes.append({
                        "type": "wireless_config", "action": "no_change",
                        "file": fname, "network": net_name,
                        "detail": display_name
                    })

        # Store changes keyed by network
        self.changes_preview_by_net[net_id_key] = net_changes
        # Flat list for UI (only include actual changes, not no_change)
        for c in net_changes:
            if c["action"] != "no_change":
                self.changes_preview.append(c)

    # ── Execute Restore ─────────────────────────────────────────

    def restore_organization(self, backup_path, options=None):
        """
        Execute full organization restore.
        options: {
            "dry_run": bool,
            "target_networks": list of network names/ids or None for all,
            "skip_existing": bool (skip networks that already exist)
        }
        """
        opts = options or {}
        self._dry_run = opts.get("dry_run", False)
        self._restore_start_time = time.time()
        self.errors = []
        self.warnings = []
        self._rollback_stack = []

        root = Path(backup_path)
        meta, errs = self.load_backup(backup_path)
        if errs:
            return self.errors

        org_id = meta["organization_id"]

        # Verify target org exists
        orgs, _ = self.client.get_organizations()
        matching = [o for o in (orgs or []) if o['id'] == org_id]
        if not matching:
            self.log.error(f"Organization {org_id} not found in current account — cannot restore")
            self.errors.append(f"Organization {org_id} not found. Restore requires matching API key.")
            return self.errors

        self.log.info(f"Starting restore to organization: {meta['organization_name']}")
        self._report(0, 100, "Starting restore...")

        networks_dir = root / "networks"
        if not networks_dir.exists():
            self.errors.append("No networks folder in backup")
            return self.errors

        networks = sorted(networks_dir.iterdir())
        total = len(networks)

        for idx, net_dir in enumerate(networks):
            if not net_dir.is_dir():
                continue

            net_name = net_dir.name
            self._report(int((idx / total) * 100), 100, f"Restoring {net_name}...")
            self.log.info(f"[{idx+1}/{total}] Restoring network: {net_name}")

            try:
                self._restore_network(net_dir, org_id, opts)
            except Exception as e:
                self.log.log_exception(f"Failed to restore network {net_name}", e)
                self.errors.append(f"Network {net_name}: {str(e)}")
                if not self.continue_on_error:
                    break

        self._report(100, 100, "Restore complete")
        self._write_restore_log(root)
        self.log.info(f"Restore complete. Errors: {len(self.errors)}, Warnings: {len(self.warnings)}")
        return self.errors

    def _restore_network(self, net_dir, org_id, opts):
        """Restore a single network's configs"""
        net_meta_file = net_dir / "network_meta.json"
        if not net_meta_file.exists():
            self.warnings.append(f"No network_meta.json in {net_dir.name}")
            return

        net_meta = json.loads(net_meta_file.read_text())
        net_name = net_meta.get("name", net_dir.name)
        net_id = net_meta.get("id", "")
        product_types = net_meta.get("productTypes", [])

        if opts.get("target_networks") and net_name not in opts["target_networks"]:
            self.log.info(f"Skipping {net_name} (not in target list)")
            return

        if self._dry_run:
            self._preview_network(net_dir)
            return

        # ── MX Appliance restore ─────────────────────────────────
        if 'appliance' in product_types:
            self._restore_appliance(net_dir, net_id)

        # ── Switch restore ───────────────────────────────────────
        if 'switch' in product_types:
            self._restore_switch(net_dir, net_id)

        # ── Wireless restore ─────────────────────────────────────
        if 'wireless' in product_types:
            self._restore_wireless(net_dir, net_id)

    def _restore_appliance(self, net_dir, net_id):
        """Restore MX appliance configs"""
        appliance_dir = net_dir / "appliance"
        if not appliance_dir.exists():
            return

        self.log.info("  Restoring MX appliance configs...")

        # Firewall inbound rules
        f = appliance_dir / "firewall_inbound_rules.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_firewall_inbound_rules(net_id, data)

        # Firewall outbound rules
        f = appliance_dir / "firewall_outbound_rules.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_firewall_outbound_rules(net_id, data)

        # L3 rules
        f = appliance_dir / "firewall_l3_rules.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_firewall_l3_rules(net_id, data)

        # Traffic shaping
        f = appliance_dir / "firewall_traffic_shaping.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_traffic_shaping(net_id, data)

        # VPN site-to-site
        f = appliance_dir / "vpn_site_to_site.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_vpn(net_id, data)

        # Client VPN
        f = appliance_dir / "vpn_client_ipsec.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_vpn_one_ipsec(net_id, data)

        # Intrusion
        f = appliance_dir / "security_intrusion.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_security_intrusion(net_id, data)

        # Content filtering
        f = appliance_dir / "security_content_filtering.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_content_filtering(net_id, data)

        # Malware
        f = appliance_dir / "security_malware.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_malware(net_id, data)

        # DHCP
        f = appliance_dir / "dhcp_subnets.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_dhcp(net_id, data)

        # DNS
        f = appliance_dir / "dns_settings.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_dns(net_id, data)

        # VLANs
        f = appliance_dir / "vlans.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_vlans(net_id, data)

        # Warm spare
        f = appliance_dir / "warm_spare.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_warm_spare(net_id, data)

        # Radio settings
        f = appliance_dir / "radio_settings.json"
        if f.exists():
            data = self._load_json(f)
            if data and "error" not in data:
                self._put_appliance_radio_settings(net_id, data)

    def _restore_switch(self, net_dir, net_id):
        """Restore switch configs"""
        switch_dir = net_dir / "switch"
        if not switch_dir.exists():
            return

        self.log.info("  Restoring switch configs...")
        # Restore switch settings, ACLs, POE, QoS, etc.
        for filename in ["settings.json", "access_control_lists.json", "poe.json",
                         "qos_rules.json", "dscp_tagging.json", "port_schedules.json",
                         "storm_control.json", "mirror.json", "dhcp_server_policy.json"]:
            f = switch_dir / filename
            if f.exists():
                data = self._load_json(f)
                if data and "error" not in data:
                    self.log.debug(f"    Restoring switch config: {filename}")

    def _restore_wireless(self, net_dir, net_id):
        """Restore wireless configs"""
        wireless_dir = net_dir / "wireless"
        if not wireless_dir.exists():
            return

        self.log.info("  Restoring wireless configs...")
        # Restore SSIDs, RF profiles, settings, etc.
        for filename in ["ssids.json", "rf_profiles.json", "settings.json",
                         "alternate_mgmt_interface.json", "air_marshal.json"]:
            f = wireless_dir / filename
            if f.exists():
                data = self._load_json(f)
                if data and "error" not in data:
                    self.log.debug(f"    Restoring wireless config: {filename}")

    # ── PUT Methods (with error handling) ───────────────────────

    def _put_appliance_firewall_inbound_rules(self, net_id, data):
        try:
            rules = data.get("rules", []) if isinstance(data, dict) else []
            syslog = data.get("syslogDefaultRule", False) if isinstance(data, dict) else False
            self.client.dashboard.appliance.updateNetworkApplianceFirewallInboundRules(
                networkId=net_id, rules=rules, syslogDefaultRule=syslog
            )
            self.log.info(f"  [OK] Restored inbound firewall rules for {net_id}")
        except Exception as e:
            self._handle_put_error("firewall_inbound_rules", net_id, e)

    def _put_appliance_firewall_outbound_rules(self, net_id, data):
        try:
            rules = data.get("rules", []) if isinstance(data, dict) else []
            syslog = data.get("syslogDefaultRule", False) if isinstance(data, dict) else False
            self.client.dashboard.appliance.updateNetworkApplianceFirewallOutboundRules(
                networkId=net_id, rules=rules, syslogDefaultRule=syslog
            )
            self.log.info(f"  [OK] Restored outbound firewall rules for {net_id}")
        except Exception as e:
            self._handle_put_error("firewall_outbound_rules", net_id, e)

    def _put_appliance_firewall_l3_rules(self, net_id, data):
        try:
            rules = data.get("rules", []) if isinstance(data, dict) else []
            self.client.dashboard.appliance.updateNetworkApplianceFirewallL3FirewallRules(
                networkId=net_id, rules=rules
            )
            self.log.info(f"  [OK] Restored L3 firewall rules for {net_id}")
        except Exception as e:
            self._handle_put_error("firewall_l3_rules", net_id, e)

    def _put_appliance_traffic_shaping(self, net_id, data):
        try:
            if isinstance(data, dict):
                self.client.dashboard.appliance.updateNetworkApplianceTrafficShaping(
                    networkId=net_id, **data
                )
            self.log.info(f"  [OK] Restored traffic shaping for {net_id}")
        except Exception as e:
            self._handle_put_error("traffic_shaping", net_id, e)

    def _put_appliance_vpn(self, net_id, data):
        try:
            if isinstance(data, dict):
                self.client.dashboard.appliance.updateNetworkApplianceVpnSiteToSiteVpn(
                    networkId=net_id, **data
                )
            self.log.info(f"  [OK] Restored site-to-site VPN for {net_id}")
        except Exception as e:
            self._handle_put_error("vpn_site_to_site", net_id, e)

    def _put_appliance_vpn_one_ipsec(self, net_id, data):
        try:
            if isinstance(data, dict):
                self.client.dashboard.appliance.updateNetworkApplianceVpnOneIpsec(
                    networkId=net_id, **data
                )
            self.log.info(f"  [OK] Restored client VPN for {net_id}")
        except Exception as e:
            self._handle_put_error("vpn_client_ipsec", net_id, e)

    def _put_appliance_security_intrusion(self, net_id, data):
        try:
            if isinstance(data, dict):
                self.client.dashboard.appliance.updateNetworkApplianceSecurityIntrusion(
                    networkId=net_id, **data
                )
            self.log.info(f"  [OK] Restored IDS/IPS settings for {net_id}")
        except Exception as e:
            self._handle_put_error("security_intrusion", net_id, e)

    def _put_appliance_content_filtering(self, net_id, data):
        try:
            if isinstance(data, dict):
                self.client.dashboard.appliance.updateNetworkApplianceSecurityContentFiltering(
                    networkId=net_id, **data
                )
            self.log.info(f"  [OK] Restored content filtering for {net_id}")
        except Exception as e:
            self._handle_put_error("content_filtering", net_id, e)

    def _put_appliance_malware(self, net_id, data):
        try:
            if isinstance(data, dict):
                self.client.dashboard.appliance.updateNetworkApplianceSecurityMalware(
                    networkId=net_id, **data
                )
            self.log.info(f"  [OK] Restored malware protection for {net_id}")
        except Exception as e:
            self._handle_put_error("security_malware", net_id, e)

    def _put_appliance_dhcp(self, net_id, data):
        try:
            if isinstance(data, dict):
                self.client.dashboard.appliance.updateNetworkApplianceDhcpV4Subnets(
                    networkId=net_id, **data
                )
            self.log.info(f"  [OK] Restored DHCP settings for {net_id}")
        except Exception as e:
            self._handle_put_error("dhcp", net_id, e)

    def _put_appliance_dns(self, net_id, data):
        try:
            if isinstance(data, dict):
                self.client.dashboard.appliance.updateNetworkApplianceDnsSettings(
                    networkId=net_id, **data
                )
            self.log.info(f"  [OK] Restored DNS settings for {net_id}")
        except Exception as e:
            self._handle_put_error("dns", net_id, e)

    def _put_appliance_vlans(self, net_id, data):
        try:
            if isinstance(data, dict) and " vlans" in data:
                vlans = data.get(" vlans", [])
                for vlan in vlans:
                    self.client.dashboard.appliance.updateNetworkApplianceVlan(
                        networkId=net_id, vlanId=vlan.get("id"), **vlan
                    )
            self.log.info(f"  [OK] Restored VLANs for {net_id}")
        except Exception as e:
            self._handle_put_error("vlans", net_id, e)

    def _put_appliance_warm_spare(self, net_id, data):
        try:
            if isinstance(data, dict):
                self.client.dashboard.appliance.updateNetworkApplianceWarmSpare(
                    networkId=net_id, **data
                )
            self.log.info(f"  [OK] Restored warm spare for {net_id}")
        except Exception as e:
            self._handle_put_error("warm_spare", net_id, e)

    def _put_appliance_radio_settings(self, net_id, data):
        try:
            if isinstance(data, dict):
                self.client.dashboard.appliance.updateNetworkApplianceRadioSettings(
                    networkId=net_id, **data
                )
            self.log.info(f"  [OK] Restored radio settings for {net_id}")
        except Exception as e:
            self._handle_put_error("radio_settings", net_id, e)

    def _handle_put_error(self, config_type, net_id, exc):
        """Handle errors during PUT operations"""
        msg = f"Failed to restore {config_type} for network {net_id}: {exc}"
        self.log.log_exception(msg, exc)
        self.errors.append(msg)
        if not self.continue_on_error:
            raise exc

    def _load_json(self, path):
        """Load JSON file safely"""
        try:
            return json.loads(path.read_text())
        except Exception as e:
            self.log.error(f"Failed to load {path}: {e}")
            return {"error": str(e)}

    def _write_restore_log(self, backup_root):
        """Write restore operation log"""
        log_data = {
            "restore_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": time.time() - self._restore_start_time if self._restore_start_time else 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "total_errors": len(self.errors),
            "total_warnings": len(self.warnings)
        }
        log_file = backup_root / "restore_log.json"
        try:
            with open(log_file, "w") as f:
                json.dump(log_data, f, indent=2)
        except Exception:
            pass