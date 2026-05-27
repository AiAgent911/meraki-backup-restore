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

# Import our modules
from config import ConfigManager
from log_manager import log_manager
from backup_engine import BackupEngine
from restore_engine import RestoreEngine


# ─── Theme Colors ────────────────────────────────────────────────
BG_DARK = "#0d1117"
BG_SECONDARY = "#161b22"
BG_TERTIARY = "#21262d"
BORDER = "#30363d"
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
ACCENT = "#58a6ff"
ACCENT_HOVER = "#79c0ff"
HIGHLIGHT = "#f78166"
SUCCESS = "#3fb950"
WARNING = "#d29922"
ERROR = "#f85149"
SIDEBAR_BG = "#010409"


class ScrollableText(tk.Frame):
    """Scrolling text widget for logs"""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, bg=BG_DARK)
        self._build_widgets(*args, **kwargs)

    def _build_widgets(self, height=20):
        self.text = tk.Text(
            self, wrap=tk.WORD, height=height,
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Consolas", 10), relief=tk.FLAT,
            insertbackground=TEXT_PRIMARY,
            padx=10, pady=10,
            state=tk.DISABLED
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


class MerakiBackupApp:
    """Main application window"""

    def __init__(self, root):
        self.root = root
        self.root.title("RSITServices — Meraki Backup & Restore")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(1000, 680)

        self.config = ConfigManager()
        self.log = log_manager

        self._current_tab = None
        self._backup_in_progress = False
        self._restore_in_progress = False

        self._build_ui()

        # Auto-load last backup info
        self._refresh_dashboard()

    # ─── UI Construction ───────────────────────────────────────

    def _build_ui(self):
        # ── Top header ──────────────────────────────────────────
        header = tk.Frame(self.root, bg=SIDEBAR_BG, height=60)
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

        # Status indicator
        self.status_dot = tk.Canvas(header, width=12, height=12, bg=SIDEBAR_BG, highlightthickness=0)
        self.status_dot.create_oval(2, 2, 12, 12, fill=ERROR, outline="")
        self.status_dot.pack(side=tk.RIGHT, padx=15, pady=12)

        self.status_label = tk.Label(
            header, text="Not Connected", bg=SIDEBAR_BG, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9)
        )
        self.status_label.pack(side=tk.RIGHT, padx=5, pady=12)

        # ── Main body: sidebar + content ────────────────────────
        body = tk.Frame(self.root, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True)

        self._build_sidebar(body)
        self.content_frame = tk.Frame(body, bg=BG_DARK)
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # ── Status bar ─────────────────────────────────────────
        self.statusbar = tk.Label(
            self.root, text="Ready", bg=BG_SECONDARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9), anchor=tk.W, padx=10, pady=4
        )
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM)

        # Show dashboard by default
        self._show_dashboard()

    def _build_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=SIDEBAR_BG, width=200)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # Nav label
        tk.Label(
            sidebar, text="NAVIGATION", bg=SIDEBAR_BG, fg=TEXT_SECONDARY,
            font=("Segoe UI", 8, "bold"), pady=15, padx=15, anchor=tk.W
        ).pack(fill=tk.X)

        nav_items = [
            ("📊", "Dashboard", self._show_dashboard),
            ("💾", "Backup", self._show_backup),
            ("♻️", "Restore", self._show_restore),
            ("📋", "Logs", self._show_logs),
            ("⚙️", "Settings", self._show_settings),
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

        # Version at bottom
        tk.Label(
            sidebar, text="v1.0.0 — RSITServices",
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
        self.status_dot.itemconfig(1, fill=color)
        if connected:
            self.status_label.config(text=f"Connected: {org_name or 'OK'}")
        else:
            self.status_label.config(text="Not Connected")

    # ─── Dashboard ───────────────────────────────────────────────

    def _show_dashboard(self):
        self._clear_content()
        self._current_tab = "dashboard"
        self._highlight_nav("Dashboard")

        container = tk.Frame(self.content_frame, bg=BG_DARK)
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)
        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)

        # Title
        tk.Label(
            container, text="Dashboard", bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 20, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 20))

        # ── Org Info Card ───────────────────────────────────────
        self._make_card(container, row=1, col=0, title="Organization", colspan=2)

        # ── Stats Cards ─────────────────────────────────────────
        self._make_stat_card(container, row=2, col=0, title="Networks", value="—")
        self._make_stat_card(container, row=2, col=1, title="Last Backup", value="Never")

        # ── Quick Actions Card ──────────────────────────────────
        self._make_card(container, row=3, col=0, title="Quick Actions", colspan=2)

        # ── Backup History Card ─────────────────────────────────
        self._make_card(container, row=4, col=0, title="Backup History", colspan=2)

    def _make_card(self, parent, row, col, title, colspan=1):
        card = tk.Frame(parent, bg=BG_SECONDARY, relief=tk.FLAT, bd=1)
        card.config(highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=row, column=col, columnspan=colspan, sticky="nsew", padx=5, pady=5)
        card.grid_columnconfigure(0, weight=1)

        # Card title
        hdr = tk.Frame(card, bg=BG_TERTIARY)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr, text=title, bg=BG_TERTIARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 10, "bold"), padx=12, pady=8
        ).pack(side=tk.LEFT)

        body = tk.Frame(card, bg=BG_SECONDARY)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        body.grid_columnconfigure(0, weight=1)

        # Store body reference for later population
        card.body = body
        return card

    def _make_stat_card(self, parent, row, col, title, value):
        card = tk.Frame(parent, bg=BG_SECONDARY, relief=tk.FLAT, bd=1)
        card.config(highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)

        tk.Label(
            card, text=title, bg=BG_SECONDARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 10), padx=15, pady=(15, 5), anchor=tk.W
        ).pack(fill=tk.X)

        lbl = tk.Label(
            card, text=value, bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 22, "bold"), padx=15, pady=(0, 15), anchor=tk.W
        )
        lbl.pack(fill=tk.X)
        return card

    def _refresh_dashboard(self):
        """Refresh dashboard with current data"""
        if self._current_tab != "dashboard":
            return

        api_key = self.config.get("api_key", "")
        if not api_key:
            self._set_connected(False)
            return

        # Test connection
        try:
            import meraki
            dash = meraki.DashboardAPI(api_key, print_console=False, suppress_logging=True)
            orgs = dash.organizations.getOrganizations()
            if orgs:
                org = orgs[0]
                self._set_connected(True, org.get("name", ""))
            else:
                self._set_connected(False)
        except Exception:
            self._set_connected(False)

    def _populate_dashboard(self, org_name, org_id, network_count, last_backup):
        """Populate dashboard cards with data"""
        # Implementation would update the card bodies with actual data
        pass

    # ─── Backup Tab ─────────────────────────────────────────────

    def _show_backup(self):
        self._clear_content()
        self._current_tab = "backup"
        self._highlight_nav("Backup")

        container = tk.Frame(self.content_frame, bg=BG_DARK)
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        # Title
        tk.Label(
            container, text="Backup", bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 20, "bold")
        ).pack(anchor=tk.W, pady=(0, 15))

        # ── Options frame ───────────────────────────────────────
        opts = tk.LabelFrame(
            container, text="  Backup Options  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW,
            padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        opts.pack(fill=tk.X, pady=(0, 15))

        self.backup_dest_var = tk.StringVar(value=self.config.get("backup_destination") or str(Path.home() / "meraki_backups"))

        tk.Label(opts, text="Destination:", bg=BG_SECONDARY, fg=TEXT_SECONDARY, font=("Segoe UI", 10)
        ).grid(row=0, column=0, sticky=tk.W, pady=5)
        tk.Entry(
            opts, textvariable=self.backup_dest_var, bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Consolas", 10), insertbackground=TEXT_PRIMARY, relief=tk.FLAT, width=50,
            readonlybackground=BG_TERTIARY
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=5)
        tk.Button(
            opts, text="Browse", bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 9), relief=tk.FLAT, padx=10, cursor="hand1",
            command=self._browse_backup_dest
        ).grid(row=0, column=2, padx=(5, 0), pady=5)
        opts.grid_columnconfigure(1, weight=1)

        self.backup_all_networks = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts, text="Backup all networks", variable=self.backup_all_networks,
            bg=BG_SECONDARY, fg=TEXT_PRIMARY, font=("Segoe UI", 10),
            selectcolor=BG_SECONDARY, activebackground=BG_SECONDARY, activeforeground=TEXT_PRIMARY
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=5)

        # ── Progress frame ──────────────────────────────────────
        progress_frame = tk.LabelFrame(
            container, text="  Progress  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW,
            padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        progress_frame.pack(fill=tk.BOTH, expand=True)

        self.backup_progress = ttk.Progressbar(
            progress_frame, orient=tk.HORIZONTAL, length=100,
            mode="determinate", style="Dark.Horizontal.TProgressbar"
        )
        self.backup_progress.pack(fill=tk.X, pady=(0, 10))
        self.backup_progress_label = tk.Label(
            progress_frame, text="Idle", bg=BG_SECONDARY, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9)
        )
        self.backup_progress_label.pack(anchor=tk.W)

        # ── Log area ────────────────────────────────────────────
        log_label = tk.Label(
            container, text="Log Output:", bg=BG_DARK, fg=TEXT_SECONDARY,
            font=("Segoe UI", 10, "bold"), pady=(15, 5)
        )
        log_label.pack(anchor=tk.W)

        log_frame = tk.Frame(container, bg=BG_SECONDARY, relief=tk.FLAT, bd=1)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.backup_log = ScrollableText(log_frame, height=12)
        self.backup_log.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # ── Action buttons ──────────────────────────────────────
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

    def _browse_backup_dest(self):
        folder = filedialog.askdirectory(title="Select Backup Destination")
        if folder:
            self.backup_dest_var.set(folder)
            self.config.set("backup_destination", folder)

    def _start_backup(self):
        if self._backup_in_progress:
            return

        api_key = self.config.get("api_key", "")
        if not api_key:
            messagebox.showerror("Error", "Please configure your API key in Settings first.")
            return

        dest = self.backup_dest_var.get().strip()
        if not dest:
            messagebox.showerror("Error", "Please select a backup destination.")
            return

        self._backup_in_progress = True
        self.backup_start_btn.config(state=tk.DISABLED, text="⏳  Backup Running...")
        self.backup_log.clear()
        self.backup_progress["value"] = 0

        def run():
            try:
                self._do_backup(api_key, dest)
            except Exception as e:
                self.backup_log.append_error(f"Fatal error: {e}")
            finally:
                self._backup_in_progress = False
                self.root.after(0, lambda: self.backup_start_btn.config(state=tk.NORMAL, text="▶  Start Backup"))

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _do_backup(self, api_key, dest):
        self.log.info("Backup started via GUI")
        self.root.after(0, lambda: self.backup_log.append_info("Starting organization backup..."))

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
        self.root.after(0, lambda: self.backup_log.append_info("Backup process finished"))

    # ─── Restore Tab ─────────────────────────────────────────────

    def _show_restore(self):
        self._clear_content()
        self._current_tab = "restore"
        self._highlight_nav("Restore")

        container = tk.Frame(self.content_frame, bg=BG_DARK)
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)
        container.grid_columnconfigure(0, weight=1)

        # Title
        tk.Label(
            container, text="Restore", bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 20, "bold")
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 15))

        # ── Select Backup ────────────────────────────────────────
        select_frame = tk.LabelFrame(
            container, text="  Select Backup  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW,
            padx=15, pady=10, relief=tk.FLAT, bd=0
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
        select_frame.grid_columnconfigure(0, weight=1)

        # ── Backup Preview ───────────────────────────────────────
        preview_frame = tk.LabelFrame(
            container, text="  Backup Contents  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW,
            padx=15, pady=10, relief=tk.FLAT, bd=0
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

        api_key = self.config.get("api_key", "")
        if not api_key:
            messagebox.showerror("Error", "API key not configured. Go to Settings.")
            return

        self.restore_preview.append("")
        self.restore_preview.append_info("Running dry-run preview...")

        def run():
            try:
                engine = RestoreEngine(api_key)
                changes, errs = engine.preview_restore(path, target_type="full")
                self.root.after(0, lambda: [
                    self.restore_preview.append_info(f"Changes to be made: {len(changes)}"),
                    *[self.restore_preview.append_info(f"  {c['type']}: {c.get('name', c.get('file', ''))}") for c in changes[:20]],
                    *(self.restore_preview.append_warning("Truncated...") if len(changes) > 20 else [])
                ])
            except Exception as e:
                self.root.after(0, lambda: self.restore_preview.append_error(f"Preview failed: {e}"))

        threading.Thread(target=run, daemon=True).start()

    def _start_restore(self):
        path = self.restore_path_var.get().strip()
        if not path:
            return

        api_key = self.config.get("api_key", "")
        if not api_key:
            messagebox.showerror("Error", "API key not configured. Go to Settings.")
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

        # Title + buttons
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

        # Log viewer
        log_frame = tk.Frame(container, bg=BG_SECONDARY, relief=tk.FLAT, bd=1)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.log_viewer = ScrollableText(log_frame, height=25)
        self.log_viewer.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Load recent logs
        self._load_logs()

        # ── Log file paths ───────────────────────────────────────
        paths_frame = tk.Frame(container, bg=BG_DARK)
        paths_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        tk.Label(
            paths_frame, text="Log files:",
            bg=BG_DARK, fg=TEXT_SECONDARY, font=("Segoe UI", 9)
        ).pack(side=tk.LEFT)
        tk.Label(
            paths_frame, text=log_manager.get_log_path(),
            bg=BG_DARK, fg=ACCENT, font=("Consolas", 8), cursor="hand1"
        ).pack(side=tk.LEFT, padx=(5, 0))
        tk.Label(
            paths_frame, text="  |  Debug:",
            bg=BG_DARK, fg=TEXT_SECONDARY, font=("Segoe UI", 9)
        ).pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(
            paths_frame, text=log_manager.get_debug_log_path(),
            bg=BG_DARK, fg=ACCENT, font=("Consolas", 8), cursor="hand1"
        ).pack(side=tk.LEFT, padx=(5, 0))

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
            title="Export Logs",
            defaultextension=".txt",
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

        # Title
        tk.Label(
            container, text="Settings", bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Segoe UI", 20, "bold")
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 20))

        # ── API Key ──────────────────────────────────────────────
        key_card = tk.LabelFrame(
            container, text="  Meraki API Key  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW,
            padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        key_card.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        key_card.grid_columnconfigure(1, weight=1)

        self.api_key_var = tk.StringVar(value=self.config.get("api_key", ""))
        self.api_key_show = tk.BooleanVar(value=False)

        self.api_key_entry = tk.Entry(
            key_card, textvariable=self.api_key_var, bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Consolas", 11), insertbackground=TEXT_PRIMARY, relief=tk.FLAT,
            show="*" if not self.api_key_show.get() else ""
        )
        self.api_key_entry.grid(row=0, column=0, columnspan=2, sticky="ew", pady=5)

        tk.Checkbutton(
            key_card, text="Show key", variable=self.api_key_show,
            bg=BG_SECONDARY, fg=TEXT_PRIMARY, font=("Segoe UI", 9),
            selectcolor=BG_SECONDARY, activebackground=BG_SECONDARY, activeforeground=TEXT_PRIMARY,
            command=self._toggle_key_visibility
        ).grid(row=1, column=0, sticky=tk.W, pady=(0, 5))

        tk.Button(
            key_card, text="Save", bg=ACCENT, fg="#fff",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=15, cursor="hand1",
            command=self._save_api_key
        ).grid(row=1, column=1, sticky=tk.E, pady=(0, 5))

        tk.Button(
            key_card, text="Test Connection", bg=SUCCESS, fg="#fff",
            font=("Segoe UI", 9), relief=tk.FLAT, padx=15, cursor="hand1",
            command=self._test_connection
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))

        self.test_result_label = tk.Label(
            key_card, text="", bg=BG_SECONDARY, fg=TEXT_SECONDARY, font=("Segoe UI", 9)
        )
        self.test_result_label.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))

        key_card.grid_columnconfigure(1, weight=1)

        # ── Backup Destination ───────────────────────────────────
        dest_card = tk.LabelFrame(
            container, text="  Backup Destination  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW,
            padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        dest_card.grid(row=2, column=0, sticky="ew", pady=(0, 15))
        dest_card.grid_columnconfigure(0, weight=1)

        self.dest_var = tk.StringVar(value=self.config.get("backup_destination") or str(Path.home() / "meraki_backups"))
        tk.Entry(
            dest_card, textvariable=self.dest_var, bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Consolas", 10), insertbackground=TEXT_PRIMARY, relief=tk.FLAT
        ).grid(row=0, column=0, sticky="ew", pady=5)
        tk.Button(
            dest_card, text="Browse", bg=BG_TERTIARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 9), relief=tk.FLAT, padx=10, cursor="hand1",
            command=self._browse_dest
        ).grid(row=0, column=1, padx=(5, 0), pady=5)
        tk.Button(
            dest_card, text="Save", bg=ACCENT, fg="#fff",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=15, cursor="hand1",
            command=self._save_dest
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        dest_card.grid_columnconfigure(0, weight=1)

        # ── About ───────────────────────────────────────────────
        about_card = tk.LabelFrame(
            container, text="  About  ",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            labelanchor=tk.NW,
            padx=15, pady=10, relief=tk.FLAT, bd=0
        )
        about_card.grid(row=3, column=0, sticky="ew")
        about_card.grid_columnconfigure(0, weight=1)

        tk.Label(
            about_card, text="RSITServices — Meraki Backup & Restore",
            bg=BG_SECONDARY, fg=TEXT_PRIMARY, font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        tk.Label(
            about_card, text="Version 1.0.0", bg=BG_SECONDARY, fg=TEXT_SECONDARY, font=("Segoe UI", 9)
        ).grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        tk.Label(
            about_card,
            text="Full organization backup and restore for Cisco Meraki.\nSupports MX, MS, MR, MV, MG, MT, SM and more.",
            bg=BG_SECONDARY, fg=TEXT_SECONDARY, font=("Segoe UI", 9), wraplength=500, justify=tk.LEFT
        ).grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
        tk.Label(
            about_card, text="API Docs: developer.cisco.com/meraki/",
            bg=BG_SECONDARY, fg=ACCENT, font=("Segoe UI", 9)
        ).grid(row=3, column=0, sticky=tk.W, pady=(0, 5))

    def _toggle_key_visibility(self):
        show = "" if self.api_key_show.get() else "*"
        self.api_key_entry.config(show=show)

    def _save_api_key(self):
        key = self.api_key_var.get().strip()
        self.config.set("api_key", key)
        self.test_result_label.config(text="✓ API key saved", fg=SUCCESS)

    def _test_connection(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            self.test_result_label.config(text="Enter an API key first", fg=WARNING)
            return

        self.test_result_label.config(text="Testing...", fg=TEXT_SECONDARY)
        self.root.update()

        try:
            import meraki
            dash = meraki.DashboardAPI(api_key, print_console=False, suppress_logging=True)
            orgs = dash.organizations.getOrganizations()
            if orgs:
                org = orgs[0]
                self.test_result_label.config(
                    text=f"✓ Connected to: {org.get('name', 'Unknown')} (ID: {org.get('id', '')})",
                    fg=SUCCESS
                )
                self._set_connected(True, org.get("name", ""))
            else:
                self.test_result_label.config(text="✗ No organizations found", fg=ERROR)
                self._set_connected(False)
        except meraki.APIError as e:
            self.test_result_label.config(text=f"✗ API Error {e.status}: {e.message}", fg=ERROR)
            self._set_connected(False)
        except Exception as e:
            self.test_result_label.config(text=f"✗ Error: {e}", fg=ERROR)
            self._set_connected(False)

    def _browse_dest(self):
        folder = filedialog.askdirectory(title="Select Default Backup Destination")
        if folder:
            self.dest_var.set(folder)

    def _save_dest(self):
        dest = self.dest_var.get().strip()
        self.config.set("backup_destination", dest)
        messagebox.showinfo("Saved", f"Backup destination set to:\n{dest}")

    # ─── Navigation Helpers ──────────────────────────────────────

    def _highlight_nav(self, active):
        for label, btn in self.nav_buttons.items():
            if label == active:
                btn.config(bg=BG_TERTIARY, fg=ACCENT)
            else:
                btn.config(bg=SIDEBAR_BG, fg=TEXT_PRIMARY)


# ─── App Entry Point ─────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.style = ttk.Style(root)

    # Configure ttk theme for dark appearance
    try:
        root.style.theme_use("clam")
    except Exception:
        pass

    root.style.configure("Dark.Horizontal.TProgressbar", troughcolor=BG_TERTIARY, background=ACCENT)

    app = MerakiBackupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()