#!/usr/bin/env python3
"""
Nexus Peripheral Control — Interactive Terminal User Interface (TUI)
Complete Rewrite from Scratch matching Caelestia Material 3 Expressive Specification.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent
AULA_TOOLS_DIR = PROJECT_ROOT / "Aula_L99_Linux" / "tools"
DRIVERS_AULA_DIR = PROJECT_ROOT / "drivers" / "aula-l99" / "tools"
DRIVERS_RAPOO_DIR = PROJECT_ROOT / "drivers" / "rapoo-mt760"

sys.path.insert(0, str(PROJECT_ROOT))
if AULA_TOOLS_DIR.exists():
    sys.path.insert(0, str(AULA_TOOLS_DIR))
if DRIVERS_AULA_DIR.exists():
    sys.path.insert(0, str(DRIVERS_AULA_DIR))
if DRIVERS_RAPOO_DIR.exists():
    sys.path.insert(0, str(DRIVERS_RAPOO_DIR))

import rapoo_mt760l_ctl
from aula_l99_hacky import device as aula_device
from aula_l99_hacky import protocol as aula_protocol
from nexus_theme import ThemeTokens, generate_tcss

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    ProgressBar,
    Label,
    Log,
    Select,
    Input,
    TabbedContent,
    TabPane,
)
from textual.reactive import reactive
from textual.events import Click

theme_tokens = ThemeTokens.load()
DYNAMIC_TCSS = generate_tcss(theme_tokens)

DPI_STAGES = (
    (1, 800),
    (2, 1000),
    (3, 1200),
    (4, 1600),
    (5, 2400),
    (6, 3200),
    (7, 4000),
)

AULA_EFFECTS = [
    ("0x01 · Static Color", "0x01"),
    ("0x02 · Single On", "0x02"),
    ("0x03 · Single Off", "0x03"),
    ("0x04 · Glittering", "0x04"),
    ("0x05 · Fluttering", "0x05"),
    ("0x06 · Colourful Waves", "0x06"),
    ("0x07 · Breathing", "0x07"),
    ("0x08 · RGB Spectrum", "0x08"),
    ("0x09 · Outward", "0x09"),
    ("0x0A · Scrolling", "0x0A"),
    ("0x0B · Rolling", "0x0B"),
    ("0x0C · Rotating", "0x0C"),
    ("0x0D · Explode", "0x0D"),
    ("0x0E · Launch", "0x0E"),
    ("0x0F · Ripples", "0x0F"),
    ("0x10 · Flowing Light", "0x10"),
    ("0x11 · Pulsating", "0x11"),
    ("0x12 · Tilt", "0x12"),
    ("0x13 · Shuttle", "0x13"),
    ("0x00 · LEDs Off", "0x00"),
]

SLEEP_OPTIONS = [
    ("Never Sleep", "0"),
    ("1 Minute", "1"),
    ("5 Minutes", "2"),
    ("30 Minutes", "3"),
]

DEBOUNCE_OPTIONS = [
    ("Level 1 (Fastest / 1ms)", "1"),
    ("Level 2 (Normal / 2ms)", "2"),
    ("Level 3 (Stable / 4ms)", "3"),
    ("Level 4 (Filtered / 6ms)", "4"),
    ("Level 5 (Safe / 8ms)", "5"),
]


class DeviceCard(Vertical):
    """Bento-styled container for device cards."""
    pass


class ClickableDeviceCard(Vertical):
    """Clickable Bento-styled container for active device cards on Home screen."""
    def __init__(self, target_tab: str, **kwargs):
        super().__init__(**kwargs)
        self.target_tab = target_tab

    def on_click(self, event: Click) -> None:
        if isinstance(event.widget, Button):
            return
        if hasattr(self.app, "action_goto_tab"):
            self.app.action_goto_tab(self.target_tab)


class NexusTUIApp(App):
    """Caelestia Material 3 Expressive TUI for Nexus Peripheral Control."""

    TITLE = "Nexus Peripheral Control"
    SUB_TITLE = "Caelestia Material 3"
    CSS = DYNAMIC_TCSS
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("escape", "tab_home", "Home"),
        ("h", "tab_home", "Home"),
        ("1", "tab_home", "Home"),
        ("2", "tab_mouse", "Rapoo"),
        ("3", "tab_keyboard", "AULA"),
        ("4", "tab_recovery", "Recovery"),
        ("5", "tab_theme", "Theme"),
        ("r", "refresh_all", "Refresh"),
        ("w", "toggle_win_lock", "Win-Lock"),
        ("s", "sync_rtc", "Sync RTC"),
        ("m", "toggle_monitor", "Toggle LCD Feed"),
        ("p", "pair_mouse", "Pair Mouse"),
    ]

    # Reactive hardware telemetry
    mouse_battery = reactive(0)
    mouse_power = reactive("Offline")
    mouse_mode = reactive("Disconnected")
    mouse_dpi = reactive("Stage 1 (800 DPI)")
    mouse_poll_time = reactive("--")

    kbd_battery = reactive(0)
    kbd_mode = reactive("Disconnected")
    kbd_win_lock = reactive(False)
    kbd_monitor_active = reactive(False)
    kbd_screen_status = reactive("3.98-in IPS Active")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent(id="tabs", initial="tab-home"):
            # 1. EXCLUSIVE HOME (NEXUS HUB) TAB
            with TabPane("🏠 01 Home", id="tab-home"):
                with Container(classes="home-hero-pill"):
                    self.lbl_home_hero = Label("🪐 NEXUS PERIPHERAL CONTROL · HARDWARE DASHBOARD", classes="hero-title")
                    yield self.lbl_home_hero

                with Container(classes="home-bento-grid"):
                    # Mouse Bento
                    with ClickableDeviceCard("tab-mouse", id="card-ov-mouse", classes="device-card-home"):
                        with Horizontal(classes="card-header-row"):
                            yield Label("🖱️ RAPOO MT760L", classes="card-title-lg")
                            self.lbl_ov_mouse_mode = Label("Connecting...", classes="status-badge")
                            yield self.lbl_ov_mouse_mode

                        with Horizontal(classes="gauge-row"):
                            yield Label("Battery :", classes="gauge-label")
                            self.pb_ov_mouse = ProgressBar(total=100, show_eta=False)
                            yield self.pb_ov_mouse
                            self.lbl_ov_mouse_bat = Label("0%", classes="value-text")
                            yield self.lbl_ov_mouse_bat

                        with Horizontal(classes="stat-row"):
                            yield Label("Active DPI :", classes="stat-label")
                            self.lbl_ov_mouse_dpi = Label("--", classes="highlight-val")
                            yield self.lbl_ov_mouse_dpi

                        with Horizontal(classes="stat-row"):
                            yield Label("Power State:", classes="stat-label")
                            self.lbl_ov_mouse_pwr = Label("--", classes="value-text")
                            yield self.lbl_ov_mouse_pwr

                        with Horizontal(classes="card-actions-row"):
                            yield Button("⚙️ Mouse Settings [2]", id="btn-goto-mouse", classes="btn-primary")
                            yield Button("🔄 Refresh", id="btn-ov-mouse-refresh")
                            yield Button("🔗 Pair", id="btn-ov-mouse-pair")

                    # Keyboard Bento
                    with ClickableDeviceCard("tab-keyboard", id="card-ov-kbd", classes="device-card-home"):
                        with Horizontal(classes="card-header-row"):
                            yield Label("⌨️ AULA L99", classes="card-title-lg")
                            self.lbl_ov_kbd_mode = Label("Connecting...", classes="status-badge")
                            yield self.lbl_ov_kbd_mode

                        with Horizontal(classes="gauge-row"):
                            yield Label("Battery :", classes="gauge-label")
                            self.pb_ov_kbd = ProgressBar(total=100, show_eta=False)
                            yield self.pb_ov_kbd
                            self.lbl_ov_kbd_bat = Label("0%", classes="value-text")
                            yield self.lbl_ov_kbd_bat

                        with Horizontal(classes="stat-row"):
                            yield Label("Smart Screen:", classes="stat-label")
                            self.lbl_ov_kbd_screen = Label("3.98-in IPS Active", classes="highlight-val")
                            yield self.lbl_ov_kbd_screen

                        with Horizontal(classes="stat-row"):
                            yield Label("Win-Lock    :", classes="stat-label")
                            self.lbl_ov_kbd_lock = Label("Win-Lock: OFF", classes="value-text")
                            yield self.lbl_ov_kbd_lock

                        with Horizontal(classes="card-actions-row"):
                            yield Button("⚙️ Keyboard Settings [3]", id="btn-goto-kbd", classes="btn-primary")
                            yield Button("🕒 Sync RTC", id="btn-ov-kbd-rtc")
                            yield Button("🔒 Win-Lock", id="btn-ov-kbd-winlock")

                with Horizontal(classes="home-footer-chips"):
                    yield Button("🛠️ Dongle 1 Recovery [4]", id="btn-goto-rec", classes="btn-chip")
                    yield Button("🎨 Theme Inspector [5]", id="btn-goto-theme", classes="btn-chip")
                    yield Button("🔄 Refresh Telemetry [R]", id="btn-home-refresh-all", classes="btn-chip")

            # 2. RAPOO MT760L TAB
            with TabPane("02 Rapoo MT760L", id="tab-mouse"):
                with Horizontal(classes="tab-subnav"):
                    yield Label("🖱️ Rapoo MT760L Detailed Configuration", classes="tab-heading")
                    yield Button("← Return Home [H / Esc]", id="btn-back-home-mouse", classes="btn-back")

                with Horizontal():
                    with DeviceCard(classes="device-card"):
                        yield Label("Hardware Telemetry", classes="card-title")
                        self.lbl_m_mode = Label("--", classes="value-text")
                        yield self.lbl_m_mode
                        yield Label("Battery Level:", classes="info-label")
                        self.pb_m_battery = ProgressBar(total=100, show_eta=False)
                        yield self.pb_m_battery
                        self.lbl_m_bat_pct = Label("0%", classes="value-text")
                        yield self.lbl_m_bat_pct
                        yield Label("Power State:", classes="info-label")
                        self.lbl_m_power = Label("--", classes="highlight-val")
                        yield self.lbl_m_power
                        yield Label("Last Poll Timestamp:", classes="info-label")
                        self.lbl_m_timestamp = Label("--", classes="value-text")
                        yield self.lbl_m_timestamp
                        yield Button("🔄 Refresh Hardware Telemetry", id="btn-m-refresh")

                    with DeviceCard(classes="device-card"):
                        yield Label("7-Stage DPI Preset Selector", classes="card-title")
                        yield Label("Select an active hardware DPI gear:", classes="info-label")
                        with Grid():
                            yield Button("Stage 1 (800)", id="dpi-1")
                            yield Button("Stage 2 (1000)", id="dpi-2")
                            yield Button("Stage 3 (1200)", id="dpi-3")
                            yield Button("Stage 4 (1600)", id="dpi-4")
                            yield Button("Stage 5 (2400)", id="dpi-5")
                            yield Button("Stage 6 (3200)", id="dpi-6")
                            yield Button("Stage 7 (4000)", id="dpi-7")

                        yield Label("Wireless Pairing Wizard", classes="card-title")
                        yield Label("Hold Left + Wheel + Right for 3s in 2.4G mode.", classes="info-label")
                        yield Button("🔗 Trigger Pairing Beacon", id="btn-m-pair")

            # 3. AULA L99 TAB
            with TabPane("03 AULA L99", id="tab-keyboard"):
                with Horizontal(classes="tab-subnav"):
                    yield Label("⌨️ AULA L99 Detailed Configuration", classes="tab-heading")
                    yield Button("← Return Home [H / Esc]", id="btn-back-home-kbd", classes="btn-back")

                with Horizontal():
                    with DeviceCard(classes="device-card"):
                        yield Label("RGB Lighting Matrix (20 Modes)", classes="card-title")
                        yield Label("Lighting Effect:", classes="info-label")
                        self.sel_kbd_effect = Select(AULA_EFFECTS, value="0x06", id="sel-kbd-effect")
                        yield self.sel_kbd_effect

                        yield Label("RGB Hex Color (e.g. 8B5CF6):", classes="info-label")
                        self.in_kbd_color = Input(value="8B5CF6", id="in-kbd-color")
                        yield self.in_kbd_color

                        yield Label("Speed (1-5) & Brightness (1-5):", classes="info-label")
                        with Horizontal():
                            self.sel_kbd_speed = Select([(f"Speed {i}", str(i)) for i in range(1, 6)], value="3", id="sel-kbd-speed")
                            self.sel_kbd_bright = Select([(f"Bright {i}", str(i)) for i in range(1, 6)], value="5", id="sel-kbd-bright")
                            yield self.sel_kbd_speed
                            yield self.sel_kbd_bright

                        yield Label("Direction:", classes="info-label")
                        self.sel_kbd_dir = Select([("Normal Direction", "0"), ("Inverted Direction", "1")], value="0", id="sel-kbd-dir")
                        yield self.sel_kbd_dir

                        yield Button("✨ Apply RGB Lighting", id="btn-kbd-apply-light")

                    with DeviceCard(classes="device-card"):
                        yield Label("Hardware Settings & LCD Screen", classes="card-title")
                        yield Label("Sleep Timeout:", classes="info-label")
                        self.sel_kbd_sleep = Select(SLEEP_OPTIONS, value="2", id="sel-kbd-sleep")
                        yield self.sel_kbd_sleep

                        yield Label("Key Response / Debounce Rate:", classes="info-label")
                        self.sel_kbd_debounce = Select(DEBOUNCE_OPTIONS, value="1", id="sel-kbd-debounce")
                        yield self.sel_kbd_debounce

                        yield Button("⚙ Apply Settings", id="btn-kbd-apply-settings")

                        yield Label("Smart Screen Telemetry Feed:", classes="card-title")
                        self.lbl_kbd_feed_status = Label("Screen Feed: Idle", classes="info-label")
                        yield self.lbl_kbd_feed_status
                        with Horizontal():
                            yield Button("▶ Start LCD Feed", id="btn-kbd-toggle-feed")
                            yield Button("🕒 Sync Clock Once", id="btn-kbd-sync-rtc")
                        yield Button("🔒 Toggle Windows-Key Lock", id="btn-kbd-winlock")

            # 4. RECOVERY TAB
            with TabPane("04 Dongle 1 Recovery", id="tab-recovery"):
                with Horizontal(classes="tab-subnav"):
                    yield Label("🛠️ Dongle 1 Recovery & Diagnostics", classes="tab-heading")
                    yield Button("← Return Home [H / Esc]", id="btn-back-home-rec", classes="btn-back")

                with DeviceCard(classes="device-card"):
                    yield Label("Rapoo Dongle 1 Recovery & Diagnostics", classes="card-title")
                    self.lbl_rec_status = Label("Scanning USB Bus...", classes="status-badge")
                    yield self.lbl_rec_status
                    yield Label("If Dongle 1 was accidentally triggered into DFU Bootloader (24ae:3040):", classes="info-label")
                    yield Static(
                        "1. The Telink TLSR8355 receiver holds DFU state in non-volatile flash header.\n"
                        "2. Unplug the dongle from your external USB hub or port.\n"
                        "3. Wait 5 FULL SECONDS for internal decoupling capacitors to discharge to 0V.\n"
                        "4. Re-plug directly into a laptop USB port to force a cold Power-On Reset (POR).\n"
                        "5. It will immediately re-enumerate in standard Gaming Mode (24ae:1870).\n",
                        classes="value-text"
                    )
                    yield Button("🔍 Re-Scan USB Bus", id="btn-rec-scan")

            # 5. THEME TAB
            with TabPane("05 Theme", id="tab-theme"):
                with Horizontal(classes="tab-subnav"):
                    yield Label("🎨 Caelestia Material 3 Scheme Inspector", classes="tab-heading")
                    yield Button("← Return Home [H / Esc]", id="btn-back-home-theme", classes="btn-back")

                with DeviceCard(classes="device-card"):
                    yield Label(f"Caelestia Material 3 Theme Tokens", classes="card-title")
                    yield Label(f"Active Palette Source: {theme_tokens.source}", classes="highlight-val")
                    yield Static(
                        f"Primary Accent       : {theme_tokens.primary}\n"
                        f"Surface Card         : {theme_tokens.surface}\n"
                        f"Background           : {theme_tokens.background}\n"
                        f"Surface High         : {theme_tokens.surface_high}\n"
                        f"Primary Container    : {theme_tokens.primary_container}\n"
                        f"Secondary Container  : {theme_tokens.secondary_container}\n"
                        f"Text Color           : {theme_tokens.text}\n"
                        f"Gauge Accent Green   : {theme_tokens.accent_green}\n"
                        f"Gauge Accent Cyan    : {theme_tokens.accent_cyan}\n",
                        classes="value-text"
                    )

        # Bottom Event Log
        with Container(id="log-container"):
            yield Label("Hardware Event & Status Log:", classes="info-label")
            self.event_log = Log()
            yield self.event_log

        yield Footer()

    def on_mount(self) -> None:
        from textual.theme import Theme
        caelestia_theme = Theme(
            name="caelestia",
            primary=theme_tokens.primary,
            secondary=theme_tokens.secondary,
            accent=theme_tokens.primary,
            foreground=theme_tokens.text,
            background=theme_tokens.background,
            surface=theme_tokens.surface_container,
            panel=theme_tokens.surface,
            dark=(theme_tokens.mode != "light"),
        )
        self.register_theme(caelestia_theme)
        self.theme = "caelestia"

        # Apply exclusive Home Screen state (hidden tabs bar & hidden bottom log)
        self.update_tab_visibility("tab-home")

        self.log_msg("Nexus TUI initialized with Caelestia theme. Starting asynchronous hardware polling...")
        self.poll_hardware_telemetry()
        self.set_interval(4.0, self.poll_hardware_telemetry)

    @on(TabbedContent.TabActivated)
    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Dynamically toggle tab bar and bottom logs when switching between Home and detail views."""
        self.update_tab_visibility(event.pane.id)

    def update_tab_visibility(self, tab_id: str) -> None:
        """Exclusive Home Screen mode: hide tab bar and bottom logs on Home, reveal on detail views."""
        is_home = (tab_id == "tab-home")
        try:
            from textual.widgets._tabbed_content import ContentTabs
            tabs_bar = self.query_one(ContentTabs)
            tabs_bar.display = not is_home
        except Exception:
            pass
        try:
            log_box = self.query_one("#log-container")
            log_box.display = not is_home
        except Exception:
            pass

    def action_goto_tab(self, tab_id: str) -> None:
        self.set_focus(None)
        self.query_one(TabbedContent).active = tab_id
        self.update_tab_visibility(tab_id)

    def log_msg(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.event_log.write_line(f"[{ts}] {msg}")

    # Watchers for reactive UI synchronization
    def watch_mouse_battery(self, val: int) -> None:
        pct = max(0, min(100, val))
        self.pb_ov_mouse.update(progress=pct)
        self.lbl_ov_mouse_bat.update(f"{pct}%")
        if hasattr(self, "pb_m_battery"):
            self.pb_m_battery.update(progress=pct)
            self.lbl_m_bat_pct.update(f"{pct}%")

    def watch_mouse_mode(self, val: str) -> None:
        self.lbl_ov_mouse_mode.update(val.upper())
        if hasattr(self, "lbl_m_mode"):
            self.lbl_m_mode.update(f"Connection: {val}")

    def watch_mouse_dpi(self, val: str) -> None:
        self.lbl_ov_mouse_dpi.update(val)

    def watch_mouse_power(self, val: str) -> None:
        self.lbl_ov_mouse_pwr.update(val)
        if hasattr(self, "lbl_m_power"):
            self.lbl_m_power.update(val)

    def watch_mouse_poll_time(self, val: str) -> None:
        if hasattr(self, "lbl_m_timestamp"):
            self.lbl_m_timestamp.update(val)

    def watch_kbd_battery(self, val: int) -> None:
        pct = max(0, min(100, val))
        self.pb_ov_kbd.update(progress=pct)
        self.lbl_ov_kbd_bat.update(f"{pct}%")

    def watch_kbd_mode(self, val: str) -> None:
        self.lbl_ov_kbd_mode.update(val.upper())

    def watch_kbd_win_lock(self, val: bool) -> None:
        txt = "Win-Lock: ON (Gaming Mode)" if val else "Win-Lock: OFF"
        self.lbl_ov_kbd_lock.update(txt)

    # Keybinding actions
    def action_tab_home(self) -> None:
        self.action_goto_tab("tab-home")

    def action_tab_mouse(self) -> None:
        self.action_goto_tab("tab-mouse")

    def action_tab_keyboard(self) -> None:
        self.action_goto_tab("tab-keyboard")

    def action_tab_recovery(self) -> None:
        self.action_goto_tab("tab-recovery")

    def action_tab_theme(self) -> None:
        self.action_goto_tab("tab-theme")

    def action_refresh_all(self) -> None:
        self.log_msg("Manual telemetry refresh triggered.")
        self.poll_hardware_telemetry()

    def action_toggle_win_lock(self) -> None:
        self.worker_toggle_winlock()

    def action_sync_rtc(self) -> None:
        self.worker_sync_rtc()

    def action_toggle_monitor(self) -> None:
        self.worker_toggle_monitor()

    def action_pair_mouse(self) -> None:
        self.worker_pair_mouse()

    # Event handlers for buttons
    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id in ("btn-ov-mouse-refresh", "btn-m-refresh", "btn-home-refresh-all"):
            self.poll_hardware_telemetry()
        elif btn_id in ("btn-ov-mouse-pair", "btn-m-pair"):
            self.worker_pair_mouse()
        elif btn_id in ("btn-ov-kbd-rtc", "btn-kbd-sync-rtc"):
            self.worker_sync_rtc()
        elif btn_id in ("btn-ov-kbd-winlock", "btn-kbd-winlock"):
            self.worker_toggle_winlock()
        elif btn_id == "btn-goto-mouse":
            self.action_tab_mouse()
        elif btn_id == "btn-goto-kbd":
            self.action_tab_keyboard()
        elif btn_id == "btn-goto-rec":
            self.action_tab_recovery()
        elif btn_id == "btn-goto-theme":
            self.action_tab_theme()
        elif btn_id.startswith("btn-back-home"):
            self.action_tab_home()
        elif btn_id.startswith("dpi-"):
            stage_num = int(btn_id.split("-")[1])
            self.worker_set_dpi(stage_num)
        elif btn_id == "btn-kbd-apply-light":
            self.worker_apply_lighting()
        elif btn_id == "btn-kbd-apply-settings":
            self.worker_apply_settings()
        elif btn_id == "btn-kbd-toggle-feed":
            self.worker_toggle_monitor()
        elif btn_id == "btn-rec-scan":
            self.worker_scan_recovery()

    # Background Workers (@work(thread=True))
    @work(thread=True)
    def poll_hardware_telemetry(self) -> None:
        """Poll telemetry from Rapoo and AULA in background thread."""
        # 1. Rapoo Mouse
        rapoo_cache = rapoo_mt760l_ctl.load_cache() or {}
        rapoo_devs = rapoo_mt760l_ctl.find_all_rapoo_devices()
        m_mode = "Disconnected"
        if "wired" in rapoo_devs:
            m_mode = "Wired USB (24ae:4500)"
        elif "wireless" in rapoo_devs:
            m_mode = "Wireless 2.4GHz"
        elif "bootloader" in rapoo_devs:
            m_mode = "Bootloader (24ae:3040)"

        m_bat = rapoo_cache.get("battery", 0)
        m_pwr = rapoo_cache.get("power_state", "Offline")
        m_dpi = rapoo_cache.get("dpi_label", "Stage 1 (800 DPI)")
        m_time = rapoo_cache.get("timestamp", "--")

        # 2. AULA Keyboard
        kbd_dev = aula_device.find_l99()
        k_mode = "Disconnected"
        k_bat = self.kbd_battery
        if kbd_dev:
            k_mode = "Wired USB" if kbd_dev.is_cable else "Wireless 2.4GHz"
            if kbd_dev.is_dongle:
                live_bat = aula_device.query_keyboard_battery(kbd_dev)
                if live_bat is not None:
                    k_bat = live_bat

        def update_ui():
            self.mouse_mode = m_mode
            self.mouse_battery = m_bat
            self.mouse_power = m_pwr
            self.mouse_dpi = m_dpi
            self.mouse_poll_time = str(m_time)

            self.kbd_mode = k_mode
            self.kbd_battery = k_bat

        self.call_from_thread(update_ui)

    @work(thread=True)
    def worker_set_dpi(self, stage: int) -> None:
        dpi_val = dict(DPI_STAGES).get(stage, 800)
        self.call_from_thread(self.log_msg, f"Setting Rapoo mouse DPI to Stage {stage} ({dpi_val} DPI)...")
        dev_path, mode = rapoo_mt760l_ctl.find_rapoo_hidraw()
        fd = os.open(dev_path, os.O_RDWR)
        try:
            pkt = bytearray(32)
            pkt[0] = 0xBA
            pkt[1] = 0xAE
            pkt[2] = 0x01
            pkt[3] = stage
            import fcntl
            fcntl.ioctl(fd, rapoo_mt760l_ctl.Hidiocsoutput(32), pkt)
            self.call_from_thread(self.log_msg, f"✔ DPI successfully updated to Stage {stage} ({dpi_val} DPI)")
            self.call_from_thread(lambda: setattr(self, "mouse_dpi", f"Stage {stage} ({dpi_val} DPI)"))
        except Exception as e:
            self.call_from_thread(self.log_msg, f"❌ Failed to set DPI: {e}")
        finally:
            os.close(fd)

    @work(thread=True)
    def worker_apply_lighting(self) -> None:
        mode_str = self.sel_kbd_effect.value or "0x06"
        mode = int(mode_str, 16)
        color_hex = (self.in_kbd_color.value or "8B5CF6").lstrip("#")
        try:
            r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
        except Exception:
            r, g, b = 139, 92, 246

        speed = int(self.sel_kbd_speed.value or "3")
        bright = int(self.sel_kbd_bright.value or "5")
        direction = int(self.sel_kbd_dir.value or "0")

        self.call_from_thread(self.log_msg, f"Applying AULA lighting: Mode=0x{mode:02X}, RGB=({r},{g},{b}), Spd={speed}, Brt={bright}, Dir={direction}")
        ok = aula_device.set_keyboard_lighting(mode, (r, g, b), direction=direction, brightness=bright, speed=speed)
        if ok:
            self.call_from_thread(self.log_msg, "✔ AULA lighting effect successfully applied!")
        else:
            self.call_from_thread(self.log_msg, "❌ Failed to send lighting packet to keyboard.")

    @work(thread=True)
    def worker_apply_settings(self) -> None:
        sleep_lvl = int(self.sel_kbd_sleep.value or "2")
        debounce_lvl = int(self.sel_kbd_debounce.value or "1")
        self.call_from_thread(self.log_msg, f"Applying AULA settings: Sleep={sleep_lvl}, Debounce={debounce_lvl}")
        ok = aula_device.set_keyboard_settings(sleep_level=sleep_lvl, response_level=debounce_lvl)
        if ok:
            self.call_from_thread(self.log_msg, "✔ Keyboard hardware settings applied.")
        else:
            self.call_from_thread(self.log_msg, "❌ Failed to apply keyboard settings.")

    @work(thread=True)
    def worker_toggle_winlock(self) -> None:
        new_val = not self.kbd_win_lock
        self.call_from_thread(self.log_msg, f"Toggling Windows-Key Lock -> {'ON' if new_val else 'OFF'}...")
        ok = aula_device.set_keyboard_shortcut_locks(win_lock=new_val)
        if ok:
            self.call_from_thread(lambda: setattr(self, "kbd_win_lock", new_val))
            self.call_from_thread(self.log_msg, f"✔ Windows-Key Lock is now {'ON' if new_val else 'OFF'}.")
        else:
            self.call_from_thread(self.log_msg, "❌ Failed to set Win-Lock state.")

    @work(thread=True)
    def worker_sync_rtc(self) -> None:
        now = datetime.datetime.now()
        self.call_from_thread(self.log_msg, f"Synchronizing AULA RTC Clock: {now.strftime('%H:%M:%S')}...")
        dev = aula_device.find_l99()
        if not dev:
            self.call_from_thread(self.log_msg, "❌ Keyboard not found.")
            return
        try:
            with aula_device.HidrawTransport(dev.path, timeout_seconds=1.5) as transport:
                transport.drain()
                if dev.is_dongle:
                    for transaction in aula_protocol.build_dongle_handshake():
                        payload = transaction.outgoing.ljust(aula_protocol.DONGLE_PACKET_SIZE, b"\x00")
                        transport.write(bytes([aula_protocol.REPORT_ID]) + payload)
                        transport.read_report(max_length=aula_protocol.DONGLE_PACKET_SIZE)
                    packet = aula_protocol.build_dongle_rtc_packet(now)
                    payload = packet.ljust(aula_protocol.DONGLE_PACKET_SIZE, b"\x00")
                    transport.write(bytes([aula_protocol.REPORT_ID]) + payload)
                    transport.read_report(max_length=aula_protocol.DONGLE_PACKET_SIZE)
                else:
                    for transaction in aula_protocol.build_rtc_transfer(now, view=1):
                        transport.set_feature(bytes([aula_protocol.REPORT_ID]) + transaction.outgoing)
                        time.sleep(0.01)
            self.call_from_thread(self.log_msg, "✔ Keyboard RTC clock successfully synchronized.")
        except Exception as e:
            self.call_from_thread(self.log_msg, f"❌ Failed to sync RTC: {e}")

    @work(thread=True)
    def worker_pair_mouse(self) -> None:
        self.call_from_thread(self.log_msg, "Starting 3-button wireless pairing sequence for Rapoo MT760L...")
        success = rapoo_mt760l_ctl.pair_mouse()
        if success:
            self.call_from_thread(self.log_msg, "🎉 SUCCESS: Rapoo MT760L paired to receiver!")
        else:
            self.call_from_thread(self.log_msg, "❌ Pairing timed out. Make sure to hold Left + Middle + Right.")

    @work(thread=True)
    def worker_toggle_monitor(self) -> None:
        if self.kbd_monitor_active:
            self.kbd_monitor_active = False
            self.call_from_thread(self.log_msg, "Stopping LCD Screen Telemetry Feed.")
            self.call_from_thread(lambda: self.lbl_kbd_feed_status.update("Screen Feed: Stopped"))
            return

        self.kbd_monitor_active = True
        self.call_from_thread(self.log_msg, "Starting LCD Screen Telemetry Feed...")
        self.call_from_thread(lambda: self.lbl_kbd_feed_status.update("Screen Feed: Streaming active"))

        try:
            import psutil
        except ImportError:
            self.call_from_thread(self.log_msg, "❌ psutil missing. Cannot stream hardware metrics.")
            self.kbd_monitor_active = False
            return

        dev = aula_device.find_l99()
        if not dev:
            self.call_from_thread(self.log_msg, "❌ Keyboard not found.")
            self.kbd_monitor_active = False
            return

        while self.kbd_monitor_active:
            cpu_load = int(psutil.cpu_percent(interval=None))
            cpu_temp = 45
            try:
                temps = psutil.sensors_temperatures()
                for s in ("coretemp", "k10temp", "zenpower", "legion_hwmon"):
                    if temps.get(s):
                        cpu_temp = int(temps[s][0].current)
                        break
            except Exception:
                pass

            gpu_load, gpu_temp = 0, 40
            try:
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=0.8, check=False,
                )
                if res.returncode == 0:
                    parts = res.stdout.strip().split(",")
                    gpu_load, gpu_temp = int(parts[0].strip()), int(parts[1].strip())
            except Exception:
                pass

            now = datetime.datetime.now()
            monitor = aula_protocol.MonitorData(
                cpu_load=cpu_load,
                cpu_temp=cpu_temp,
                gpu_load=gpu_load,
                gpu_temp=gpu_temp,
                humidity=50,
                condition=aula_protocol.parse_condition("clear"),
            )

            try:
                with aula_device.HidrawTransport(dev.path, timeout_seconds=1.5) as transport:
                    transport.drain()
                    if dev.is_dongle:
                        packet = aula_protocol.build_dongle_rtc_packet(now, monitor)
                        payload = packet.ljust(aula_protocol.DONGLE_PACKET_SIZE, b"\x00")
                        transport.write(bytes([aula_protocol.REPORT_ID]) + payload)
                        transport.read_report(max_length=aula_protocol.DONGLE_PACKET_SIZE)
                    else:
                        for transaction in aula_protocol.build_rtc_transfer(now, monitor, view=1):
                            transport.set_feature(bytes([aula_protocol.REPORT_ID]) + transaction.outgoing)
                            time.sleep(0.01)
                self.call_from_thread(lambda: self.lbl_kbd_feed_status.update(f"Streaming: CPU {cpu_load}% ({cpu_temp}°C) | GPU {gpu_load}%"))
            except Exception as e:
                self.call_from_thread(self.log_msg, f"Stream error: {e}")

            for _ in range(25):
                if not self.kbd_monitor_active:
                    break
                time.sleep(0.1)

    @work(thread=True)
    def worker_scan_recovery(self) -> None:
        self.call_from_thread(self.log_msg, "Scanning USB bus for Rapoo receivers...")
        rapoo_devs = rapoo_mt760l_ctl.find_all_rapoo_devices()
        bootloader_active = "bootloader" in rapoo_devs
        wireless_active = "wireless" in rapoo_devs

        def update():
            if bootloader_active:
                self.lbl_rec_status.update("DFU BOOTLOADER ACTIVE (24ae:3040)")
                self.log_msg("⚠ Dongle 1 detected in DFU bootloader mode. Follow recovery steps.")
            elif wireless_active:
                self.lbl_rec_status.update("NORMAL GAMING RECEIVER ACTIVE (24ae:1870)")
                self.log_msg("✔ Receiver is operating in normal gaming mode.")
            else:
                self.lbl_rec_status.update("NO RAPOO RECEIVER DETECTED")
                self.log_msg("No Rapoo wireless receivers currently enumerated.")

        self.call_from_thread(update)


def main() -> None:
    app = NexusTUIApp()
    app.run()


if __name__ == "__main__":
    main()
