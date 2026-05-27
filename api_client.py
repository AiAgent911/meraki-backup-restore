"""
Meraki Backup & Restore — RSITServices
API Client: Meraki Dashboard API wrapper with full logging
SDK: meraki v3.x
"""

import meraki
import time
from log_manager import log_manager


class MerakiAPIClient:
    """Meraki Dashboard API client with retry logic and comprehensive logging"""

    def __init__(self, api_key):
        self.api_key = api_key
        self.dashboard = meraki.DashboardAPI(
            api_key=api_key,
            print_console=False,
            log_path='./logs',
            suppress_logging=True,
            maximum_retries=3
        )
        self.log = log_manager

    # ─── Organizations ───────────────────────────────────────────

    def get_organizations(self):
        return self._call_api(lambda: self.dashboard.organizations.getOrganizations())

    def get_organization(self, org_id):
        return self._call_api(lambda: self.dashboard.organizations.getOrganization(org_id))

    def get_organization_networks(self, org_id, total_pages=-1):
        return self._call_api(
            lambda: self.dashboard.organizations.getOrganizationNetworks(org_id, total_pages=total_pages)
        )

    def get_organization_admins(self, org_id):
        return self._call_api(lambda: self.dashboard.organizations.getOrganizationAdmins(org_id))

    def get_organization_saml_roles(self, org_id):
        return self._call_api(lambda: self.dashboard.organizations.getOrganizationSamlRoles(org_id))

    def get_organization_sensor_alerts_overview(self, org_id):
        return self._call_api(lambda: self.dashboard.organizations.getOrganizationSensorAlertsOverview(org_id))

    # ─── Networks ─────────────────────────────────────────────────

    def get_network(self, network_id):
        return self._call_api(lambda: self.dashboard.networks.getNetwork(network_id))

    def get_network_devices(self, network_id):
        # v3: networks.getNetworkDevices (not dashboard.devices)
        return self._call_api(lambda: self.dashboard.networks.getNetworkDevices(network_id))

    def get_network_clients(self, network_id, total_pages=-1):
        # v3: networks.getNetworkClients (not dashboard.clients)
        return self._call_api(lambda: self.dashboard.networks.getNetworkClients(network_id, total_pages=total_pages))

    # ─── MX Appliance / Firewall ─────────────────────────────────

    def get_appliance_firewall_inbound_rules(self, network_id):
        # v3: getNetworkApplianceFirewallInboundFirewallRules
        return self._call_api(
            lambda: self.dashboard.appliance.getNetworkApplianceFirewallInboundFirewallRules(network_id)
        )

    # outbound rules — removed in v3 SDK, no equivalent at network level
    def get_appliance_firewall_outbound_rules(self, network_id):
        return None, "not_available"

    def get_appliance_firewall_l3_rules(self, network_id):
        # v3: getNetworkApplianceFirewallL3FirewallRules
        return self._call_api(
            lambda: self.dashboard.appliance.getNetworkApplianceFirewallL3FirewallRules(network_id)
        )

    # traffic shaping rules — removed in v3; use getNetworkApplianceTrafficShaping
    def get_appliance_firewall_traffic_shaping(self, network_id):
        return None, "not_available"

    # cellular VPN rules — removed in v3
    def get_appliance_firewall_cellular_vpn_rules(self, network_id):
        return None, "not_available"

    # ─── VPN ─────────────────────────────────────────────────────

    def get_appliance_vpn(self, network_id):
        return self._call_api(lambda: self.dashboard.appliance.getNetworkApplianceVpnSiteToSiteVpn(network_id))

    # client VPN (IPsec) — removed in v3
    def get_appliance_vpn_one_ipsec(self, network_id):
        return None, "not_available"

    # ─── Security ─────────────────────────────────────────────────

    def get_appliance_security_intrusion(self, network_id):
        return self._call_api(
            lambda: self.dashboard.appliance.getNetworkApplianceSecurityIntrusion(network_id)
        )

    def get_appliance_security_content_filtering(self, network_id):
        # v3: getNetworkApplianceContentFiltering
        return self._call_api(
            lambda: self.dashboard.appliance.getNetworkApplianceContentFiltering(network_id)
        )

    def get_appliance_security_malware(self, network_id):
        return self._call_api(
            lambda: self.dashboard.appliance.getNetworkApplianceSecurityMalware(network_id)
        )

    # ─── DHCP / DNS ───────────────────────────────────────────────

    # DHCP subnets — v3 only has device-level getDeviceApplianceDhcpSubnets, skip
    def get_appliance_dhcp(self, network_id):
        return None, "not_available"

    # DNS settings — removed in v3
    def get_appliance_dns(self, network_id):
        return None, "not_available"

    # ─── VLANs ────────────────────────────────────────────────────

    def get_appliance_vlans(self, network_id):
        return self._call_api(lambda: self.dashboard.appliance.getNetworkApplianceVlans(network_id))

    def get_appliance_vlan(self, network_id, vlan_id):
        return self._call_api(lambda: self.dashboard.appliance.getNetworkApplianceVlan(network_id, vlan_id))

    # ─── Traffic ─────────────────────────────────────────────────

    def get_appliance_traffic_shaping(self, network_id):
        return self._call_api(
            lambda: self.dashboard.appliance.getNetworkApplianceTrafficShaping(network_id)
        )

    # ─── Warm Spare ─────────────────────────────────────────────

    def get_appliance_warm_spare(self, network_id):
        return self._call_api(lambda: self.dashboard.appliance.getNetworkApplianceWarmSpare(network_id))

    # ─── Switch ───────────────────────────────────────────────────

    def get_switch_stacks(self, network_id):
        return self._call_api(lambda: self.dashboard.switch.getNetworkSwitchStacks(network_id))

    def get_switch_stack_routing(self, network_id, stack_id):
        return self._call_api(
            lambda: self.dashboard.switch.getNetworkSwitchStackRouting(network_id, stack_id)
        )

    def get_switch_storm_control(self, network_id):
        return self._call_api(lambda: self.dashboard.switch.getNetworkSwitchStormControl(network_id))

    # Port mirroring — removed in v3
    def get_switch_mirror(self, network_id):
        return None, "not_available"

    # POE settings — removed in v3
    def get_switch_poe(self, network_id):
        return None, "not_available"

    def get_switch_qos_rules(self, network_id):
        return self._call_api(lambda: self.dashboard.switch.getNetworkSwitchQosRules(network_id))

    # DSCP tagging — removed in v3 (replaced by DSCP-to-CoS mappings)
    def get_switch_dscp_tagging(self, network_id):
        return None, "not_available"

    def get_switch_access_control_lists(self, network_id):
        return self._call_api(lambda: self.dashboard.switch.getNetworkSwitchAccessControlLists(network_id))

    def get_switch_port_schedules(self, network_id):
        return self._call_api(lambda: self.dashboard.switch.getNetworkSwitchPortSchedules(network_id))

    def get_switch_settings(self, network_id):
        return self._call_api(lambda: self.dashboard.switch.getNetworkSwitchSettings(network_id))

    def get_switch_dhcp_server_policy(self, network_id):
        return self._call_api(lambda: self.dashboard.switch.getNetworkSwitchDhcpServerPolicy(network_id))

    # ─── Wireless ────────────────────────────────────────────────

    def get_wireless_ssids(self, network_id):
        return self._call_api(lambda: self.dashboard.wireless.getNetworkWirelessSsids(network_id))

    # BSSIDs — removed in v3
    def get_wireless_bssid(self, network_id):
        return None, "not_available"

    # Wireless clients — removed in v3; use networks.getNetworkClients instead
    def get_wireless_clients(self, network_id):
        return None, "not_available"

    def get_wireless_failed_connections(self, network_id):
        return self._call_api(
            lambda: self.dashboard.wireless.getNetworkWirelessFailedConnections(network_id)
        )

    def get_wireless_rf_profiles(self, network_id):
        return self._call_api(lambda: self.dashboard.wireless.getNetworkWirelessRfProfiles(network_id))

    # Survey/datasets — removed in v3
    def get_wireless_survey_destination(self, network_id):
        return None, "not_available"

    # Floor plans — v3 has no floor_plans object; skip
    def get_wireless_ssid_floor_plan(self, network_id):
        return None, "not_available"

    def get_wireless_settings(self, network_id):
        return self._call_api(lambda: self.dashboard.wireless.getNetworkWirelessSettings(network_id))

    def get_wireless_alternate_management_interface(self, network_id):
        return self._call_api(
            lambda: self.dashboard.wireless.getNetworkWirelessAlternateManagementInterface(network_id)
        )

    # ─── Camera ──────────────────────────────────────────────────

    def get_camera_sensors(self, network_id):
        return self._call_api(lambda: self.dashboard.camera.getNetworkCameras(network_id))

    def get_camera_quality(self, network_id):
        return self._call_api(
            lambda: self.dashboard.camera.getNetworkCameraQualityRetentionProfiles(network_id)
        )

    # Camera sense — removed in v3
    def get_camera_sense(self, network_id):
        return None, "not_available"

    def get_camera_zones(self, network_id):
        return self._call_api(lambda: self.dashboard.camera.getNetworkCameraZones(network_id))

    def get_camera_schedules(self, network_id):
        return self._call_api(lambda: self.dashboard.camera.getNetworkCameraSchedules(network_id))

    # ─── Cellular Gateway ─────────────────────────────────────────

    # Cellular gateway settings — removed in v3
    def get_cellular_gateway_settings(self, network_id):
        return None, "not_available"

    # Connectivity tracking — removed in v3
    def get_cellular_gateway_connectivity(self, network_id):
        return None, "not_available"

    # ─── Sensors ─────────────────────────────────────────────────

    # Sensor sensors — removed in v3; use getNetworkSensorAlertsProfiles
    def get_sensor_sensors(self, network_id):
        return None, "not_available"

    # Sensor alerts — v3 uses getNetworkSensorAlertsProfiles (no direct equivalent)
    def get_sensor_alerts(self, network_id):
        return self._call_api(lambda: self.dashboard.sensor.getNetworkSensorAlertsProfiles(network_id))

    # MQTT broker — v3 uses getNetworkSensorMqttBrokers (plural)
    def get_sensor_mqtt_broker(self, network_id):
        return self._call_api(lambda: self.dashboard.sensor.getNetworkSensorMqttBrokers(network_id))

    # ─── Systems Manager ─────────────────────────────────────────

    def get_sm_profiles(self, network_id):
        return self._call_api(lambda: self.dashboard.sm.getNetworkSmProfiles(network_id))

    def get_sm_device_certificates(self, network_id):
        return self._call_api(
            lambda: self.dashboard.sm.getNetworkSmDevices(network_id)
        )

    # ─── Administrators ──────────────────────────────────────────

    def get_admins(self, network_id):
        return self._call_api(lambda: self.dashboard.administered_licensing_subscription_claims(
            network_id=network_id
        ))

    def get_organization_config_templates(self, org_id):
        return self._call_api(
            lambda: self.dashboard.organizations.getOrganizationConfigTemplates(org_id)
        )

    # ─── Webhooks / Alerts ───────────────────────────────────────

    # v3: webhooks are getNetworkWebhooksHttpServers (no plain getNetworkWebhooks)
    def get_webhooks(self, network_id):
        return self._call_api(
            lambda: self.dashboard.networks.getNetworkWebhooksHttpServers(network_id)
        )

    def get_webhook_payload_templates(self, network_id):
        return self._call_api(
            lambda: self.dashboard.networks.getNetworkWebhooksPayloadTemplates(network_id)
        )

    # ─── VLAN Profiles ───────────────────────────────────────────

    def get_appliance_vlan_profiles(self, network_id):
        # v3: networks.getNetworkVlanProfiles
        return self._call_api(
            lambda: self.dashboard.networks.getNetworkVlanProfiles(network_id)
        )

    # ─── Air Marshal ─────────────────────────────────────────────

    def get_wireless_air_marshal(self, network_id):
        return self._call_api(lambda: self.dashboard.wireless.getNetworkWirelessAirMarshal(network_id))

    # ─── Radio Settings ──────────────────────────────────────────

    # Radio settings — removed in v3
    def get_appliance_radio_settings(self, network_id):
        return None, "not_available"

    # ─── Content Filtering ────────────────────────────────────────

    def get_appliance_content_filtering(self, network_id):
        return self._call_api(
            lambda: self.dashboard.appliance.getNetworkApplianceContentFiltering(network_id)
        )

    # ─── Internal API Helpers ────────────────────────────────────

    def _call_api(self, func, retries=3, delay=2):
        """Execute an API call with retry logic and logging"""
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                self.log.debug(f"API_CALL | Attempt {attempt}/{retries} | {func.__name__}", logger='debug')
                result = func()
                self.log.debug(f"API_SUCCESS | {func.__name__}", logger='debug')
                return result, None
            except meraki.APIError as e:
                last_error = f"Meraki API Error {e.status}: {e.message}"
                self.log.error(f"API Error {e.status}: {e.message}")
                if attempt < retries:
                    time.sleep(delay * attempt)
            except Exception as e:
                last_error = str(e)
                self.log.log_exception(f"API call failed (attempt {attempt}/{retries})", e)
                if attempt < retries:
                    time.sleep(delay * attempt)

        self.log.error(f"All {retries} retries exhausted for {func.__name__}: {last_error}")
        return None, last_error

    def test_connection(self):
        """Test API key validity"""
        orgs, err = self.get_organizations()
        if err:
            return False, err
        return True, None
