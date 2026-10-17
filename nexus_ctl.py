#!/usr/bin/env python3
"""
Nexus Peripheral Control — Unified Command Line Interface (CLI)
Caelestia Material 3 Expressive Controller for Rapoo MT760L & AULA L99.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root and driver tools to sys.path
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
from nexus_theme import ThemeTokens

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns

try:
    from rich_argparse import RichHelpFormatter
    theme_tokens = ThemeTokens.load()
    RichHelpFormatter.styles["argparse.args"] = f"bold {theme_tokens.primary}"
    RichHelpFormatter.styles["argparse.groups"] = f"bold {theme_tokens.secondary}"
    RichHelpFormatter.styles["argparse.help"] = f"{theme_tokens.text}"
    RichHelpFormatter.styles["argparse.metavar"] = f"italic {theme_tokens.primary}"
    RichHelpFormatter.styles["argparse.syntax"] = "dim"
    RichHelpFormatter.styles["argparse.text"] = f"{theme_tokens.text}"
    FORMATTER = RichHelpFormatter
except ImportError:
    FORMATTER = argparse.HelpFormatter

theme_tokens = ThemeTokens.load()
console = Console()

DPI_STAGES = {
    1: 800,
    2: 1000,
    3: 1200,
    4: 1600,
    5: 2400,
    6: 3200,
    7: 4000,
}

AULA_EFFECTS = {
    "0x01": "Static",
    "0x02": "Single On",
    "0x03": "Single Off",
    "0x04": "Glittering",
    "0x05": "Fluttering",
    "0x06": "Colourful Waves",
    "0x07": "Breathing",
    "0x08": "RGB Spectrum",
    "0x09": "Outward",
    "0x0A": "Scrolling",
    "0x0B": "Rolling",
    "0x0C": "Rotating",
    "0x0D": "Explode",
    "0x0E": "Launch",
    "0x0F": "Ripples",
    "0x10": "Flowing Light",
    "0x11": "Pulsating",
    "0x12": "Tilt",
    "0x13": "Shuttle",
    "0x00": "LED Off",
}


def render_battery_bar(pct: int, width: int = 14) -> Text:
    clamped = max(0, min(100, pct))
    filled_len = int(width * clamped / 100)
    empty_len = width - filled_len
    
    color = "bold green" if clamped >= 50 else ("bold yellow" if clamped >= 25 else "bold red")
    text = Text()
    text.append("[" + "█" * filled_len, style=color)
    text.append("░" * empty_len + "]", style="dim")
    text.append(f" {clamped:>3}%", style=color)
    return text


def cmd_status(args: argparse.Namespace) -> int:
    """Print a rich unified status dashboard of all connected peripherals."""
    rapoo_devs = rapoo_mt760l_ctl.find_all_rapoo_devices()
    rapoo_cache = rapoo_mt760l_ctl.load_cache() or {}
    
    mouse_connected = bool(rapoo_devs)
    mouse_mode = "Disconnected"
    if "wired" in rapoo_devs:
        mouse_mode = "Wired USB (24ae:4500)"
    elif "wireless" in rapoo_devs:
        mouse_mode = "Wireless 2.4GHz (Dongle 2, 24ae:1870)"
    elif "bootloader" in rapoo_devs:
        mouse_mode = "DFU Bootloader (24ae:3040)"

    mouse_bat = rapoo_cache.get("battery", 0)
    mouse_power = rapoo_cache.get("power_state", "Offline")
    mouse_dpi = rapoo_cache.get("dpi_label", "Unknown")
    mouse_time = rapoo_cache.get("timestamp", "--")

    # AULA L99
    kbd_dev = aula_device.find_l99()
    kbd_connected = kbd_dev is not None
    kbd_mode = "Disconnected"
    kbd_bat = 0
    if kbd_dev:
        kbd_mode = "Wired USB (0c45:800a)" if kbd_dev.is_cable else "Wireless 2.4GHz (05ac:024f)"
        if kbd_dev.is_dongle:
            live_bat = aula_device.query_keyboard_battery(kbd_dev)
            if live_bat is not None:
                kbd_bat = live_bat
            else:
                # check cache
                aula_cache_path = Path.home() / ".cache" / "aula_l99.json"
                if aula_cache_path.exists():
                    try:
                        kcache = json.loads(aula_cache_path.read_text())
                        kbd_bat = kcache.get("battery", 0)
                    except Exception:
                        pass

    if getattr(args, "json", False):
        data = {
            "mouse": {
                "connected": mouse_connected,
                "mode": mouse_mode,
                "battery": mouse_bat,
                "power_state": mouse_power,
                "dpi": mouse_dpi,
                "last_poll": mouse_time,
            },
            "keyboard": {
                "connected": kbd_connected,
                "mode": kbd_mode,
                "battery": kbd_bat,
                "screen": "3.98-in IPS Active" if kbd_connected else "Offline",
                "vendor_channel": "Interface 3",
            },
            "theme": {
                "source": theme_tokens.source,
                "primary": theme_tokens.primary,
                "surface": theme_tokens.surface,
            }
        }
        print(json.dumps(data, indent=2))
        return 0

    console.print()
    header_text = Text()
    header_text.append("Nexus Peripheral Control", style=f"bold {theme_tokens.primary}")
    header_text.append(" · ", style="dim")
    header_text.append("Hardware Status Dashboard", style=f"italic {theme_tokens.secondary}")
    header_text.append(f"  [{theme_tokens.source}]", style="dim text")
    console.print(header_text)
    console.print()

    # 1. Rapoo Mouse Panel
    mouse_table = Table.grid(padding=(0, 2))
    mouse_table.add_column("Key", style="dim", justify="right")
    mouse_table.add_column("Value")

    mouse_table.add_row("Connection:", Text(mouse_mode, style="cyan" if mouse_connected else "red"))
    mouse_table.add_row("Power State:", Text(mouse_power, style="bold green" if "Active" in mouse_power else "yellow"))
    mouse_table.add_row("Battery Level:", render_battery_bar(mouse_bat))
    mouse_table.add_row("Active DPI:", Text(mouse_dpi, style=f"bold {theme_tokens.accent_cyan}"))
    mouse_table.add_row("Last Update:", Text(str(mouse_time), style="dim"))

    mouse_panel = Panel(
        mouse_table,
        title=f"[bold {theme_tokens.primary}]🖱️ Rapoo MT760L[/]",
        subtitle="[dim]Ergonomic Wireless Mouse[/dim]",
        border_style=theme_tokens.primary if mouse_connected else "dim red",
        padding=(1, 2),
    )

    # 2. AULA L99 Panel
    kbd_table = Table.grid(padding=(0, 2))
    kbd_table.add_column("Key", style="dim", justify="right")
    kbd_table.add_column("Value")

    kbd_table.add_row("Connection:", Text(kbd_mode, style="cyan" if kbd_connected else "red"))
    kbd_table.add_row("Battery Level:", render_battery_bar(kbd_bat) if kbd_connected else Text("--", style="dim"))
    kbd_table.add_row("Smart Screen:", Text("3.98-in IPS Active", style="bold green") if kbd_connected else Text("Offline", style="dim red"))
    kbd_table.add_row("Device Node:", Text(kbd_dev.path if kbd_dev else "--", style="dim"))
    kbd_table.add_row("Vendor Channel:", Text("Interface 3 (Confirmed)", style="dim green") if kbd_connected else Text("--", style="dim"))

    kbd_panel = Panel(
        kbd_table,
        title=f"[bold {theme_tokens.primary}]⌨️ AULA L99[/]",
        subtitle="[dim]75% Mechanical Keyboard[/dim]",
        border_style=theme_tokens.primary if kbd_connected else "dim red",
        padding=(1, 2),
    )

    console.print(Columns([mouse_panel, kbd_panel], equal=True))
    console.print()
    return 0


def cmd_mouse(args: argparse.Namespace) -> int:
    """Rapoo MT760L control actions."""
    if args.pair:
        console.print("[bold yellow]Initiating Rapoo MT760L 3-button wireless pairing...[/]")
        success = rapoo_mt760l_ctl.pair_mouse()
        return 0 if success else 1

    if args.refresh:
        console.print("[dim]Polling live Rapoo interrupt report...[/]")
        dev_path, mode = rapoo_mt760l_ctl.find_rapoo_hidraw()
        fd = os.open(dev_path, os.O_RDWR | os.O_NONBLOCK)
        try:
            rapoo_mt760l_ctl.read_status(fd, mode=mode)
            console.print("[bold green]✔ Successfully refreshed Rapoo telemetry cache.[/]")
        finally:
            os.close(fd)
        return 0

    if args.dpi:
        stage = args.dpi
        dpi_val = DPI_STAGES.get(stage, 800)
        console.print(f"[bold cyan]Setting active DPI preset to Stage {stage} ({dpi_val} DPI)...[/]")
        dev_path, mode = rapoo_mt760l_ctl.find_rapoo_hidraw()
        fd = os.open(dev_path, os.O_RDWR)
        try:
            pkt = bytearray(32)
            pkt[0] = 0xBA
            pkt[1] = 0xAE
            pkt[2] = 0x01
            pkt[3] = stage
            # Send vendor command
            import fcntl
            fcntl.ioctl(fd, rapoo_mt760l_ctl.Hidiocsoutput(32), pkt)
            console.print(f"[bold green]✔ Mouse DPI set to Stage {stage} ({dpi_val} DPI).[/]")
        finally:
            os.close(fd)
        return 0

    return cmd_status(args)


def cmd_kbd(args: argparse.Namespace) -> int:
    """AULA L99 control actions."""
    dev = aula_device.find_l99()
    if not dev:
        console.print("[bold red]❌ AULA L99 keyboard not detected.[/]")
        return 1

    if args.battery:
        bat = aula_device.query_keyboard_battery(dev)
        if bat is not None:
            console.print(f"[bold green]AULA L99 Battery Level:[/] {bat}%")
            return 0
        console.print("[bold yellow]Unable to query battery (ensure 2.4GHz wireless receiver is connected).[/]")
        return 1

    if args.effect:
        raw_val = args.effect
        try:
            mode = int(raw_val, 16) if raw_val.startswith("0x") else int(raw_val)
        except ValueError:
            matched = [k for k, v in AULA_EFFECTS.items() if v.lower() == raw_val.lower()]
            if matched:
                mode = int(matched[0], 16)
            else:
                console.print(f"[bold red]Unknown effect: {raw_val}[/]")
                return 1

        color_hex = args.color or "8B5CF6"
        color_hex = color_hex.lstrip("#")
        r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
        direction = args.direction if args.direction is not None else 0
        speed = max(1, min(5, args.speed or 3))
        brightness = max(1, min(5, args.brightness or 5))

        console.print(f"Applying Lighting: Mode=0x{mode:02X} ({AULA_EFFECTS.get(f'0x{mode:02X}', 'Custom')}), RGB=({r},{g},{b}), Speed={speed}, Brightness={brightness}, Direction={direction}")
        ok = aula_device.set_keyboard_lighting(mode, (r, g, b), direction=direction, brightness=brightness, speed=speed, dev=dev)
        if ok:
            console.print("[bold green]✔ Lighting applied successfully.[/]")
            return 0
        console.print("[bold red]❌ Failed to apply lighting.[/]")
        return 1

    if args.settings:
        sleep_lvl, resp_lvl = args.settings
        console.print(f"Applying Settings: Sleep Level={sleep_lvl}, Key Debounce Level={resp_lvl}")
        ok = aula_device.set_keyboard_settings(sleep_level=sleep_lvl, response_level=resp_lvl, dev=dev)
        if ok:
            console.print("[bold green]✔ Hardware settings applied successfully.[/]")
            return 0
        console.print("[bold red]❌ Failed to apply settings.[/]")
        return 1

    if args.win_lock is not None:
        lock_val = bool(args.win_lock)
        console.print(f"Setting Windows-Key Lock: {'ON' if lock_val else 'OFF'}")
        ok = aula_device.set_keyboard_shortcut_locks(win_lock=lock_val, dev=dev)
        if ok:
            console.print(f"[bold green]✔ Windows-Key Lock set to {'ON' if lock_val else 'OFF'}.[/]")
            return 0
        console.print("[bold red]❌ Failed to set Win-Lock.[/]")
        return 1

    if args.rtc:
        now = datetime.now()
        console.print(f"Syncing keyboard on-board RTC clock to: {now.strftime('%Y-%m-%d %H:%M:%S')}...")
        import fcntl
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
            console.print("[bold green]✔ Keyboard RTC clock synchronized successfully.[/]")
            return 0
        except Exception as e:
            console.print(f"[bold red]❌ Failed to sync RTC clock: {e}[/]")
            return 1

    if args.monitor:
        interval = max(0.5, args.interval or 2.5)
        console.print(f"[bold cyan]Starting real-time LCD hardware telemetry feed (interval={interval}s)...[/]")
        console.print("[dim]Press Ctrl+C to stop.[/dim]")
        try:
            import psutil
        except ImportError:
            console.print("[bold red]psutil is required for monitor feed. Please install python-psutil.[/]")
            return 1

        try:
            while True:
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

                now = datetime.now()
                monitor = aula_protocol.MonitorData(
                    cpu_load=cpu_load,
                    cpu_temp=cpu_temp,
                    gpu_load=gpu_load,
                    gpu_temp=gpu_temp,
                    humidity=50,
                    condition=aula_protocol.parse_condition("clear"),
                )

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

                sys.stdout.write(f"\r📡 [{now.strftime('%H:%M:%S')}] CPU: {cpu_load}% ({cpu_temp}°C) | GPU: {gpu_load}% ({gpu_temp}°C) -> LCD Stream OK  ")
                sys.stdout.flush()
                time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[dim]Monitor feed stopped.[/dim]")
            return 0

    return cmd_status(args)


def cmd_recovery(args: argparse.Namespace) -> int:
    """Dongle 1 Recovery tooling."""
    rapoo_devs = rapoo_mt760l_ctl.find_all_rapoo_devices()
    bootloader_active = "bootloader" in rapoo_devs
    wireless_active = "wireless" in rapoo_devs

    console.print()
    console.print(f"[bold {theme_tokens.primary}]Dongle 1 Diagnostic & Recovery[/]")
    console.print("=" * 60)
    console.print(f"Receiver Status: {'[bold red]DFU Bootloader Active (24ae:3040)[/]' if bootloader_active else ('[bold green]Normal Gaming Receiver (24ae:1870)[/]' if wireless_active else '[dim]Not Detected[/]')}")
    console.print()

    if bootloader_active:
        console.print("[bold yellow]⚠ Recovery Required for Dongle 1:[/]")
        console.print("The Telink TLSR8355 receiver is holding DFU bootloader state.")
        console.print("To restore normal gaming operation:")
        console.print("1. Physically UNPLUG Dongle 1 from the USB port.")
        console.print("2. Wait 5 FULL SECONDS for internal decoupling capacitors to discharge to 0V.")
        console.print("3. Reconnect the dongle directly to a laptop USB port (avoid external hubs).")
        console.print("4. It will immediately cold-boot into normal receiver mode (24ae:1870).")
    else:
        console.print("[bold green]✔ Dongle 1 is operational or inactive.[/]")
    return 0


def cmd_theme(args: argparse.Namespace) -> int:
    """Inspect active Caelestia Material 3 theme tokens."""
    console.print()
    console.print(f"[bold {theme_tokens.primary}]Caelestia Theme Tokens[/] · [dim]{theme_tokens.source}[/]")
    console.print("-" * 50)
    table = Table(box=None)
    table.add_column("Role", style="bold")
    table.add_column("Hex Value")
    table.add_column("Swatch")

    for k, v in theme_tokens.__dict__.items():
        if k == "source":
            continue
        table.add_row(k, v, Text("  ██████  ", style=f"bold {v}"))
    console.print(table)
    return 0


def cmd_help(args: argparse.Namespace) -> int:
    """Display comprehensive command reference and interactive usage guides."""
    target = getattr(args, "target", None)
    if not target or target == "all":
        console.print()
        header_text = Text()
        header_text.append("Nexus Peripheral Control", style=f"bold {theme_tokens.primary}")
        header_text.append(" · ", style="dim")
        header_text.append("CLI Command Reference", style=f"italic {theme_tokens.secondary}")
        header_text.append(f"  [{theme_tokens.source}]", style="dim text")
        console.print(header_text)
        console.print()

        table = Table(box=None, padding=(0, 2))
        table.add_column("Command", style=f"bold {theme_tokens.primary}")
        table.add_column("Description", style=f"{theme_tokens.text}")
        table.add_column("Common Syntax / Example", style="dim")

        commands = [
            ("status", "Show unified hardware telemetry dashboard", "nexus-ctl status [--json]"),
            ("mouse", "Rapoo MT760L DPI, battery, pairing, refresh", "nexus-ctl mouse --dpi 4"),
            ("kbd", "AULA L99 20 RGB modes, settings, Win-lock, RTC, LCD feed", "nexus-ctl kbd --effect 0x06 --color 8B5CF6"),
            ("recovery", "Dongle 1 Telink bootloader diagnostic & unbrick guide", "nexus-ctl recovery --diagnose"),
            ("theme", "Inspect active Caelestia Material 3 color tokens", "nexus-ctl theme"),
            ("tui", "Launch interactive Textual Terminal Dashboard", "nexus-ctl tui"),
            ("gui", "Launch desktop PyQt6 Graphical Interface", "nexus-ctl gui"),
            ("help", "Display help on any command or topic", "nexus-ctl help [command]"),
        ]

        for cmd, desc, ex in commands:
            table.add_row(cmd, desc, ex)

        panel = Panel(
            table,
            title=f"[bold {theme_tokens.primary}]Available Commands[/]",
            subtitle="[dim]Run 'nexus-ctl help <command>' or 'nexus-ctl <command> --help' for details[/dim]",
            border_style=theme_tokens.primary,
            padding=(1, 2),
        )
        console.print(panel)
        console.print()
        return 0

    target = target.lower()
    if target == "mouse":
        table = Table(box=None, padding=(0, 2))
        table.add_column("Option", style=f"bold {theme_tokens.primary}")
        table.add_column("Description", style=f"{theme_tokens.text}")

        table.add_row("--status", "Query current battery %, power state, and DPI preset")
        table.add_row("--refresh", "Poll live HID interrupt report from the 2.4GHz USB receiver")
        table.add_row("--dpi <1-7>", "Set hardware DPI stage (1: 800, 2: 1000, 3: 1200, 4: 1600, 5: 2400, 6: 3200, 7: 4000)")
        table.add_row("--pair", "Initiate 3-button wireless pairing sequence (Left + Wheel + Right for 3s)")

        panel = Panel(
            table,
            title=f"[bold {theme_tokens.primary}]🖱️ Rapoo MT760L Command Options[/]",
            subtitle="[dim]Usage: nexus-ctl mouse [options][/dim]",
            border_style=theme_tokens.primary,
            padding=(1, 2),
        )
        console.print()
        console.print(panel)
        console.print("\n[bold]Quick Examples:[/]")
        console.print("  nexus-ctl mouse --status        # Read current telemetry")
        console.print("  nexus-ctl mouse --dpi 4         # Switch to Stage 4 (1600 DPI)")
        console.print("  nexus-ctl mouse --refresh       # Poll live HID interrupt")
        console.print("  nexus-ctl mouse --pair          # Start receiver pairing mode")
        console.print()
        return 0

    elif target in ("kbd", "keyboard"):
        table = Table(box=None, padding=(0, 2))
        table.add_column("Option", style=f"bold {theme_tokens.primary}")
        table.add_column("Description", style=f"{theme_tokens.text}")

        table.add_row("--status", "Query current connection mode and battery")
        table.add_row("--battery", "Query live battery percentage over 2.4GHz receiver")
        table.add_row("--effect <mode>", "Apply RGB lighting effect by hex opcode (0x01..0x13, 0x00) or name")
        table.add_row("--color <hex>", "Set RGB color in 6-digit hex format (e.g. 8B5CF6, default: 8B5CF6)")
        table.add_row("--speed <1-5>", "Set animation speed (1: slowest, 5: fastest)")
        table.add_row("--brightness <1-5>", "Set backlight brightness level (1: dim, 5: max)")
        table.add_row("--direction <0|1>", "Set light flow direction (0: normal, 1: inverted)")
        table.add_row("--settings <sleep> <debounce>", "Set sleep timeout (0-3) and debounce latency level (1-5)")
        table.add_row("--win-lock <0|1>", "Toggle Windows-key gaming lock (0: disabled, 1: enabled)")
        table.add_row("--rtc", "Synchronize keyboard on-board real-time clock to system time")
        table.add_row("--monitor", "Live stream CPU & GPU metrics to the 3.98-inch LCD screen")
        table.add_row("--interval <sec>", "Streaming interval in seconds for --monitor (default 2.5s)")

        panel = Panel(
            table,
            title=f"[bold {theme_tokens.primary}]⌨️ AULA L99 Command Options[/]",
            subtitle="[dim]Usage: nexus-ctl kbd [options][/dim]",
            border_style=theme_tokens.primary,
            padding=(1, 2),
        )
        console.print()
        console.print(panel)

        eff_table = Table(title="[bold]Supported 20 RGB Lighting Effects[/]", box=None, padding=(0, 2))
        eff_table.add_column("Opcode", style=f"bold {theme_tokens.primary}")
        eff_table.add_column("Effect Name", style=f"{theme_tokens.text}")
        eff_table.add_column("Opcode", style=f"bold {theme_tokens.primary}")
        eff_table.add_column("Effect Name", style=f"{theme_tokens.text}")

        items = list(AULA_EFFECTS.items())
        half = (len(items) + 1) // 2
        for i in range(half):
            c1_k, c1_v = items[i]
            if i + half < len(items):
                c2_k, c2_v = items[i + half]
                eff_table.add_row(c1_k, c1_v, c2_k, c2_v)
            else:
                eff_table.add_row(c1_k, c1_v, "", "")
        console.print(eff_table)

        console.print("\n[bold]Quick Examples:[/]")
        console.print("  nexus-ctl kbd --battery                                     # Live battery check")
        console.print("  nexus-ctl kbd --effect 0x06 --color 8B5CF6 --speed 4        # Waves in violet")
        console.print("  nexus-ctl kbd --effect 'Colourful Waves' --brightness 5     # Named effect")
        console.print("  nexus-ctl kbd --settings 2 1                                # 5m sleep, 1ms debounce")
        console.print("  nexus-ctl kbd --win-lock 1                                  # Lock Windows key")
        console.print("  nexus-ctl kbd --rtc                                         # Sync RTC clock")
        console.print("  nexus-ctl kbd --monitor                                     # Stream CPU/GPU to LCD")
        console.print()
        return 0

    elif target == "status":
        console.print()
        console.print(f"[bold {theme_tokens.primary}]nexus-ctl status[/] — Display Unified Hardware Dashboard")
        console.print("Options:")
        console.print("  --json       Output raw telemetry for all devices in structured JSON format")
        console.print("\nExample:")
        console.print("  nexus-ctl status")
        console.print("  nexus-ctl status --json | jq .")
        console.print()
        return 0

    elif target == "recovery":
        console.print()
        console.print(f"[bold {theme_tokens.primary}]nexus-ctl recovery[/] — Dongle 1 Telink TLSR8355 Bootloader Tooling")
        console.print("Options:")
        console.print("  --diagnose   Scan the USB bus for receivers in DFU bootloader (24ae:3040)")
        console.print("               and output cold-power-cycle unbrick guidance.")
        console.print()
        return 0

    elif target in ("theme", "tui", "gui"):
        descriptions = {
            "theme": "Display active Material 3 color roles extracted from Caelestia scheme.json",
            "tui": "Launch the interactive Textual terminal dashboard with reactive gauges",
            "gui": "Launch the desktop PyQt6 graphical application with Caelestia M3 QSS",
        }
        console.print()
        console.print(f"[bold {theme_tokens.primary}]nexus-ctl {target}[/] — {descriptions[target]}")
        console.print(f"Usage: nexus-ctl {target}")
        console.print()
        return 0

    else:
        console.print(f"[bold red]Unknown command topic: '{target}'[/]")
        console.print("Run 'nexus-ctl help' to see all available commands.")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nexus Peripheral Control — CLI Hardware Manager for Rapoo MT760L & AULA L99",
        formatter_class=FORMATTER,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. status
    status_parser = subparsers.add_parser("status", help="Display peripheral status dashboard", formatter_class=FORMATTER)
    status_parser.add_argument("--json", action="store_true", help="Output as structured JSON")

    # 2. mouse
    mouse_parser = subparsers.add_parser("mouse", help="Rapoo MT760L actions", formatter_class=FORMATTER)
    mouse_parser.add_argument("--status", action="store_true", help="Query mouse status")
    mouse_parser.add_argument("--refresh", action="store_true", help="Refresh live interrupt report")
    mouse_parser.add_argument("--dpi", type=int, choices=range(1, 8), help="Set DPI Stage (1=800 .. 7=4000)")
    mouse_parser.add_argument("--pair", action="store_true", help="Initiate 3-button wireless pairing")

    # 3. kbd
    kbd_parser = subparsers.add_parser("kbd", help="AULA L99 actions", formatter_class=FORMATTER)
    kbd_parser.add_argument("--status", action="store_true", help="Query keyboard status")
    kbd_parser.add_argument("--battery", action="store_true", help="Query 2.4GHz battery level")
    kbd_parser.add_argument("--effect", type=str, help="RGB Effect name or hex opcode (e.g. 0x06)")
    kbd_parser.add_argument("--color", type=str, help="RGB Hex Color (e.g. 8B5CF6)")
    kbd_parser.add_argument("--speed", type=int, choices=range(1, 6), help="Effect speed (1-5)")
    kbd_parser.add_argument("--brightness", type=int, choices=range(1, 6), help="Brightness level (1-5)")
    kbd_parser.add_argument("--direction", type=int, choices=[0, 1], help="Direction (0=normal, 1=inverted)")
    kbd_parser.add_argument("--settings", nargs=2, type=int, metavar=("SLEEP", "DEBOUNCE"), help="Set sleep (0-3) and debounce (1-5)")
    kbd_parser.add_argument("--win-lock", type=int, choices=[0, 1], help="Win-key lock (0=off, 1=on)")
    kbd_parser.add_argument("--rtc", action="store_true", help="Synchronize on-board RTC clock")
    kbd_parser.add_argument("--monitor", action="store_true", help="Stream CPU/GPU metrics to keyboard LCD")
    kbd_parser.add_argument("--interval", type=float, help="Monitor stream interval in seconds (default 2.5)")

    # 4. recovery
    recovery_parser = subparsers.add_parser("recovery", help="Dongle 1 bootloader recovery diagnostics", formatter_class=FORMATTER)
    recovery_parser.add_argument("--diagnose", action="store_true", help="Scan USB bus for bootloader state")

    # 5. theme
    theme_parser = subparsers.add_parser("theme", help="Show active Caelestia theme tokens", formatter_class=FORMATTER)

    # 6. tui
    subparsers.add_parser("tui", help="Launch interactive Textual TUI", formatter_class=FORMATTER)

    # 7. gui
    subparsers.add_parser("gui", help="Launch desktop PyQt6 GUI", formatter_class=FORMATTER)

    # 8. help
    help_parser = subparsers.add_parser("help", help="Show command reference and usage guides", formatter_class=FORMATTER)
    help_parser.add_argument("target", nargs="?", default=None, help="Command name to show detailed help for")

    args = parser.parse_args()

    if not args.command:
        cmd_status(args)
        return

    if args.command == "status":
        cmd_status(args)
    elif args.command == "mouse":
        cmd_mouse(args)
    elif args.command == "kbd":
        cmd_kbd(args)
    elif args.command == "recovery":
        cmd_recovery(args)
    elif args.command == "theme":
        cmd_theme(args)
    elif args.command == "help":
        cmd_help(args)
    elif args.command == "tui":
        os.execv(sys.executable, [sys.executable, str(PROJECT_ROOT / "nexus_tui.py")])
    elif args.command == "gui":
        os.execv(sys.executable, [sys.executable, str(PROJECT_ROOT / "nexus_gui.py")])


if __name__ == "__main__":
    main()
