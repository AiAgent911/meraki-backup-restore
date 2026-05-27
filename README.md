# Meraki Backup & Restore — RSITServices

A production-grade GUI application for full organization backup and restore of Cisco Meraki Dashboard configurations.

📦 **Download:** Windows `.exe` available from the [Releases](https://github.com/RSITServices/meraki-backup-restore/releases) page.

---

## Features

### Backup
- **Full Organization Backup** — All networks, devices, configurations
- **Comprehensive Coverage** — MX firewall/VPN/IDS/Content Filtering, MS switching, MR wireless, MV cameras, MG cellular, MT sensors, SM MDM, administrators, SAML roles, webhooks
- **Timestamped Directories** — `backup_YYYY-MM-DD_HH-MMSS/` with JSON configs
- **Progress Tracking** — Real-time progress bar and live log output
- **Error Resilience** — Continue on error, individual item failure isolation

### Restore
- **Full Organization Restore** — Apply backup configs back to Meraki
- **Selective Network Restore** — Choose specific networks
- **Dry-Run Preview** — See exactly what will change before applying
- **Validation** — Backup integrity checks on load
- **Detailed Logging** — Full restore operation log

### GUI
- **Professional Dark Theme** — RSITServices branded
- **Sidebar Navigation** — Dashboard, Backup, Restore, Logs, Settings
- **Live Scrolling Logs** — Color-coded by severity
- **Progress Indicators** — Status dots, progress bars
- **Log Export** — Save logs to file anytime

### Debug & Safety
- **Rotating Log Files** — 10MB max, 5 backups each
- **Full Traceback Logging** — Every exception with context
- **API Call Tracing** — All requests/responses in debug log
- **Non-destructive Preview** — Dry-run before any changes

---

## Getting Started

### 1. Configure API Key
1. Go to **Settings** tab
2. Enter your Meraki Dashboard API key
3. Click **Test Connection** to verify
4. Click **Save**

> Get your API key from: [dashboard.meraki.com](https://dashboard.meraki.com) → Admin → API Keys

### 2. Run a Backup
1. Go to **Backup** tab
2. Select destination folder (or use default)
3. Click **Start Backup**
4. Monitor progress in the log output
5. Backup saved to `backup_YYYY-MM-DD_HH-MMSS/` in your destination

### 3. Restore
1. Go to **Restore** tab
2. Browse to select a backup folder
3. Click **Load** to preview contents
4. Toggle **Dry-run** to preview changes
5. Click **Restore** to apply

---

## Backup Structure

```
backup_2026-05-27_14-30-00/
├── organization_meta.json          # Org info + timestamp
├── backup_summary.json             # Error/warning summary
├── organization/
│   ├── admins.json                 # Organization admins
│   ├── saml_roles.json            # SAML roles
│   └── config_templates.json       # Config templates
├── networks/
│   ├── My Network Name/
│   │   ├── network_meta.json       # Network metadata
│   │   ├── appliance/              # MX configs
│   │   ├── switch/                # MS configs
│   │   ├── wireless/              # MR configs
│   │   ├── camera/               # MV configs
│   │   ├── cellular_gateway/     # MG configs
│   │   ├── sensor/               # MT configs
│   │   ├── sm/                   # SM configs
│   │   ├── devices/              # Device list
│   │   ├── clients/              # Client summary
│   │   └── webhooks/             # Webhook configs
└── restore_log.json               # Restore operation log
```

---

## Build from Source

```bash
pip install meraki
python main.py
```

### Build Windows .exe

```bash
pip install pyinstaller meraki
pyinstaller meraki_backup.spec
# Output: dist/MerakiBackupRestore.exe
```

---

## Network Types Supported

| Product | Code | Configs |
|---------|------|--------|
| **MX** | Security Appliance | Firewall, VPN, IDS/IPS, Content Filter, Malware, DHCP, DNS, VLANs |
| **MS** | Switch | Stacks, POE, QoS, ACLs, Storm control, Port mirroring |
| **MR** | Wireless | SSIDs, BSSIDs, RF profiles, Air Marshal |
| **MV** | Camera | Cameras, Zones, Schedules, Quality, Sense |
| **MG** | Cellular Gateway | Settings, Connectivity |
| **MT** | Sensor | Sensors, Alerts, MQTT broker |
| **SM** | Systems Manager | Profiles, Devices |

---

## Log Files

| File | Description |
|------|-------------|
| `logs/meraki_backup.log` | Main application log |
| `logs/meraki_backup_debug.log` | Debug log (all API calls) |

---

## Brought to you by

**RSITServices** — Enterprise IT Solutions
*Reliable. Professional. Built for Real-World Use.*

---

## License

Internal use — RSITServices © 2026