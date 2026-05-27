"""
Meraki Backup & Restore — RSITServices
Main Tkinter GUI Application
"""

import os
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import traceback
from datetime import datetime

# Import our modules
from config import ConfigManager
from log_manager import log_manager
from backup_engine import BackupEngine
from restore_engine import RestoreEngine

APP_VERSION = "1.0.2"

# ─── Theme Colors ────────────────────────────────────────────────
BG_DARK       = "#0d1117"
BG_SECONDARY  = "#161b22"
BG_TERTIARY   = "#21262d"
BORDER        = "#30363d"
TEXT_PRIMARY  = "#e6edf3"
TEXT_SECONDARY= "#8b949e"
ACCENT        = "#58a6ff"
ACCENT_HOVER  = "#79c0ff"
HIGHLIGHT     = "#f78166"
SUCCESS       = "#3fb950"
WARNING       = "#d29922"
ERROR         = "#f85149"
SIDEBAR_BG    = "#010409"
CARD_BG       = "#1c2128"


# ─── Scrollable Log Widget ───────────────────────────────────────

class ScrollableText(tk.Frame):
    def __init__(self, parent, height=20, **kwargs):
        super().__init__(parent, bg=BG_DARK)
        self._build_widgets(height, **kwargs)

    def _build_widgets(self, height, **kwargs):
        self.text = tk.Text(
            self, wrap=tk.WORD, height=height,
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Consolas", 10), relief=tk.FLAT,
            insertbackground=TEXT_PRIMARY,
            padx=10, pady=10,
            state=tk.DISABLED,
            **kwargs
        )
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.text.yview)
        self.text.config(yscrollcommand=self.scrollbar.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def append(self, text, color=None):
        self.text.config(state=tk.NORMAL)
        if color:
            self.text.tag_add(color, "end-1c", "end")
            self.text.tag_config(color, foreground=color)
        self.text.insert(tk.END, text + "\n")
        self.text.see(tk.END)
        self.text.config(state=tk.DISABLED)

    def append_info(self, text):
        self.append(f"[INFO]  {text}", TEXT_PRIMARY)

    def append_success(self, text):
        self.append(f"[OK]    {text}", SUCCESS)

    def append_warning(self, text):
        self.append(f"[WARN]  {text}", WARNING)

    def append_error(self, text):
        self.append(f"[ERROR] {text}", ERROR)

    def append_debug(self, text):
        self.append(f"[DEBUG] {text}", TEXT_SECONDARY)

    def clear(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.config(state=tk.DISABLED)


# ─── Main Application ─────────────────────────────────────────────

class MerakiBackupApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RSITServices — Meraki Backup & Restore")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(1100, 720)

        self.config = ConfigManager()
        self.log = log_manager

        self._current_tab = None
        self._backup_in_progress = False
        self._restore_in_progress = False
        self._dashboard_populated = False

        # Org state
        self._org_vars = {}  # org_id -> {name, networks, last_backup, last_error}

        self._build_ui()
        self._refresh_dashboard()

    # ─── UI Construction ───────────────────────────────────────

    def _build_ui(self):
        self._build_header(self.root)
        body = tk.Frame(self.root, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(1, weight=1)

        self._build_sidebar(body)
        self.content_frame = tk.Frame(body, bg=BG_DARK)
        self.content_frame.grid(row=0, column=1, sticky="nsew")

        self.statusbar = tk.Label(
            self.root, text="Ready", bg=BG_SECONDARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9), anchor=tk.W, padx=10, pady=4
        )
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM)

        self._show_dashboard()

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=SIDEBAR_BG, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="RSITServices",
            bg=SIDEBAR_BG, fg=ACCENT,
            font=("Segoe UI", 16, "bold")
        ).pack(side=tk.LEFT, padx=20, pady=12)

        tk.Label(
            header, text="Meraki Backup & Restore",
            bg=SIDEBAR_BG, fg=TEXT_PRIMARY,
            font=("Segoe UI", 13)
        ).pack(side=tk.LEFT, pady=12)

        self.header_status_dot = tk.Canvas(header, width=12, height=12, bg=SIDEBAR_BG, highlightthickness=0)
        self.header_status_dot.create_oval(2, 2, 12, 12, fill=ERROR, outline="")
        self.header_status_dot.pack(side=tk.RIGHT, padx=15, pady=12)

        self.header_status_label = tk.Label(
            header, text="No org selected", bg=SIDEBAR_BG, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9)
        )
        self.header_status_label.pack(side=tk.RIGHT, padx=5, pady=12)

    def _build_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=SIDEBAR_BG, width=210)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # ── Org Selector ──────────────────────────────────────
        org_header = tk.Frame(sidebar, bg=BG_TERTIARY, padx=10, pady=8)
        org_header.pack(fill=tk.X, pady=(0, 2))

        tk.Label(
            org_header, text="ORGANIZATION", bg=BG_TERTIARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 8, "bold")
        ).pack(anchor=tk.W)

        self.org_selector = ttk.Combobox(
            sidebar, state="readonly", font=("Segoe UI", 10),
            background=BG_TERTIARY, foreground=TEXT_PRIMARY
        )
        self.org_selector.pack(fill=tk.X, padx=10, pady=(4, 2), ipady=4)
        self.org_selector.bind("<<ComboboxSelected>>", self._on_org_changed)

        self.add_org_btn = tk.Button(
            sidebar, text="+ Add Organization", bg=SUCCESS, fg="#fff",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=0, pady=4,
            cursor="hand1", command=self._show_add_org_dialog
        )
        self.add_org_btn.pack(fill=tk.X, padx=10, pady=(2, 8))

        # ── Separator ──────────────────────────────────────────
        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill=tk.X, padx=10, pady=(0, 5))

        # ── Nav label ─────────────────────────────────────────
        tk.Label(
            sidebar, text="NAVIGATION", bg=SIDEBAR_BG, fg=TEXT_SECONDARY,
            font=("Segoe UI", 8, "bold"), pady=10, padx=15, anchor=tk.W
        ).pack(fill=tk.X)

        nav_items = [
            ("📊", "Dashboard", self._show_dashboard),
            ("💾", "Backup",   self._show_backup),
            ("♻️", "Restore",  self._show_restore),
            ("📋", "Logs",    self._show_logs),
            ("⚙️", "Settings",self._show_settings),
        ]

        self.nav_buttons = {}
        for icon, label, cmd in nav_items:
            btn = tk.Button(
                sidebar, text=f"  {icon}  {label}", bg=SIDEBAR_BG, fg=TEXT_PRIMARY,
                font=("Segoe UI", 11), anchor=tk.W, relief=tk.FLAT,
                padx=15, pady=10, cursor="hand1", command=cmd
            )
            btn.pack(fill=tk.X, padx=0, pady=0)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=BG_TERTIARY))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=SIDEBAR_BG))
            self.nav_buttons[label] = btn

        # ── Version at bottom ───────────────────────────────────
        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill=tk.X, padx=10, pady=(0, 0))
        tk.Label(
            sidebar, text=f"v{APP_VERSION} — RSITServices",
            bg=SIDEBAR_BG, fg=TEXT_SECONDARY,
            font=("Segoe UI", 8), pady=10
        ).pack(side=tk.BOTTOM, fill=tk.X)

    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _set_status(self, text):
        self.statusbar.config(text=text)

    def _set_connected(self, connected, org_name=None):
        color = SUCCESS if connected else ERROR
        self.header_status_dot.itemconfig(1, fill=color)
        if connected:
            self.header_status_label.config(text=f"Connected: {org_name or 'OK'}")
        else:
            self.header_status_label.config(text="No org selected")

    def _highlight_nav(self, active):
        for label, btn in self.nav_buttons.items():
            if label == active:
                btn.config(bg=BG_TERTIARY, fg=ACCENT)
            else:
                btn.config(bg=SIDEBAR_BG, fg=TEXT_PRIMARY)

    def _on_org_changed(self, event=None):
        selection = self.org_selector.current()
        org_ids = list(self._org_vars.keys())
        if 0 <= selection < len(org_ids):
            org_id = org_ids[selection]
            self.config.set_active_org(org_id)
            self._refresh_dashboard()

    def _populate_org_selector(self):
        """Repopulate sidebar org dropdown from config."""
        orgs = self.config.get("organizations", {})
        if not orgs:
            self.org_selector.config(values=["No organizations configured"])
            self.org_selector.current(0)
            self.org_selector.config(state="disabled")
            self._set_connected(False)
            return

        labels = []
        active_idx = 0
        active_org_id = self.config.get("active_org_id")
        for idx, (org_id, org) in enumerate(orgs.items()):
            label = org.get("name", org_id)
            labels.append(label)
            if org_id == active_org_id:
                active_idx = idx

        self.org_selector.config(state="readonly", values=labels)
        self.org_selector.current(active_idx)

        if active_org_id and active_org_id in orgs:
            self._set_connected(True, orgs[active_org_id].get("name", ""))
        else:
            self._set_connected(False)

    # ─── Org Management Dialogs ─────────────────────────────────

    def _show_add_org_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Organization")
        dialog.configure(bg=BG_DARK)
        dialog.geometry("520x380")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Center
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 260
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 190
        dialog.geometry(f"+{x}+{y}")

        container = tk.Frame(dialog, bg=BG_DARK, padx=25, pady=20)
        container.pack(fill=tk.BOTH, expand=True)
        container.grid_columnconfigure(1, weight=1)

        tk.Label(
            container, text="Add New Organization", bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 16, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 20))

        fields = [
            ("Organization Name:", "name_var", ""),
            ("API Key:",         "api_key_var", ""),
            ("Backup Destination:", "dest_var", ""),
        ]

        row = 1
        self._add_org_entries = {}
        for label_text, var_name, default in fields:
            tk.Label(
                container, text=label_text, bg=BG_DARK, fg=TEXT_SECONDARY,
                font=("Segoe UI", 10)
            ).grid(row=row, column=0, sticky=tk.W, pady=8, padx=(0, 10))
            var = tk.StringVar(value=default)
            entry = tk.Entry(
                container, textvariable=var, bg=BG_TERTIARY, fg=TEXT_PRIMARY,
                font=("Consolas", 10), insertbackground=TEXT_PRIMARY, relief=tk.FLAT
            )
            entry.grid(row=row, column=1, sticky="ew", pady=8)
            self._add_org_entries[var_name] = var
            row += 1

        # Test + Save buttons
        btn_row = tk.Frame(container, bg=BG_DARK)
        btn_row.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(15, 0))
        btn_row.grid_columnconfigure(0, weight=1)

        def test():
            key = self._add_org_entries["api_key_var"].get().strip()
            if not key:
                messagebox.showwarning("Missing", "Enter an API key to test.", parent=dialog)
                return
            try:
                import meraki
                dash = meraki.DashboardAPI(key, print_console=False, suppress_logging=True)
                orgs = dash.organizations.getOrganizations()
                if orgs:
                    names = ", ".join(o.get("name","?") for o in orgs[:5])
                    messagebox.showinfo("Connected", f"✓ API key valid.\nFound organizations:\n{names}", parent=dialog)
                else:
                    messagebox.showwarning("No Orgs", "API key valid but no organizations found.", parent=dialog)
            except Exception as e:
                messagebox.showerror("Error", f"Connection failed:\n{e}", parent=dialog)

        def save():
            name = self._add_org_entries["name_var"].get().strip()
            api_key = self._add_org_entries["api_key_var"].get().strip()
            dest = self._add_org_entries["dest_var"].get().strip()
            if not name or not api_key:
                messagebox.showwarning("Missing", "Name and API key are required.", parent=dialog)
                return
            # Use API key to get real org info
            try:
                import meraki
                dash = meraki.DashboardAPI(api_key, print_console=False, suppress_logging=True)
                orgs = dash.organizations.getOrganizations()
                if not orgs:
                    messagebox.showwarning("No Orgs", "No organizations found for this API key.", parent=dialog)
                    return
                # Add first org (user can rename later)
                org = orgs[0]
                org_id = str(org["id"])
                self.config.add_organization(org_id, name, api_key, dest)
                # Update org name from API if not manually set
                if name == org.get("name", name):
                    pass  # used provided name
                messagebox.showinfo("Added", f"Organization '{name}' added successfully.", parent=dialog)
                dialog.destroy()
                self._populate_org_selector()
                self._refresh_dashboard()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to verify API key:\n{e}", parent=dialog)

        tk.Button(
            btn_row, text="Test Connection", bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 9), relief=tk.FLAT, padx=15, pady=8, cursor="hand1", command=test
        ).pack(side=tk.LEFT)
        tk.Button(
            btn_row, text="Cancel", bg=BG_TERTIARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9), relief=tk.FLAT, padx=15, pady=8, cursor="hand1", command=dialog.destroy
        ).pack(side=tk.LEFT, padx=(5, 0))
        tk.Button(
            btn_row, text="Save", bg=SUCCESS, fg="#fff",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=20, pady=8, cursor="hand1", command=save
        ).pack(side=tk.RIGHT)

    def _show_edit_org_dialog(self, org_id):
        orgs = self.config.get("organizations", {})
        org = orgs.get(org_id, {})
        if not org:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit: {org.get('name', org_id)}")
        dialog.configure(bg=BG_DARK)
        dialog.geometry("520x340")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 260
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 170
        dialog.geometry(f"+{x}+{y}")

        container = tk.Frame(dialog, bg=BG_DARK, padx=25, pady=20)
        container.pack(fill=tk.BOTH, expand=True)
        container.grid_columnconfigure(1, weight=1)

        tk.Label(
            container, text=f"Edit Organization", bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 16, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 20))

        fields = [
            ("Organization Name:", "name_var", org.get("name", "")),
            ("API Key:",          "api_key_var", org.get("api_key", "")),
            ("Backup Destination:","dest_var", org.get("backup_destination", "")),
        ]

        row = 1
        edit_entries = {}
        for label_text, var_name, default in fields:
            tk.Label(
                container, text=label_text, bg=BG_DARK, fg=TEXT_SECONDARY,
                font=("Segoe UI", 10)
            ).grid(row=row, column=0, sticky=tk.W, pady=8, padx=(0, 10))
            var = tk.StringVar(value=default)
            entry = tk.Entry(
                container, textvariable=var, bg=BG_TERTIARY, fg=TEXT_PRIMARY,
                font=("Consolas", 10), insertbackground=TEXT_PRIMARY, relief=tk.FLAT
            )
            entry.grid(row=row, column=1, sticky="ew", pady=8)
            edit_entries[var_name] = var
            row += 1

        def save():
            name = edit_entries["name_var"].get().strip()
            api_key = edit_entries["api_key_var"].get().strip()
            dest = edit_entries["dest_var"].get().strip()
            if not name or not api_key:
                messagebox.showwarning("Missing", "Name and API key are required.", parent=dialog)
                return
            self.config.update_organization(org_id, name=name, api_key=api_key, backup_destination=dest)
            messagebox.showinfo("Saved", "Organization updated.", parent=dialog)
            dialog.destroy()
            self._populate_org_selector()
            self._refresh_dashboard()

        btn_row = tk.Frame(container, bg=BG_DARK)
        btn_row.grid(row=row, column=0, columnspan=2, sticky=tk.E, pady=(15, 0))

        tk.Button(
            btn_row, text="Delete Org", bg=ERROR, fg="#fff",
            font=("Segoe UI", 9), relief=tk.FLAT, padx=15, pady=8, cursor="hand1",
            command=lambda: self._confirm_delete_org(org_id, dialog)
        ).pack(side=tk.LEFT)
        tk.Button(
            btn_row, text="Cancel", bg=BG_TERTIARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9), relief=tk.FLAT, padx=15, pady=8, cursor="hand1", command=dialog.destroy
        ).pack(side=tk.LEFT, padx=(5, 0))
        tk.Button(
            btn_row, text="Save", bg=SUCCESS, fg="#fff",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=20, pady=8, cursor="hand1", command=save
        ).pack(side=tk.RIGHT)

    def _confirm_delete_org(self, org_id, parent_dialog):
        org = self.config.get("organizations", {}).get(org_id, {})
        name = org.get("name", org_id)
        if messagebox.askyesno("Delete Organization", f"Remove '{name}' from the app?\n\nThis will not delete any backup files.", parent=parent_dialog):
            self.config.remove_organization(org_id)
            parent_dialog.destroy()
            self._populate_org_selector()
            self._refresh_dashboard()

    # ─── Dashboard ───────────────────────────────────────────────

    def _show_dashboard(self):
        self._clear_content()
        self._current_tab = "dashboard"
        self._highlight_nav("Dashboard")
        self._refresh_dashboard()

    def _refresh_dashboard(self):
        """Build or refresh dashboard with current org data."""
        if self._current_tab != "dashboard":
            return

        org_id, org = self.config.get_active_org()

        container = tk.Frame(self.content_frame, bg=BG_DARK)
        container.pack(fill=tk.BOTH, expand=True, padx=28, pady=22)
        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)
        container.grid_rowconfigure(3, weight=1)

        # Title
        title = org.get("name", "Dashboard") if org else "Dashboard"
        tk.Label(
            container, text=title, bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 22, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 18))

        # ── Org Status Card ──────────────────────────────────
        status_card = self._make_dash_card(container, row=1, col=0, title="Connection Status", colspan=2)
        self._populate_status_card(status_card, org_id, org)

        # ── Stat Cards ────────────────────────────────────────
        self.networks_card = self._make_dash_card(container, row=2, col=0, title="Networks", colspan=1)
        self.last_backup_card = self._make_dash_card(container, row=2, col=1, title="Last Backup", colspan=1)
        self._populate_stat_cards(org_id, org)

        # ── Quick Actions ─────────────────────────────────────
        actions_card = self._make_dash_card(container, row=3, col=0, title="Quick Actions", colspan=2)
        self._populate_actions_card(actions_card, org_id, org)

        # ── Backup History ────────────────────────────────────
        history_card = self._make_dash_card(container, row=4, col=0, title="Backup History", colspan=2)
        self._populate_history_card(history_card, org_id, org)

        self._dashboard_populated = True

    def _make_dash_card(self, parent, row, col, title, colspan=1):
        card = tk.Frame(parent, bg=CARD_BG, relief=tk.FLAT, bd=1)
        card.config(highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=row, column=col, columnspan=colspan, sticky="nsew", padx=6, pady=6)
        card.grid_columnconfigure(0, weight=1)

        hdr = tk.Frame(card, bg=BG_TERTIARY)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr, text=title, bg=BG_TERTIARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9, "bold"), padx=12, pady=7
        ).pack(side=tk.LEFT)

        body = tk.Frame(card, bg=CARD_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
        body.grid_columnconfigure(0, weight=1)
        card._body = body
        return card

    def _populate_status_card(self, card, org_id, org):
        body = card._body
        for w in body.winfo_children():
            w.destroy()

        if not org_id or not org:
            tk.Label(
                body, text="⚠  No organization selected.\n\nAdd an organization from the sidebar or Settings.",
                bg=CARD_BG, fg=WARNING, font=("Segoe UI", 10), justify=tk.LEFT
            ).pack(anchor=tk.W)
            self._set_connected(False)
            return

        api_key = org.get("api_key", "")
        masked = api_key[:4] + "****" + api_key[-4:] if len(api_key) >= 8 else "****"
        dest = org.get("backup_destination", "Not set")

        rows = [
            ("Organization", org.get("name", org_id)),
            ("Org ID",        org_id),
            ("API Key",      masked),
            ("Backup Dest.", dest),
        ]
        for label, value in rows:
            row = tk.Frame(body, bg=CARD_BG)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label + ":", bg=CARD_BG, fg=TEXT_SECONDARY,
                     font=("Segoe UI", 9), width=14, anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row, text=value, bg=CARD_BG, fg=TEXT_PRIMARY,
                     font=("Consolas", 9)).pack(side=tk.LEFT)

        # Test connection button
        tk.Button(
            body, text="Test Connection", bg=ACCENT, fg="#fff",
            font=("Segoe UI", 9), relief=tk.FLAT, padx=12, pady=5,
            cursor="hand1", command=lambda: self._test_org_connection(org_id)
        ).pack(anchor=tk.W, pady=(8, 0))

    def _populate_stat_cards(self, org_id, org):
        # Networks card
        for w in self.networks_card._body.winfo_children():
            w.destroy()
        if org_id and org:
            try:
                import meraki
                dash = meraki.DashboardAPI(org.get("api_key",""), print_console=False, suppress_logging=True)
                networks = dash.networks.getOrganizationNetworks(org_id)
                count = len(networks)
            except Exception:
                count = "—"
        else:
            count = "—"
        tk.Label(
            self.networks_card._body, text=str(count), bg=CARD_BG, fg=TEXT_PRIMARY,
            font=("Segoe UI", 28, "bold"), anchor=tk.W
        ).pack(anchor=tk.W)
        tk.Label(
            self.networks_card._body, text="networks discovered", bg=CARD_BG, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9)
        ).pack(anchor=tk.W)

        # Last backup card
        for w in self.last_backup_card._body.winfo_children():
            w.destroy()
        if org_id and org:
            last = self._org_vars.get(org_id, {}).get("last_backup", None)
            if last:
                dt = datetime.strptime(last, "%Y-%m-%d_%H-%M%S")
                ts = dt.strftime("%b %d %Y, %I:%M %p")
            else:
                ts = "Never"
        else:
            ts = "—"
        tk.Label(
            self.last_backup_card._body, text=ts, bg=CARD_BG, fg=TEXT_PRIMARY,
            font=("Segoe UI", 18, "bold"), anchor=tk.W
        ).pack(anchor=tk.W)
        tk.Label(
            self.last_backup_card._body, text="last backup completed", bg=CARD_BG, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9)
        ).pack(anchor=tk.W)

    def _populate_actions_card(self, card, org_id, org):
        body = card._body
        for w in body.winfo_children():
            w.destroy()

        if not org_id or not org:
            tk.Label(
                body, text="Add an organization to enable backups.",
                bg=CARD_BG, fg=TEXT_SECONDARY, font=("Segoe UI", 10)
            ).pack(anchor=tk.W)
            return

        btn_frame = tk.Frame(body, bg=CARD_BG)
        btn_frame.pack(anchor=tk.W)

        def action_btn(text, bg, cmd):
            b = tk.Button(
                btn_frame, text=text, bg=bg, fg="#fff",
                font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=18, pady=8,
                cursor="hand1", command=cmd
            )
            b.pack(side=tk.LEFT, padx=(0, 10))
            return b

        action_btn("▶  Run Backup Now", SUCCESS, self._show_backup)
        action_btn("♻  Restore", HIGHLIGHT, self._show_restore)
        action_btn("⚙  Settings", BG_TERTIARY, self._show_settings)

    def _populate_history_card(self, card, org_id, org):
        body = card._body
        for w in body.winfo_children():
            w.destroy()

        if not org_id or not org:
            tk.Label(body, text="No organization selected.", bg=CARD_BG,
                     fg=TEXT_SECONDARY, font=("Segoe UI", 10)).pack(anchor=tk.W)
            return

        backup_dest = org.get("backup_destination", "")
        if not backup_dest or not os.path.exists(backup_dest):
            tk.Label(body, text="No backups found — destination not set or not accessible.",
                     bg=CARD_BG, fg=TEXT_SECONDARY, font=("Segoe UI", 10)).pack(anchor=tk.W)
            return

        # Scan for backup folders for this org
        org_name_safe = org.get("name", org_id).replace("/", "_").replace("\\", "_")
        matches = []
        try:
            for entry in os.scandir(backup_dest):
                if entry.is_dir() and entry.name.startswith("backup_"):
                    # Check if it's a valid backup (has org info)
                    info_file = Path(entry.path) / "organization_info.json"
                    if info_file.exists():
                        try:
                            info = json.loads(info_file.read_text())
                            matches.append((entry.name, info.get("organization_name", "?"), entry.path))
                        except Exception:
                            matches.append((entry.name, "Unknown", entry.path))
        except Exception:
            pass

        if not matches:
            tk.Label(body, text="No backup history found.", bg=CARD_BG,
                     fg=TEXT_SECONDARY, font=("Segoe UI", 10)).pack(anchor=tk.W)
            return

        # Sort by name (newest first)
        matches.sort(reverse=True)
        for fname, oname, fpath in matches[:10]:
            ts = fname.replace("backup_", "").replace("_", " ")
            row = tk.Frame(body, bg=CARD_BG)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=f"📁 {ts}", bg=CARD_BG, fg=TEXT_PRIMARY,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)
            tk.Label(row, text=oname[:30], bg=CARD_BG, fg=TEXT_SECONDARY,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(10, 0))

    def _test_org_connection(self, org_id=None):
        if org_id is None:
            org_id, org = self.config.get_active_org()
        else:
            org = self.config.get("organizations", {}).get(org_id, {})

        if not org:
            messagebox.showerror("Error", "No organization selected.")
            return

        api_key = org.get("api_key", "")
        if not api_key:
            messagebox.showerror("Error", "No API key configured for this organization.")
            return

        try:
            import meraki
            dash = meraki.DashboardAPI(api_key, print_console=False, suppress_logging=True)
            orgs = dash.organizations.getOrganizations()
            if orgs:
                self._set_connected(True, org.get("name", ""))
                messagebox.showinfo("Connected", f"✓ Successfully connected to:\n{org.get('name','Unknown')}")
            else:
                self._set_connected(False)
                messagebox.showwarning("No Orgs", "API key valid but no organizations found.")
        except meraki.APIError as e:
            self._set_connected(False)
            messagebox.showerror("API Error", f"Code {e.status}: {e.message}")
        except Exception as e:
            self._set_connected(False)
            messagebox.showerror("Error", str(e))

    # ─── Backup Tab ─────────────────────────────────────────────

    def _show_backup(self):
        self._clear_content()
        self._current_tab = "backup"
        self._highlight_nav("Backup")

        container = tk.Frame(self.content_frame, bg=BG_DARK)
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        tk.Label(
            container, text="Backup", bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 20, "bold")
        ).pack(anchor=tk.W, pady=15)

        opts = tk.LabelFrame(
            container, text="  Backup Options  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW, padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        opts.pack(fill=tk.X, pady=15)
        opts.grid_columnconfigure(1, weight=1)

        # Destination
        tk.Label(opts, text="Destination:", bg=BG_SECONDARY, fg=TEXT_SECONDARY,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.backup_dest_var = tk.StringVar(value=self.config.get_active_destination() or "")
        tk.Entry(
            opts, textvariable=self.backup_dest_var, bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Consolas", 10), insertbackground=TEXT_PRIMARY, relief=tk.FLAT
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=5)
        tk.Button(
            opts, text="Browse", bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 9), relief=tk.FLAT, padx=10, cursor="hand1",
            command=self._browse_backup_dest
        ).grid(row=0, column=2, padx=(5, 0), pady=5)

        self.backup_all_networks = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts, text="Backup all networks", variable=self.backup_all_networks,
            bg=BG_SECONDARY, fg=TEXT_PRIMARY, font=("Segoe UI", 10),
            selectcolor=BG_SECONDARY, activebackground=BG_SECONDARY, activeforeground=TEXT_PRIMARY
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=5)

        # Progress
        progress_frame = tk.LabelFrame(
            container, text="  Progress  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW, padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        progress_frame.pack(fill=tk.X, pady=15)
        progress_frame.grid_columnconfigure(0, weight=1)

        self.backup_progress = ttk.Progressbar(
            progress_frame, orient=tk.HORIZONTAL, length=100,
            mode="determinate", style="Dark.Horizontal.TProgressbar"
        )
        self.backup_progress.grid(row=0, column=0, sticky="ew", pady=8)
        self.backup_progress_label = tk.Label(
            progress_frame, text="Idle", bg=BG_SECONDARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9)
        )
        self.backup_progress_label.grid(row=1, column=0, sticky=tk.W)

        # Log
        tk.Label(
            container, text="Log Output:", bg=BG_DARK, fg=TEXT_SECONDARY,
            font=("Segoe UI", 10, "bold"), pady=10
        ).pack(anchor=tk.W)

        log_frame = tk.Frame(container, bg=BG_SECONDARY, relief=tk.FLAT, bd=1)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.backup_log = ScrollableText(log_frame, height=12)
        self.backup_log.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        btn_frame = tk.Frame(container, bg=BG_DARK)
        btn_frame.pack(fill=tk.X)

        self.backup_start_btn = tk.Button(
            btn_frame, text="▶  Start Backup", bg=SUCCESS, fg="#fff",
            font=("Segoe UI", 11, "bold"), relief=tk.FLAT, padx=25, pady=10,
            cursor="hand1", command=self._start_backup
        )
        self.backup_start_btn.pack(side=tk.LEFT)

        tk.Button(
            btn_frame, text="Clear Log", bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10), relief=tk.FLAT, padx=15, pady=10,
            cursor="hand1", command=self.backup_log.clear
        ).pack(side=tk.LEFT, padx=(10, 0))

        self._set_status("Configure and run a backup from this tab.")

    def _browse_backup_dest(self):
        folder = filedialog.askdirectory(title="Select Backup Destination")
        if folder:
            self.backup_dest_var.set(folder)

    def _start_backup(self):
        if self._backup_in_progress:
            return

        org_id, org = self.config.get_active_org()
        if not org:
            messagebox.showerror("Error", "Select an organization first from the sidebar.")
            return

        api_key = org.get("api_key", "")
        dest = self.backup_dest_var.get().strip()
        if not api_key:
            messagebox.showerror("Error", "No API key for selected organization. Go to Settings.")
            return
        if not dest:
            messagebox.showerror("Error", "Select a backup destination.")
            return

        # Save destination back to org config
        self.config.update_organization(org_id, backup_destination=dest)

        self._backup_in_progress = True
        self.backup_start_btn.config(state=tk.DISABLED, text="⏳  Backup Running...")
        self.backup_log.clear()
        self.backup_progress["value"] = 0

        def run():
            try:
                self._do_backup(api_key, dest, org_id)
            except Exception as e:
                self.backup_log.append_error(f"Fatal error: {e}")
            finally:
                self._backup_in_progress = False
                self.root.after(0, lambda: self.backup_start_btn.config(state=tk.NORMAL, text="▶  Start Backup"))

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _do_backup(self, api_key, dest, org_id):
        self.log.info("Backup started via GUI")
        self.root.after(0, lambda: self.backup_log.append_info("Starting organization backup..."))
        self.root.after(0, lambda: self._set_status(f"Backing up to: {dest}"))

        engine = BackupEngine(api_key, dest, continue_on_error=True)

        def progress_callback(step, total, message):
            pct = int((step / total) * 100) if total > 0 else 0
            self.root.after(0, lambda: [
                self.backup_progress.config(value=pct),
                self.backup_progress_label.config(text=message),
                self.backup_log.append_info(message)
            ])

        engine.set_progress_callback(progress_callback)

        try:
            result_path, errors = engine.backup_organization()

            if result_path:
                # Record last backup time
                ts = datetime.now().strftime("%Y-%m-%d_%H-%M%S")
                self._org_vars.setdefault(org_id, {})["last_backup"] = ts
                self.root.after(0, lambda: self.backup_log.append_success(f"Backup complete: {result_path}"))
                self.root.after(0, lambda: self._set_status(f"Backup saved to: {result_path}"))
            else:
                self.root.after(0, lambda: self.backup_log.append_error(f"Backup failed: {errors[0] if errors else 'Unknown error'}"))

            for err in (errors or []):
                self.root.after(0, lambda e=err: self.backup_log.append_error(e))

        except Exception as e:
            self.root.after(0, lambda: self.backup_log.append_error(f"Exception: {e}"))
            self.log.log_exception("Backup failed", e)

        self.root.after(0, lambda: self.backup_progress.config(value=100))
        self.root.after(0, lambda: self.backup_log.append_info("Backup process finished."))
        self.root.after(0, lambda: self._set_connected(True, self.config.get("organizations", {}).get(org_id, {}).get("name","")))

    # ─── Restore Tab ─────────────────────────────────────────────

    def _show_restore(self):
        self._clear_content()
        self._current_tab = "restore"
        self._highlight_nav("Restore")

        container = tk.Frame(self.content_frame, bg=BG_DARK)
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)
        container.grid_columnconfigure(0, weight=1)

        tk.Label(
            container, text="Restore", bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 20, "bold")
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 15))

        # ── Select Backup ─────────────────────────────────────
        select_frame = tk.LabelFrame(
            container, text="  Select Backup  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW, padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        select_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        select_frame.grid_columnconfigure(0, weight=1)

        self.restore_path_var = tk.StringVar()
        tk.Entry(
            select_frame, textvariable=self.restore_path_var, bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Consolas", 10), insertbackground=TEXT_PRIMARY, relief=tk.FLAT
        ).grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=5)
        tk.Button(
            select_frame, text="Browse", bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 9), relief=tk.FLAT, padx=10, cursor="hand1",
            command=self._browse_restore_path
        ).grid(row=0, column=1, pady=5)
        tk.Button(
            select_frame, text="Load", bg=ACCENT, fg="#fff",
            font=("Segoe UI", 9), relief=tk.FLAT, padx=15, cursor="hand1",
            command=self._load_restore_backup
        ).grid(row=0, column=2, padx=(5, 0), pady=5)

        # ── Backup Preview ─────────────────────────────────────
        preview_frame = tk.LabelFrame(
            container, text="  Backup Contents  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW, padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        preview_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 15))
        container.grid_rowconfigure(2, weight=1)

        self.restore_preview = ScrollableText(preview_frame, height=10)
        self.restore_preview.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # ── Options ─────────────────────────────────────────────
        opts_frame = tk.Frame(container, bg=BG_DARK)
        opts_frame.grid(row=3, column=0, sticky="ew", pady=(0, 15))

        self.dry_run_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts_frame, text="Dry-run (preview changes only)", variable=self.dry_run_var,
            bg=BG_DARK, fg=TEXT_PRIMARY, font=("Segoe UI", 10),
            selectcolor=BG_SECONDARY, activebackground=BG_DARK, activeforeground=TEXT_PRIMARY
        ).pack(side=tk.LEFT)

        self.confirm_restore_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts_frame, text="Confirm before applying", variable=self.confirm_restore_var,
            bg=BG_DARK, fg=TEXT_PRIMARY, font=("Segoe UI", 10),
            selectcolor=BG_SECONDARY, activebackground=BG_DARK, activeforeground=TEXT_PRIMARY
        ).pack(side=tk.LEFT, padx=(20, 0))

        # ── Buttons ──────────────────────────────────────────────
        btn_frame = tk.Frame(container, bg=BG_DARK)
        btn_frame.grid(row=4, column=0, sticky="ew")

        self.restore_preview_btn = tk.Button(
            btn_frame, text="👁  Preview Changes", bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 11), relief=tk.FLAT, padx=20, pady=10,
            cursor="hand1", command=self._preview_restore
        )
        self.restore_preview_btn.pack(side=tk.LEFT)

        self.restore_start_btn = tk.Button(
            btn_frame, text="♻  Restore", bg=HIGHLIGHT, fg="#fff",
            font=("Segoe UI", 11, "bold"), relief=tk.FLAT, padx=25, pady=10,
            cursor="hand1", command=self._start_restore
        )
        self.restore_start_btn.pack(side=tk.LEFT, padx=(10, 0))

        self._set_status("Load a backup folder to preview or restore configurations.")

    def _browse_restore_path(self):
        folder = filedialog.askdirectory(title="Select Backup Folder")
        if folder:
            self.restore_path_var.set(folder)

    def _load_restore_backup(self):
        path = self.restore_path_var.get().strip()
        if not path:
            return

        self.restore_preview.clear()
        self.restore_preview.append_info(f"Loading backup: {path}")

        try:
            info = BackupEngine.inspect_backup(path)
            if not info:
                self.restore_preview.append_error("Invalid or unreadable backup folder")
                return

            self.restore_preview.append_success(f"Backup timestamp: {info['timestamp']}")
            if info.get("organization"):
                org = info["organization"]
                self.restore_preview.append_info(f"Organization: {org.get('organization_name', '?')} ({org.get('organization_id', '?')})")
            self.restore_preview.append_info(f"Networks backed up: {len(info.get('networks', []))}")
            self.restore_preview.append_info(f"Total config files: {info.get('total_files', 0)}")
            self.restore_preview.append("")

            for net in info.get("networks", []):
                products = ", ".join(net.get("product_types", []))
                self.restore_preview.append_info(f"  📁 {net['name']} [{products}] — {net.get('files', 0)} files")

        except Exception as e:
            self.restore_preview.append_error(f"Failed to load backup: {e}")

    def _preview_restore(self):
        path = self.restore_path_var.get().strip()
        if not path:
            messagebox.showwarning("No backup selected", "Please select a backup folder first.")
            return

        org_id, org = self.config.get_active_org()
        if not org:
            messagebox.showerror("Error", "Select an organization first from the sidebar.")
            return

        api_key = org.get("api_key", "")
        if not api_key:
            messagebox.showerror("Error", "No API key for selected organization. Go to Settings.")
            return

        self.restore_preview.append("")
        self.restore_preview.append_info("Running dry-run preview...")

        def run():
            try:
                engine = RestoreEngine(api_key)
                changes, errs = engine.preview_restore(path, target_type="full")
                changes = changes or []
                self.root.after(0, lambda: [
                    self.restore_preview.append_info(f"Changes to be made: {len(changes)}"),
                    *[self.restore_preview.append_info(f"  {c.get('type','?')}: {c.get('name', c.get('file', ''))}") for c in (changes[:30] or [])],
                    *(self.restore_preview.append_warning("...truncated") if len(changes) > 30 else []),
                    *(self.restore_preview.append_error(f"Error: {e}") for e in (errs or []))
                ])
            except Exception as e:
                self.root.after(0, lambda: self.restore_preview.append_error(f"Preview failed: {e}"))

        threading.Thread(target=run, daemon=True).start()

    def _start_restore(self):
        path = self.restore_path_var.get().strip()
        if not path:
            return

        org_id, org = self.config.get_active_org()
        if not org:
            messagebox.showerror("Error", "Select an organization first from the sidebar.")
            return

        api_key = org.get("api_key", "")
        if not api_key:
            messagebox.showerror("Error", "No API key for selected organization. Go to Settings.")
            return

        if self.confirm_restore_var.get():
            confirm = messagebox.askyesno(
                "Confirm Restore",
                "This will apply configuration changes to your Meraki organization.\n"
                "This may overwrite existing settings.\n\nContinue?"
            )
            if not confirm:
                return

        self.restore_start_btn.config(state=tk.DISABLED, text="⏳  Restoring...")
        self.restore_preview.append_info("Restore started...")

        def run():
            try:
                engine = RestoreEngine(api_key)
                errors = engine.restore_organization(path, options={"dry_run": self.dry_run_var.get()})
                self.root.after(0, lambda: [
                    self.restore_preview.append_success("Restore complete!"),
                    *[self.restore_preview.append_error(f"Error: {e}") for e in (errors or [])]
                ])
            except Exception as e:
                self.root.after(0, lambda: self.restore_preview.append_error(f"Restore failed: {e}"))
            finally:
                self.root.after(0, lambda: self.restore_start_btn.config(state=tk.NORMAL, text="♻  Restore"))

        threading.Thread(target=run, daemon=True).start()

    # ─── Logs Tab ───────────────────────────────────────────────

    def _show_logs(self):
        self._clear_content()
        self._current_tab = "logs"
        self._highlight_nav("Logs")

        container = tk.Frame(self.content_frame, bg=BG_DARK)
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        hdr = tk.Frame(container, bg=BG_DARK)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        tk.Label(
            hdr, text="Debug Logs", bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 20, "bold")
        ).pack(side=tk.LEFT)
        tk.Button(
            hdr, text="Clear", bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 9), relief=tk.FLAT, padx=15, cursor="hand1",
            command=self._clear_logs
        ).pack(side=tk.RIGHT, padx=(5, 0))
        tk.Button(
            hdr, text="Export", bg=ACCENT, fg="#fff",
            font=("Segoe UI", 9), relief=tk.FLAT, padx=15, cursor="hand1",
            command=self._export_logs
        ).pack(side=tk.RIGHT)
        hdr.grid_columnconfigure(0, weight=1)

        log_frame = tk.Frame(container, bg=BG_SECONDARY, relief=tk.FLAT, bd=1)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.log_viewer = ScrollableText(log_frame, height=25)
        self.log_viewer.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self._load_logs()

        paths_frame = tk.Frame(container, bg=BG_DARK)
        paths_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        tk.Label(paths_frame, text="Log files:",
                 bg=BG_DARK, fg=TEXT_SECONDARY, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Label(paths_frame, text=log_manager.get_log_path(),
                 bg=BG_DARK, fg=ACCENT, font=("Consolas", 8)).pack(side=tk.LEFT, padx=(5, 0))
        tk.Label(paths_frame, text="  |  Debug:",
                 bg=BG_DARK, fg=TEXT_SECONDARY, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(paths_frame, text=log_manager.get_debug_log_path(),
                 bg=BG_DARK, fg=ACCENT, font=("Consolas", 8)).pack(side=tk.LEFT, padx=(5, 0))

        self._set_status(f"Logs: {log_manager.get_log_path()}")

    def _load_logs(self):
        try:
            log_path = log_manager.get_log_path()
            if os.path.exists(log_path):
                lines = open(log_path).readlines()
                for line in lines[-200:]:
                    line = line.strip()
                    if not line:
                        continue
                    if "ERROR" in line:
                        self.log_viewer.append(line, ERROR)
                    elif "WARNING" in line or "WARN" in line:
                        self.log_viewer.append(line, WARNING)
                    elif "DEBUG" in line:
                        self.log_viewer.append(line, TEXT_SECONDARY)
                    elif "OK" in line or "SUCCESS" in line:
                        self.log_viewer.append(line, SUCCESS)
                    else:
                        self.log_viewer.append(line, TEXT_PRIMARY)
        except Exception as e:
            self.log_viewer.append(f"Error loading logs: {e}", ERROR)

    def _clear_logs(self):
        self.log_viewer.clear()
        log_manager.clear_logs()
        self.log_viewer.append_info("Logs cleared")

    def _export_logs(self):
        path = filedialog.asksaveasfilename(
            title="Export Logs", defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            try:
                log_path = log_manager.get_log_path()
                with open(path, "w") as out:
                    out.write(f"=== Main Log ({log_path}) ===\n\n")
                    if os.path.exists(log_path):
                        out.write(open(log_path).read())
                    out.write(f"\n\n=== Debug Log ({log_manager.get_debug_log_path()}) ===\n\n")
                    debug_path = log_manager.get_debug_log_path()
                    if os.path.exists(debug_path):
                        out.write(open(debug_path).read())
                self.log_viewer.append_success(f"Logs exported to: {path}")
            except Exception as e:
                self.log_viewer.append_error(f"Export failed: {e}")

    # ─── Settings Tab ───────────────────────────────────────────

    def _show_settings(self):
        self._clear_content()
        self._current_tab = "settings"
        self._highlight_nav("Settings")

        container = tk.Frame(self.content_frame, bg=BG_DARK)
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)
        container.grid_columnconfigure(0, weight=1)

        tk.Label(
            container, text="Settings", bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 20, "bold")
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 20))

        # ── Organizations Manager ──────────────────────────────
        orgs_card = tk.LabelFrame(
            container, text="  Organizations  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW, padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        orgs_card.grid(row=1, column=0, sticky="nsew", pady=(0, 15))
        container.grid_rowconfigure(1, weight=1)
        orgs_card.grid_columnconfigure(0, weight=1)

        # Toolbar
        toolbar = tk.Frame(orgs_card, bg=BG_SECONDARY)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            toolbar, text=f"{len(self.config.list_organizations())} organization(s) configured",
            bg=BG_SECONDARY, fg=TEXT_SECONDARY, font=("Segoe UI", 9)
        ).pack(side=tk.LEFT)
        tk.Button(
            toolbar, text="+ Add Org", bg=SUCCESS, fg="#fff",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=12, pady=4,
            cursor="hand1", command=self._show_add_org_dialog
        ).pack(side=tk.RIGHT)

        # Org list
        list_frame = tk.Frame(orgs_card, bg=BG_SECONDARY)
        list_frame.pack(fill=tk.BOTH, expand=True)
        list_frame.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(list_frame, bg=BG_SECONDARY, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.org_list_inner = tk.Frame(canvas, bg=BG_SECONDARY)

        self.org_list_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.org_list_inner, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._render_org_list()

        # ── About ───────────────────────────────────────────────
        about_card = tk.LabelFrame(
            container, text="  About  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW, padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        about_card.grid(row=2, column=0, sticky="ew", pady=(0, 5))

        tk.Label(
            about_card, text="RSITServices — Meraki Backup & Restore",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY, font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        tk.Label(
            about_card, text=f"Version {APP_VERSION}", bg=BG_SECONDARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9)
        ).grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        tk.Label(
            about_card,
            text="Full organization backup and restore for Cisco Meraki.\n"
                 "Supports MX, MS, MR, MV, MG, MT, SM and more.",
            bg=BG_SECONDARY, fg=TEXT_SECONDARY, font=("Segoe UI", 9), wraplength=500, justify=tk.LEFT
        ).grid(row=2, column=0, sticky=tk.W, pady=(0, 5))

    def _render_org_list(self):
        for w in self.org_list_inner.winfo_children():
            w.destroy()

        orgs = self.config.get("organizations", {})
        if not orgs:
            tk.Label(
                self.org_list_inner, text="No organizations added yet.",
                bg=BG_SECONDARY, fg=TEXT_SECONDARY, font=("Segoe UI", 10), pady=20
            ).pack()
            return

        active_id = self.config.get("active_org_id")
        for org_id, org in orgs.items():
            is_active = org_id == active_id
            row_bg = BG_TERTIARY if is_active else BG_SECONDARY
            row = tk.Frame(self.org_list_inner, bg=row_bg, relief=tk.FLAT, bd=0)
            row.pack(fill=tk.X, pady=2)

            label = tk.Label(
                row, text=org.get("name", org_id),
                bg=row_bg, fg=ACCENT if is_active else TEXT_PRIMARY,
                font=("Segoe UI", 10, "bold" if is_active else "normal"),
                padx=10, pady=8, anchor=tk.W
            )
            label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            label.bind("<Button-1>", lambda e, oid=org_id: self._select_org_from_list(oid))

            if is_active:
                tk.Label(row, text="✓ Active", bg=row_bg, fg=SUCCESS,
                         font=("Segoe UI", 8, "bold"), padx=8
                ).pack(side=tk.RIGHT, pady=8, padx=(0, 5))

            edit_btn = tk.Button(
                row, text="Edit", bg=BG_DARK, fg=TEXT_SECONDARY,
                font=("Segoe UI", 8), relief=tk.FLAT, padx=10, pady=6,
                cursor="hand1", command=lambda oid=org_id: self._show_edit_org_dialog(oid)
            )
            edit_btn.pack(side=tk.RIGHT, pady=6, padx=(0, 5))

    def _select_org_from_list(self, org_id):
        self.config.set_active_org(org_id)
        self._populate_org_selector()
        self._render_org_list()
        self._refresh_dashboard()


# ─── App Entry Point ─────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.style = ttk.Style(root)
    try:
        root.style.theme_use("clam")
    except Exception:
        pass
    root.style.configure("Dark.Horizontal.TProgressbar", troughcolor=BG_TERTIARY, background=ACCENT)

    app = MerakiBackupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
