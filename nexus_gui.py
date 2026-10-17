#!/usr/bin/env python3
"""Nexus Peripheral Control — a Caelestia-inspired Rapoo and AULA peripheral manager."""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import re
import select
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.qpa.wayland.textinput.warning=false;kf.config.core.warning=false",
)

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import (
    QEasingCurve,
    QFileSystemWatcher,
    QProcess,
    QProcessEnvironment,
    QPropertyAnimation,
    QPointF,
    QThread,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

APP_DIR = Path(__file__).resolve().parent
TOOLS_DIR = APP_DIR / "Aula_L99_Linux" / "tools"
if not TOOLS_DIR.exists() and (APP_DIR / "drivers" / "aula-l99" / "tools").exists():
    TOOLS_DIR = APP_DIR / "drivers" / "aula-l99" / "tools"
if (APP_DIR / "drivers" / "rapoo-mt760").exists() and str(APP_DIR / "drivers" / "rapoo-mt760") not in sys.path:
    sys.path.insert(0, str(APP_DIR / "drivers" / "rapoo-mt760"))
DEVICE_ASSET_DIR = APP_DIR / "assets" / "devices"
CACHE_FILE = Path.home() / ".cache" / "rapoo_mt760l.json"
AULA_CACHE_FILE = Path.home() / ".cache" / "aula_l99.json"
STATE_DIR = Path.home() / ".local" / "state" / "caelestia"
SCHEME_FILE = STATE_DIR / "scheme.json"
_AULA_IO_LOCK = threading.Lock()

DPI_STAGES = (
    (1, 800),
    (2, 1000),
    (3, 1200),
    (4, 1600),
    (5, 2400),
    (6, 3200),
    (7, 4000),
)
DPI_MAP = {dpi: stage for stage, dpi in DPI_STAGES}
AULA_EFFECTS = (
    ("0x01", "Static"),
    ("0x02", "Single On"),
    ("0x03", "Single Off"),
    ("0x04", "Glittering"),
    ("0x05", "Fluttering"),
    ("0x06", "Colourful Waves"),
    ("0x07", "Breathing"),
    ("0x08", "RGB Spectrum"),
    ("0x09", "Outward"),
    ("0x0A", "Scrolling"),
    ("0x0B", "Rolling"),
    ("0x0C", "Rotating"),
    ("0x0D", "Explode"),
    ("0x0E", "Launch"),
    ("0x0F", "Ripples"),
    ("0x10", "Flowing Light"),
    ("0x11", "Pulsating"),
    ("0x12", "Tilt"),
    ("0x13", "Shuttle"),
    ("0x00", "LED Off"),
)


@dataclass(frozen=True)
class ThemeTokens:
    """M3 role values read from Caelestia's active scheme.json."""

    background: str
    surface: str
    surface_lowest: str
    surface_container: str
    surface_high: str
    surface_highest: str
    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str
    secondary: str
    secondary_container: str
    outline_variant: str
    text: str
    subtext0: str
    source: str = "dark M3 fallback"

    @staticmethod
    def _hex(value: object, fallback: str) -> str:
        if not isinstance(value, str):
            return fallback
        candidate = value.strip()
        if not candidate.startswith("#"):
            candidate = f"#{candidate}"
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", candidate):
            return fallback
        return candidate.upper()

    @classmethod
    def load(cls, path: Path = SCHEME_FILE) -> "ThemeTokens":
        defaults = {
            "background": "#141218",
            "surface": "#1C1A21",
            "surface_lowest": "#17151B",
            "surface_container": "#242129",
            "surface_high": "#2C2932",
            "surface_highest": "#36333D",
            "primary": "#D0BCFF",
            "on_primary": "#39245F",
            "primary_container": "#4F378B",
            "on_primary_container": "#EADDFF",
            "secondary": "#CCC2DC",
            "secondary_container": "#4A4458",
            "outline_variant": "#49454F",
            "text": "#E6E0E9",
            "subtext0": "#CAC4D0",
        }
        aliases = {
            "background": ("background",),
            "surface": ("surface",),
            "surface_lowest": ("surfaceContainerLowest", "surface_container_lowest"),
            "surface_container": ("surfaceContainer", "surfaceContainerLow", "surface_container"),
            "surface_high": ("surfaceContainerHigh", "surface_container_high"),
            "surface_highest": ("surfaceContainerHighest", "surface_container_highest"),
            "primary": ("primary",),
            "on_primary": ("onPrimary", "on_primary"),
            "primary_container": ("primaryContainer", "primary_container"),
            "on_primary_container": ("onPrimaryContainer", "on_primary_container"),
            "secondary": ("secondary",),
            "secondary_container": ("secondaryContainer", "secondary_container"),
            "outline_variant": ("outlineVariant", "outline_variant"),
            "text": ("text", "onSurface", "on_surface"),
            "subtext0": ("subtext0", "subtext1", "onSurfaceVariant", "on_surface_variant"),
        }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            colors = payload.get("colours", payload.get("colors", payload))
            if not isinstance(colors, dict):
                raise ValueError("scheme color map is not an object")
            values = {}
            for role, keys in aliases.items():
                raw = next((colors[key] for key in keys if key in colors), None)
                values[role] = cls._hex(raw, defaults[role])
            for role in ("background", "surface", "surface_lowest", "surface_container", "surface_high", "surface_highest"):
                if values[role] == "#000000":
                    values[role] = defaults[role]
            if values["text"] == "#000000":
                values["text"] = defaults["text"]
            return cls(**values, source=str(path))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return cls(**defaults)


class ProductPhotoLabel(QLabel):
    """Keep product photography uncropped and scale it with its layout."""

    def __init__(self, image_path: Path | str, parent: QWidget | None = None):
        super().__init__(parent)
        self._source = QPixmap(str(image_path))
        self.setObjectName("productPhoto")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if self._source.isNull():
            self.setText("Product image unavailable")

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if not self._source.isNull():
            target = self.contentsRect().size() - QtCore.QSize(12, 12)
            if target.width() > 0 and target.height() > 0:
                self.setPixmap(self._source.scaled(
                    target,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))


class ClickableCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._pressed = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        self._pressed = event.button() == Qt.MouseButton.LeftButton
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._pressed and event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        self._pressed = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class DpiPresetTile(ClickableCard):
    def __init__(self, stage: int, dpi: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.stage = stage
        self.dpi = dpi
        self.setObjectName("dpiTile")
        self.setProperty("active", False)
        self.setProperty("requested", False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)
        layout.addWidget(QLabel(f"STAGE {stage:02d}", objectName="tileStageLabel"))
        self.value_label = QLabel(f"{dpi:,} DPI", objectName="tileDpiLabel")
        layout.addWidget(self.value_label)
        self.state_label = QLabel("WAITING", objectName="tileStateLabel")
        layout.addWidget(self.state_label)
        self.setToolTip("Click to mark a preset. Change the mouse DPI with its physical DPI button; the active tile follows live telemetry.")

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.state_label.setText("ACTIVE" if active else ("PRESET" if self.property("requested") else "WAITING"))
        self._refresh_style()

    def set_requested(self, requested: bool) -> None:
        self.setProperty("requested", requested)
        if not self.property("active"):
            self.state_label.setText("SELECTED" if requested else "WAITING")
        self._refresh_style()

    def _refresh_style(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()


def material_symbol_icon(name: str, size: int, color: str) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont("Material Symbols Rounded")
    if not font.exactMatch():
        font = QFont("Noto Sans Symbols 2")
    font.setPixelSize(max(13, int(size * 0.88)))
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, name)
    painter.end()
    return QIcon(pixmap)


# ---------------------------------------------------------------------------
# Existing asynchronous peripheral workers. Their public signal contracts stay
# stable so device behavior remains separate from this fresh widget hierarchy.
# ---------------------------------------------------------------------------
class RapooTelemetryThread(QThread):
    telemetry_received = pyqtSignal(dict)
    device_status_changed = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.running = True

    def find_hidraw(self) -> tuple[str | None, str]:
        try:
            if str(APP_DIR) not in sys.path:
                sys.path.insert(0, str(APP_DIR))
            import rapoo_mt760l_ctl
            devices = rapoo_mt760l_ctl.find_all_rapoo_devices()
            for key in ("wired", "wireless", "bootloader"):
                if key in devices:
                    return devices[key], key
        except Exception:
            pass
        return None, "disconnected"

    def run(self) -> None:
        while self.running:
            device_path, mode = self.find_hidraw()
            self.device_status_changed.emit(mode, device_path or "")
            if not device_path or mode not in ("wireless", "wired"):
                self.msleep(900)
                continue
            try:
                fd = os.open(device_path, os.O_RDWR | os.O_NONBLOCK)
            except OSError:
                self.msleep(900)
                continue
            try:
                while self.running:
                    readable, _, _ = select.select([fd], [], [], 0.7)
                    if not readable:
                        continue
                    try:
                        data = os.read(fd, 64)
                    except BlockingIOError:
                        continue
                    if len(data) >= 7 and data[0] == 0xBB:
                        battery = min(100, data[6])
                        power_code = data[5]
                        power = {0x01: "Online / Active", 0x00: "Standby / Sleep", 0x02: "Charging"}.get(
                            power_code, f"Status 0x{power_code:02X}"
                        )
                        dpi = int.from_bytes(data[3:5], "little")
                        stage = DPI_MAP.get(dpi, 0)
                        payload = {
                            "mode": mode,
                            "battery": battery,
                            "battery_percent": battery,
                            "power_state": power,
                            "dpi_value": dpi,
                            "dpi_stage": stage,
                            "dpi_label": f"Stage {stage} ({dpi} DPI)" if stage else f"{dpi} DPI",
                            "timestamp": dt.datetime.now().strftime("%H:%M:%S"),
                            "raw": " ".join(f"{byte:02x}" for byte in data),
                        }
                        self.telemetry_received.emit(payload)
                        try:
                            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                            CACHE_FILE.write_text(json.dumps(payload), encoding="utf-8")
                        except OSError:
                            pass
            except OSError:
                pass
            finally:
                os.close(fd)
            self.msleep(350)

    def stop(self) -> None:
        self.running = False


class AulaSystemMonitorThread(QThread):
    stats_updated = pyqtSignal(int, int, int, int, str)

    def __init__(self, interval: float = 2.5, parent: QWidget | None = None):
        super().__init__(parent)
        self.interval = max(0.5, interval)
        self.running = True

    @staticmethod
    def sample_hardware() -> tuple[int, int, int, int]:
        try:
            import psutil
            cpu_load = int(psutil.cpu_percent(interval=None))
        except Exception:
            cpu_load = 0
        cpu_temp = 45
        try:
            import psutil
            temperatures = psutil.sensors_temperatures()
            for sensor in ("coretemp", "k10temp", "zenpower", "legion_hwmon"):
                if temperatures.get(sensor):
                    cpu_temp = int(temperatures[sensor][0].current)
                    break
        except Exception:
            pass
        gpu_load, gpu_temp = 0, 40
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=0.8,
                check=False,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                gpu_load, gpu_temp = int(parts[0].strip()), int(parts[1].strip())
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            pass
        return cpu_load, cpu_temp, gpu_load, gpu_temp

    def run(self) -> None:
        if str(TOOLS_DIR) not in sys.path:
            sys.path.insert(0, str(TOOLS_DIR))
        try:
            from aula_l99_hacky import device, protocol
        except Exception as exc:
            self.stats_updated.emit(0, 0, 0, 0, f"Feed unavailable: {exc}")
            return
        from datetime import datetime

        while self.running:
            cpu_load, cpu_temp, gpu_load, gpu_temp = self.sample_hardware()
            now = datetime.now()
            try:
                with _AULA_IO_LOCK:
                    keyboard = device.find_l99()
                    monitor = protocol.MonitorData(
                        cpu_load=cpu_load,
                        cpu_temp=cpu_temp,
                        gpu_load=gpu_load,
                        gpu_temp=gpu_temp,
                        humidity=50,
                        condition=protocol.parse_condition("clear"),
                    )
                    if keyboard.is_cable:
                        with device.HidrawTransport(keyboard.path) as transport:
                            for transaction in protocol.build_rtc_transfer(now, monitor, view=1):
                                if not self.running:
                                    break
                                transport.set_feature(bytes([protocol.REPORT_ID]) + transaction.outgoing)
                                time.sleep(0.01)
                    else:
                        with device.HidrawTransport(keyboard.path) as transport:
                            transport.drain()
                            for transaction in protocol.build_dongle_handshake():
                                if not self.running:
                                    break
                                payload = transaction.outgoing.ljust(protocol.DONGLE_PACKET_SIZE, b"\x00")
                                transport.write(bytes([protocol.REPORT_ID]) + payload)
                                transport.read_report(max_length=protocol.DONGLE_PACKET_SIZE)
                            if self.running:
                                packet = protocol.build_dongle_rtc_packet(now, monitor)
                                payload = packet.ljust(protocol.DONGLE_PACKET_SIZE, b"\x00")
                                transport.write(bytes([protocol.REPORT_ID]) + payload)
                                transport.read_report(max_length=protocol.DONGLE_PACKET_SIZE)
                status = f"Updated {now.strftime('%H:%M:%S')}"
            except Exception as exc:
                status = f"Feed error: {exc}"
            self.stats_updated.emit(cpu_load, cpu_temp, gpu_load, gpu_temp, status)
            for _ in range(int(self.interval * 10)):
                if not self.running:
                    break
                self.msleep(100)

    def stop(self) -> None:
        self.running = False


class AulaTelemetryThread(QThread):
    """Poll AULA battery without blocking the UI or overlapping LCD I/O."""

    battery_updated = pyqtSignal(int)
    device_status_changed = pyqtSignal(str, str)
    battery_unavailable = pyqtSignal(str)
    poll_finished = pyqtSignal()

    def __init__(self, interval: float = 9.0, parent: QWidget | None = None):
        super().__init__(parent)
        self.interval = max(8.0, min(10.0, interval))
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()

    def request_poll(self) -> None:
        self._wake_event.set()

    def run(self) -> None:
        if str(TOOLS_DIR) not in sys.path:
            sys.path.insert(0, str(TOOLS_DIR))
        try:
            from aula_l99_hacky import device
        except Exception as exc:
            self.device_status_changed.emit("disconnected", "")
            self.battery_unavailable.emit(f"AULA backend unavailable: {exc}")
            self.poll_finished.emit()
            return

        while not self._stop_event.is_set():
            self._wake_event.clear()
            try:
                with _AULA_IO_LOCK:
                    keyboard = device.find_l99()
                    mode = "wired" if keyboard.is_cable else "wireless"
                    self.device_status_changed.emit(mode, keyboard.path)
                    if keyboard.is_dongle:
                        battery = device.query_keyboard_battery(keyboard)
                    else:
                        battery = None
                if battery is None:
                    self.battery_unavailable.emit(
                        "Live battery reads require the 2.4 GHz receiver."
                        if mode == "wired" else "No live battery reply from the keyboard."
                    )
                else:
                    self.battery_updated.emit(max(0, min(100, int(battery))))
            except FileNotFoundError:
                self.device_status_changed.emit("disconnected", "")
                self.battery_unavailable.emit("AULA L99 or its receiver is not connected.")
            except Exception as exc:
                self.battery_unavailable.emit(f"Battery poll failed: {exc}")
            finally:
                self.poll_finished.emit()
            if not self._stop_event.is_set():
                self._wake_event.wait(self.interval)

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()


class AulaCommandThread(QThread):
    """Run AULA hardware commands off the GUI thread with serialized HID I/O."""

    command_finished = pyqtSignal(str, bool, str)
    rtc_metrics = pyqtSignal(int, int, int, int)

    def __init__(self, command: str, values: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.command = command
        self.values = values
        self._cancelled = False

    def run(self) -> None:
        if str(TOOLS_DIR) not in sys.path:
            sys.path.insert(0, str(TOOLS_DIR))
        try:
            from aula_l99_hacky import device, protocol
            if self._cancelled:
                return
            if self.command == "rtc":
                metrics = AulaSystemMonitorThread.sample_hardware()
                self.rtc_metrics.emit(*metrics)
            with _AULA_IO_LOCK:
                keyboard = device.find_l99()
                if self.command == "lighting":
                    rgb = tuple(self.values["rgb"])
                    ok = device.set_keyboard_lighting(
                        int(self.values["mode"]), rgb, int(self.values["direction"]),
                        int(self.values["brightness"]), int(self.values["speed"]), keyboard,
                    )
                    mode_name = dict((int(code, 0), label) for code, label in AULA_EFFECTS).get(
                        int(self.values["mode"]), "lighting"
                    )
                    direction_name = "inverted" if self.values["direction"] else "normal"
                    message = f"Applied {mode_name} · {direction_name} direction." if ok else "Could not apply lighting effect. Check the keyboard link."
                elif self.command == "settings":
                    sleep_level = int(self.values["sleep_level"])
                    response_level = int(self.values["response_level"])
                    ok = device.set_keyboard_settings(sleep_level, response_level, keyboard)
                    message = "Keyboard settings applied." if ok else "Could not apply keyboard settings. Check the link."
                elif self.command == "win_lock":
                    locked = bool(self.values["locked"])
                    ok = keyboard.is_dongle and device.set_keyboard_shortcut_locks(locked, dev=keyboard)
                    message = (
                        f"Windows key {'locked' if locked else 'unlocked'}." if ok
                        else "Windows key lock requires the 2.4 GHz receiver."
                    )
                elif self.command == "rtc":
                    cpu_load, cpu_temp, gpu_load, gpu_temp = metrics
                    now = dt.datetime.now()
                    monitor = protocol.MonitorData(
                        cpu_load=cpu_load,
                        cpu_temp=max(0, cpu_temp),
                        gpu_load=gpu_load,
                        gpu_temp=max(0, gpu_temp),
                        humidity=50,
                        condition=protocol.parse_condition("clear"),
                    )
                    if keyboard.is_cable:
                        with device.HidrawTransport(keyboard.path) as transport:
                            for transaction in protocol.build_rtc_transfer(now, monitor, view=1):
                                transport.set_feature(bytes([protocol.REPORT_ID]) + transaction.outgoing)
                                time.sleep(0.01)
                    else:
                        with device.HidrawTransport(keyboard.path) as transport:
                            transport.drain()
                            for transaction in protocol.build_dongle_handshake():
                                payload = transaction.outgoing.ljust(protocol.DONGLE_PACKET_SIZE, b"\x00")
                                transport.write(bytes([protocol.REPORT_ID]) + payload)
                                transport.read_report(max_length=protocol.DONGLE_PACKET_SIZE)
                            packet = protocol.build_dongle_rtc_packet(now, monitor)
                            payload = packet.ljust(protocol.DONGLE_PACKET_SIZE, b"\x00")
                            transport.write(bytes([protocol.REPORT_ID]) + payload)
                            transport.read_report(max_length=protocol.DONGLE_PACKET_SIZE)
                    message = "Clock and screen statistics sent to the keyboard."
                    ok = True
                else:
                    raise ValueError(f"Unknown AULA command: {self.command}")
            if not self._cancelled:
                self.command_finished.emit(self.command, bool(ok), message)
        except Exception as exc:
            if not self._cancelled:
                self.command_finished.emit(self.command, False, str(exc))

    def stop(self) -> None:
        self._cancelled = True


class RapooPairingWorker(QThread):
    sig_status = pyqtSignal(str)
    sig_finished = pyqtSignal(bool, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.running = True

    def run(self) -> None:
        try:
            if str(APP_DIR) not in sys.path:
                sys.path.insert(0, str(APP_DIR))
            import rapoo_mt760l_ctl
            devices = rapoo_mt760l_ctl.find_all_rapoo_devices()
            token = None
            if "wired" in devices:
                try:
                    fd = os.open(devices["wired"], os.O_RDWR)
                    try:
                        info = rapoo_mt760l_ctl.read_wired_status(fd)
                        token_hex = info.get("token_hex")
                        if token_hex and len(token_hex) == 8:
                            token = bytes.fromhex(token_hex)
                            self.sig_status.emit(f"Read mouse authentication token · 0x{token_hex.upper()}")
                    finally:
                        os.close(fd)
                except Exception:
                    pass
            if token is None:
                cached = rapoo_mt760l_ctl.load_token_cache()
                if cached and cached.get("token_hex"):
                    token = bytes.fromhex(cached["token_hex"])
                    self.sig_status.emit(f"Using cached token · 0x{cached['token_hex'].upper()}")
                else:
                    self.sig_finished.emit(False, "Connect the mouse by USB-C once to read its security key.")
                    return

            receiver = devices.get("wireless_pairing") or devices.get("wireless")
            if not receiver:
                self.sig_finished.emit(False, "Insert Rapoo Dongle 2 (24ae:1870) to begin pairing.")
                return
            fd = os.open(receiver, os.O_RDWR)
            paired = False
            try:
                beacon = bytearray(32)
                beacon[:5] = bytes((0xBA, 0xA0, 0x81, 0x01, 0x00))
                beacon[5:13] = b"\xff" * 8
                beacon[13] = 0xC8
                beacon[21:25] = token
                fcntl.ioctl(fd, rapoo_mt760l_ctl.Hidiocsoutput(32), beacon)
                self.sig_status.emit("Receiver listening · hold Left + Middle + Right for 3 seconds")

                poll = bytearray(32)
                poll[:3] = bytes((0xBA, 0xA1, 0x01))
                deadline = time.monotonic() + 25
                while self.running and time.monotonic() < deadline:
                    try:
                        fcntl.ioctl(fd, rapoo_mt760l_ctl.Hidiocsoutput(32), poll)
                    except OSError:
                        pass
                    time.sleep(0.04)
                    response = bytearray(32)
                    response[0] = 0xBA
                    try:
                        fcntl.ioctl(fd, rapoo_mt760l_ctl.Hidiocginput(32), response)
                    except OSError:
                        time.sleep(0.08)
                        continue
                    if response[:3] == b"\x01\x01\x01":
                        paired = True
                        break
                    remaining = max(0, int(deadline - time.monotonic()))
                    self.sig_status.emit(f"Hold all three buttons · {remaining}s remaining")
                    time.sleep(0.16)
                exit_packet = bytearray(32)
                exit_packet[:3] = bytes((0xBA, 0xA1, 0x80))
                try:
                    fcntl.ioctl(fd, rapoo_mt760l_ctl.Hidiocsoutput(32), exit_packet)
                except OSError:
                    pass
            finally:
                os.close(fd)
            if not self.running:
                self.sig_finished.emit(False, "Pairing cancelled.")
            elif paired:
                self.sig_finished.emit(True, "Rapoo MT760L paired with Dongle 2.")
            else:
                self.sig_finished.emit(False, "Pairing timed out. Check 2.4 GHz mode and hold all three buttons for 3 seconds.")
        except Exception as exc:
            self.sig_finished.emit(False, f"Pairing error: {exc}")

    def stop(self) -> None:
        self.running = False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nexus Peripheral Control")
        self.resize(1140, 880)
        self.setMinimumSize(960, 720)
        self.tokens = ThemeTokens.load()
        self._bar_animations: dict[QProgressBar, QPropertyAnimation] = {}
        self._dashboard_expanded = True
        self.telemetry_worker: RapooTelemetryThread | None = None
        self.sysmon_thread: AulaSystemMonitorThread | None = None
        self.pairing_worker: RapooPairingWorker | None = None
        self.aula_telemetry_worker: AulaTelemetryThread | None = None
        self.aula_command_worker: AulaCommandThread | None = None
        self.action_processes: dict[str, QProcess] = {}
        self.process_callbacks: dict[str, Callable[[int, str, str], None]] = {}
        self.current_color = self.tokens.primary.lstrip("#")
        self.last_aula_metrics = (0, 45, 0, 40)
        self.aula_battery_value: int | None = None
        self.aula_connection_mode = "disconnected"
        self.aula_connection_path = ""
        self._aula_refresh_pending = False
        self._win_lock_confirmed: bool | None = None
        self._pending_win_lock = False
        self._aula_feed_error: str | None = None
        self._requested_dpi_stage: int | None = None
        self.setup_ui()
        self.apply_styles()
        self.start_telemetry_worker()
        self.load_initial_cache()
        self.load_aula_cache()
        self._install_theme_watcher()
        self._sync_dashboard_summary()
        self.start_aula_telemetry_worker()

    # ---- application shell and navigation ---------------------------------
    def setup_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 16, 18, 14)
        root_layout.setSpacing(12)
        self.setCentralWidget(root)

        self.dashboard_surface = QFrame(objectName="dashboardSurface")
        shell = QVBoxLayout(self.dashboard_surface)
        shell.setContentsMargins(18, 12, 18, 14)
        shell.setSpacing(0)

        top_bar = QWidget(objectName="shellStatusBar")
        top = QHBoxLayout(top_bar)
        top.setContentsMargins(2, 0, 2, 10)
        top.setSpacing(10)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        brand.addWidget(QLabel("NEXUS", objectName="brandTitle"))
        brand.addWidget(QLabel("PERIPHERAL CONTROL", objectName="brandSubtitle"))
        top.addLayout(brand)
        top.addStretch(1)

        self.dynamic_island = QPushButton("NEXUS  ·  2 DEVICES")
        self.dynamic_island.setObjectName("dynamicIsland")
        self.dynamic_island.setCheckable(True)
        self.dynamic_island.setChecked(True)
        self.dynamic_island.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dynamic_island.setIcon(material_symbol_icon("devices_other", 20, self.tokens.on_primary))
        self.dynamic_island.setIconSize(QtCore.QSize(20, 20))
        self.dynamic_island.setFixedHeight(46)
        self.dynamic_island.setMinimumWidth(240)
        self.dynamic_island.setMaximumWidth(320)
        self.dynamic_island.clicked.connect(self.toggle_dashboard)
        top.addWidget(self.dynamic_island, alignment=Qt.AlignmentFlag.AlignCenter)

        top.addStretch(1)
        self.top_mouse_chip = QLabel("RAPOO  ·  SEARCHING", objectName="statusChip")
        self.top_mouse_chip.setProperty("state", "searching")
        self.top_aula_chip = QLabel("AULA L99  ·  SEARCHING", objectName="statusChip")
        self.top_aula_chip.setProperty("state", "searching")
        top.addWidget(self.top_mouse_chip)
        top.addWidget(self.top_aula_chip)
        shell.addWidget(top_bar)

        self.dashboard_drawer = self.create_nexus_dashboard()
        shell.addWidget(self.dashboard_drawer)
        root_layout.addWidget(self.dashboard_surface)

        nav = QFrame(objectName="deviceNavigation")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(4, 0, 4, 0)
        nav_layout.setSpacing(8)
        nav_layout.addWidget(QLabel("DEVICES", objectName="sectionEyebrow"))
        nav_layout.addSpacing(4)
        self.nav_mouse_btn = self._nav_button("01   Rapoo MT760L", 0)
        self.nav_kbd_btn = self._nav_button("02   AULA L99", 1)
        self.nav_dfu_btn = self._nav_button("03   Receiver Recovery", 2)
        self.nav_mouse_btn.setChecked(True)
        nav_layout.addWidget(self.nav_mouse_btn)
        nav_layout.addWidget(self.nav_kbd_btn)
        nav_layout.addWidget(self.nav_dfu_btn)
        nav_layout.addStretch(1)
        self.device_index_label = QLabel("DEVICE 01", objectName="monoQuiet")
        nav_layout.addWidget(self.device_index_label)
        root_layout.addWidget(nav)

        self.stack = QStackedWidget()
        self.stack.setObjectName("deviceStack")
        self.page_mouse = self.create_mouse_page()
        self.page_kbd = self.create_keyboard_page()
        self.page_recovery = self.create_recovery_page()
        for page in (self.page_mouse, self.page_kbd, self.page_recovery):
            self.stack.addWidget(self._make_scrollable(page))
        root_layout.addWidget(self.stack, stretch=1)

        self.drawer_animation = QPropertyAnimation(self.dashboard_drawer, b"maximumHeight", self)
        self.drawer_animation.setDuration(460)
        self.drawer_animation.setEasingCurve(self._spring_curve())
        self.drawer_animation.finished.connect(self._finish_drawer_animation)
        self.island_animation = QPropertyAnimation(self.dynamic_island, b"maximumWidth", self)
        self.island_animation.setDuration(420)
        self.island_animation.setEasingCurve(self._spring_curve())
        self.dashboard_drawer.setMaximumHeight(16777215)
        self.dashboard_drawer.adjustSize()
        self._drawer_open_height = max(240, self.dashboard_drawer.sizeHint().height())

    def _nav_button(self, title: str, index: int) -> QPushButton:
        button = QPushButton(title)
        button.setObjectName("deviceTabButton")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, page=index: self.switch_page(page))
        return button

    @staticmethod
    def _spring_curve() -> QEasingCurve:
        curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
        curve.addCubicBezierSegment(QPointF(0.34, 1.56), QPointF(0.64, 1.0), QPointF(1.0, 1.0))
        return curve

    @staticmethod
    def _make_scrollable(page: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidget(page)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        area.setObjectName("deviceScrollArea")
        return area

    def switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_mouse_btn.setChecked(index == 0)
        self.nav_kbd_btn.setChecked(index == 1)
        self.nav_dfu_btn.setChecked(index == 2)
        self.device_index_label.setText(f"DEVICE {index + 1:02d}")

    def toggle_dashboard(self, _checked: bool | None = None) -> None:
        expanded = self.dynamic_island.isChecked()
        self._dashboard_expanded = expanded
        self.dynamic_island.setText("NEXUS  ·  2 DEVICES" if expanded else "NEXUS  ·  DEVICES")
        self.dynamic_island.setIcon(material_symbol_icon(
            "expand_less" if expanded else "expand_more", 20, self.tokens.on_primary
        ))
        self.drawer_animation.stop()
        start_height = self.dashboard_drawer.height()
        target_height = self._drawer_open_height if expanded else 0
        if expanded:
            self.dashboard_drawer.setMaximumHeight(max(0, start_height))
        self.drawer_animation.setStartValue(start_height)
        self.drawer_animation.setEndValue(target_height)
        self.drawer_animation.start()
        self.island_animation.stop()
        self.island_animation.setStartValue(self.dynamic_island.maximumWidth())
        self.island_animation.setEndValue(320 if expanded else 250)
        self.island_animation.start()

    def _finish_drawer_animation(self) -> None:
        if self._dashboard_expanded:
            self.dashboard_drawer.setMaximumHeight(16777215)

    # ---- Nexus dashboard ---------------------------------------------------
    def create_nexus_dashboard(self) -> QFrame:
        drawer = QFrame(objectName="dashboardDrawer")
        outer = QVBoxLayout(drawer)
        outer.setContentsMargins(0, 0, 0, 4)
        outer.setSpacing(12)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(QLabel("YOUR PERIPHERALS", objectName="sectionEyebrow"))
        title_box.addWidget(QLabel("Live status and quick device access", objectName="subtleLabel"))
        heading.addLayout(title_box)
        heading.addStretch(1)
        self.scheme_source_label = QLabel("CAELESTIA THEME", objectName="themePill")
        heading.addWidget(self.scheme_source_label)
        outer.addLayout(heading)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        mouse_card = ClickableCard()
        mouse_card.setObjectName("peripheralOverviewCard")
        mouse_card.clicked.connect(lambda: self.switch_page(0))
        mouse_layout = QHBoxLayout(mouse_card)
        mouse_layout.setContentsMargins(12, 12, 14, 12)
        mouse_layout.setSpacing(12)
        mouse_stage = QFrame(objectName="overviewPhotoStage")
        mouse_stage.setFixedSize(112, 116)
        mouse_photo = QVBoxLayout(mouse_stage)
        mouse_photo.setContentsMargins(6, 6, 6, 6)
        mouse_photo.addWidget(ProductPhotoLabel(DEVICE_ASSET_DIR / "rapoo-mt760l.png"))
        mouse_layout.addWidget(mouse_stage)
        mouse_details = QVBoxLayout()
        mouse_details.setSpacing(5)
        mouse_details.addWidget(QLabel("RAPOO  ·  MT760L", objectName="productEyebrow"))
        mouse_details.addWidget(QLabel("Ergonomic multi-mode mouse", objectName="cardTitle"))
        self.dashboard_mouse_status = QLabel("Searching for mouse or receiver", objectName="statusChip")
        self.dashboard_mouse_status.setProperty("state", "searching")
        mouse_details.addWidget(self.dashboard_mouse_status, alignment=Qt.AlignmentFlag.AlignLeft)
        summary = QHBoxLayout()
        self.dashboard_battery_label = QLabel("BATTERY  ·  --%", objectName="monoStat")
        self.dashboard_dpi_label = QLabel("DPI  ·  --", objectName="monoStat")
        summary.addWidget(self.dashboard_battery_label)
        summary.addStretch(1)
        summary.addWidget(self.dashboard_dpi_label)
        mouse_details.addLayout(summary)
        self.dashboard_battery_bar = QProgressBar(objectName="hubBatteryBar")
        self.dashboard_battery_bar.setRange(0, 100)
        self.dashboard_battery_bar.setValue(0)
        self.dashboard_battery_bar.setTextVisible(False)
        self.dashboard_battery_bar.setFixedHeight(7)
        mouse_details.addWidget(self.dashboard_battery_bar)
        mouse_layout.addLayout(mouse_details, stretch=1)
        cards.addWidget(mouse_card, stretch=1)

        aula_card = ClickableCard()
        aula_card.setObjectName("peripheralOverviewCard")
        aula_card.clicked.connect(lambda: self.switch_page(1))
        aula_layout = QHBoxLayout(aula_card)
        aula_layout.setContentsMargins(12, 12, 14, 12)
        aula_layout.setSpacing(12)
        aula_stage = QFrame(objectName="overviewPhotoStage")
        aula_stage.setFixedSize(158, 116)
        aula_photo = QVBoxLayout(aula_stage)
        aula_photo.setContentsMargins(6, 6, 6, 6)
        aula_photo.addWidget(ProductPhotoLabel(DEVICE_ASSET_DIR / "aula-l99.png"))
        aula_layout.addWidget(aula_stage)
        aula_details = QVBoxLayout()
        aula_details.setSpacing(5)
        aula_details.addWidget(QLabel("AULA  ·  L99", objectName="productEyebrow"))
        aula_details.addWidget(QLabel("75% mechanical keyboard", objectName="cardTitle"))
        self.aula_screen_status = QLabel("LCD FEED  ·  IDLE", objectName="statusChip")
        self.aula_rgb_summary = QLabel("RGB  ·  STATIC COLOR", objectName="monoStat")
        aula_details.addWidget(self.aula_screen_status, alignment=Qt.AlignmentFlag.AlignLeft)
        aula_details.addWidget(self.aula_rgb_summary)
        self.aula_dashboard_battery_label = QLabel("BATTERY  ·  --%", objectName="monoStat")
        aula_details.addWidget(self.aula_dashboard_battery_label)
        self.aula_dashboard_battery_bar = QProgressBar(objectName="hubBatteryBar")
        self.aula_dashboard_battery_bar.setRange(0, 100)
        self.aula_dashboard_battery_bar.setValue(0)
        self.aula_dashboard_battery_bar.setTextVisible(False)
        self.aula_dashboard_battery_bar.setFixedHeight(7)
        aula_details.addWidget(self.aula_dashboard_battery_bar)
        aula_layout.addLayout(aula_details, stretch=1)
        cards.addWidget(aula_card, stretch=1)
        outer.addLayout(cards)
        return drawer

    def _sync_dashboard_summary(self) -> None:
        if hasattr(self, "effect_combo"):
            current = self.effect_combo.currentText()
            self.aula_rgb_summary.setText(f"RGB  ·  {current.upper()}")
        if self._aula_feed_error:
            self.aula_screen_status.setText("LCD FEED  ·  ERROR")
            self.aula_screen_status.setProperty("state", "warning")
        elif self.sysmon_thread and self.sysmon_thread.isRunning():
            self.aula_screen_status.setText("LCD FEED  ·  STREAMING")
            self.aula_screen_status.setProperty("state", "connected")
        else:
            self.aula_screen_status.setText("LCD FEED  ·  IDLE")
            self.aula_screen_status.setProperty("state", "searching")
        self._refresh_style(self.aula_screen_status)

    # ---- Rapoo MT760L page -------------------------------------------------
    def create_mouse_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 24)
        layout.setSpacing(14)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title_box.addWidget(QLabel("Rapoo MT760L", objectName="pageTitle"))
        self.mouse_status_badge = QLabel("Searching for mouse or receiver", objectName="statusChip")
        self.mouse_status_badge.setProperty("state", "searching")
        title_box.addWidget(self.mouse_status_badge, alignment=Qt.AlignmentFlag.AlignLeft)
        header.addLayout(title_box)
        header.addStretch(1)
        self.refresh_button = QPushButton("Refresh Live Link")
        self.refresh_button.setObjectName("secondaryAction")
        self.refresh_button.setIcon(material_symbol_icon("refresh", 18, self.tokens.primary))
        self.refresh_button.clicked.connect(self.trigger_mouse_refresh)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        hero = QFrame(objectName="heroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(16, 16, 18, 16)
        hero_layout.setSpacing(18)
        photo_stage = QFrame(objectName="photoStage")
        photo_stage.setFixedSize(222, 254)
        photo_layout = QVBoxLayout(photo_stage)
        photo_layout.setContentsMargins(8, 8, 8, 8)
        photo_layout.addWidget(ProductPhotoLabel(DEVICE_ASSET_DIR / "rapoo-mt760l.png"))
        hero_layout.addWidget(photo_stage)
        details = QVBoxLayout()
        details.setSpacing(10)
        details.addWidget(QLabel("ERGONOMIC MULTI-MODE MOUSE", objectName="sectionEyebrow"))
        details.addWidget(QLabel("Built for long sessions", objectName="heroTitle"))
        desc = QLabel("Dual scroll wheels, sculpted thumb support and three connection modes in one graphite profile.")
        desc.setObjectName("subtleLabel")
        desc.setWordWrap(True)
        details.addWidget(desc)
        features = QHBoxLayout()
        features.setSpacing(7)
        for text in ("Dual scroll wheels", "Sculpted thumb wing", "2.4G · Bluetooth · USB-C"):
            features.addWidget(QLabel(text, objectName="featureChip"))
        features.addStretch(1)
        details.addLayout(features)
        details.addStretch(1)
        details.addWidget(QLabel("HARDWARE", objectName="sectionEyebrow"))
        details.addWidget(QLabel("2.4 GHz dongle · 24ae:1870     Wired USB-C · 24ae:4500", objectName="monoStat"))
        hero_layout.addLayout(details, stretch=1)
        layout.addWidget(hero)

        telemetry = QFrame(objectName="contentCard")
        telemetry_layout = QHBoxLayout(telemetry)
        telemetry_layout.setContentsMargins(20, 17, 20, 17)
        telemetry_layout.setSpacing(24)
        battery = QVBoxLayout()
        battery.setSpacing(8)
        battery.addWidget(QLabel("LIVE BATTERY", objectName="sectionEyebrow"))
        battery_row = QHBoxLayout()
        self.battery_value = QLabel("--%", objectName="metricBig")
        self.power_state_badge = QLabel("Awaiting telemetry", objectName="statePill")
        battery_row.addWidget(self.battery_value)
        battery_row.addWidget(self.power_state_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        battery_row.addStretch(1)
        battery.addLayout(battery_row)
        self.battery_bar = QProgressBar(objectName="batteryBar")
        self.battery_bar.setRange(0, 100)
        self.battery_bar.setValue(0)
        self.battery_bar.setTextVisible(False)
        self.battery_bar.setFixedHeight(12)
        battery.addWidget(self.battery_bar)
        telemetry_layout.addLayout(battery, stretch=3)
        link_details = QVBoxLayout()
        link_details.setSpacing(6)
        link_details.addWidget(QLabel("CONNECTION & RADIO", objectName="sectionEyebrow"))
        self.link_mode_label = QLabel("Link mode · searching", objectName="subtleLabel")
        self.link_rf_label = QLabel("RF ADDRESS  ·  0x06030201", objectName="monoStat")
        self.link_time_label = QLabel("LAST POLL  ·  WAITING", objectName="monoStat")
        link_details.addWidget(self.link_mode_label)
        link_details.addWidget(self.link_rf_label)
        link_details.addWidget(self.link_time_label)
        telemetry_layout.addLayout(link_details, stretch=2)
        layout.addWidget(telemetry)

        dpi_card = QFrame(objectName="contentCard")
        dpi_layout = QVBoxLayout(dpi_card)
        dpi_layout.setContentsMargins(18, 16, 18, 16)
        dpi_layout.setSpacing(10)
        dpi_header = QHBoxLayout()
        dpi_header.addWidget(QLabel("DPI SENSITIVITY", objectName="sectionEyebrow"))
        dpi_header.addStretch(1)
        self.dpi_live_label = QLabel("LIVE STAGE · AWAITING TELEMETRY", objectName="monoStat")
        dpi_header.addWidget(self.dpi_live_label)
        dpi_layout.addLayout(dpi_header)
        grid = QGridLayout()
        grid.setHorizontalSpacing(9)
        grid.setVerticalSpacing(9)
        self.dpi_tiles: dict[int, DpiPresetTile] = {}
        for stage, dpi in DPI_STAGES:
            tile = DpiPresetTile(stage, dpi)
            tile.clicked.connect(lambda s=stage: self.select_dpi_preset(s))
            grid.addWidget(tile, (stage - 1) // 4, (stage - 1) % 4)
            self.dpi_tiles[stage] = tile
        dpi_layout.addLayout(grid)
        self.dpi_help_label = QLabel(
            "Select a preset to mark it; change the hardware with the mouse DPI switch. The active tile follows receiver telemetry.",
            objectName="subtleLabel",
        )
        self.dpi_help_label.setWordWrap(True)
        dpi_layout.addWidget(self.dpi_help_label)
        layout.addWidget(dpi_card)

        pairing = QFrame(objectName="contentCard")
        pairing_layout = QVBoxLayout(pairing)
        pairing_layout.setContentsMargins(18, 16, 18, 16)
        pairing_layout.setSpacing(10)
        pairing_layout.addWidget(QLabel("WIRELESS PAIRING WIZARD", objectName="sectionEyebrow"))
        pair_text = QLabel(
            "1 · Connect the mouse over USB-C once to read its security token.\n"
            "2 · Start pairing, then hold Left Click + Middle Wheel + Right Click for 3 seconds.\n"
            "3 · Keep the mouse in 2.4 GHz mode while the receiver listens."
        )
        pair_text.setObjectName("subtleLabel")
        pair_text.setWordWrap(True)
        pairing_layout.addWidget(pair_text)
        pair_row = QHBoxLayout()
        self.pair_button = QPushButton("Start pairing")
        self.pair_button.setObjectName("primaryAction")
        self.pair_button.setIcon(material_symbol_icon("sensors", 18, self.tokens.on_primary))
        self.pair_button.clicked.connect(self.start_pairing_wizard)
        self.pair_status_label = QLabel("Ready when Dongle 2 is connected.", objectName="subtleLabel")
        pair_row.addWidget(self.pair_button)
        pair_row.addWidget(self.pair_status_label, stretch=1)
        pairing_layout.addLayout(pair_row)
        layout.addWidget(pairing)
        layout.addStretch(1)
        return page

    def select_dpi_preset(self, stage: int) -> None:
        self._requested_dpi_stage = stage
        for number, tile in self.dpi_tiles.items():
            tile.set_requested(number == stage)
        self.dpi_help_label.setText(
            f"{stage} · {dict(DPI_STAGES)[stage]:,} DPI selected. Use the mouse DPI switch to change hardware; live telemetry confirms the active stage."
        )

    # ---- AULA L99 page -----------------------------------------------------
    def create_keyboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 24)
        layout.setSpacing(14)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title_box.addWidget(QLabel("AULA L99", objectName="pageTitle"))
        self.kbd_status_badge = QLabel("SUPPORTED  ·  05ac:024f / 0c45:800a", objectName="statusChip")
        title_box.addWidget(self.kbd_status_badge, alignment=Qt.AlignmentFlag.AlignLeft)
        header.addLayout(title_box)
        header.addStretch(1)
        self.rgb_mode_badge = QLabel("RGB · STATIC", objectName="featureChip")
        header.addWidget(self.rgb_mode_badge)
        layout.addLayout(header)

        battery_card = QFrame(objectName="contentCard")
        battery_layout = QHBoxLayout(battery_card)
        battery_layout.setContentsMargins(18, 14, 18, 14)
        battery_layout.setSpacing(18)
        battery_details = QVBoxLayout()
        battery_details.setSpacing(5)
        battery_details.addWidget(QLabel("LIVE BATTERY", objectName="sectionEyebrow"))
        self.aula_battery_value_label = QLabel("--%", objectName="metricBig")
        battery_details.addWidget(self.aula_battery_value_label)
        self.aula_battery_bar = QProgressBar(objectName="batteryBar")
        self.aula_battery_bar.setRange(0, 100)
        self.aula_battery_bar.setValue(0)
        self.aula_battery_bar.setTextVisible(False)
        self.aula_battery_bar.setFixedHeight(12)
        battery_details.addWidget(self.aula_battery_bar)
        self.aula_battery_note = QLabel("Waiting for live battery reading…", objectName="subtleLabel")
        self.aula_battery_note.setWordWrap(True)
        battery_details.addWidget(self.aula_battery_note)
        battery_layout.addLayout(battery_details, stretch=2)

        connection_details = QVBoxLayout()
        connection_details.setSpacing(7)
        self.aula_connection_badge = QLabel("AULA L99 · SEARCHING", objectName="statusChip")
        self.aula_connection_badge.setProperty("state", "searching")
        connection_details.addWidget(self.aula_connection_badge, alignment=Qt.AlignmentFlag.AlignLeft)
        self.aula_connection_detail = QLabel("Waiting for USB or 2.4 GHz receiver", objectName="monoStat")
        self.aula_connection_detail.setWordWrap(True)
        connection_details.addWidget(self.aula_connection_detail)
        self.aula_last_poll_label = QLabel("LAST POLL  ·  --", objectName="monoStat")
        connection_details.addWidget(self.aula_last_poll_label)
        connection_details.addStretch(1)
        self.aula_refresh_button = QPushButton("Refresh Link")
        self.aula_refresh_button.setObjectName("secondaryAction")
        self.aula_refresh_button.setIcon(material_symbol_icon("refresh", 18, self.tokens.text))
        self.aula_refresh_button.clicked.connect(self.refresh_aula_link)
        connection_details.addWidget(self.aula_refresh_button, alignment=Qt.AlignmentFlag.AlignLeft)
        battery_layout.addLayout(connection_details, stretch=2)
        layout.addWidget(battery_card)

        hero = QFrame(objectName="heroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(16, 16, 18, 16)
        hero_layout.setSpacing(18)
        photo_stage = QFrame(objectName="photoStage")
        photo_stage.setMinimumWidth(365)
        photo_stage.setFixedHeight(202)
        photo_layout = QVBoxLayout(photo_stage)
        photo_layout.setContentsMargins(8, 8, 8, 8)
        photo_layout.addWidget(ProductPhotoLabel(DEVICE_ASSET_DIR / "aula-l99.png"))
        hero_layout.addWidget(photo_stage, stretch=1)
        details = QVBoxLayout()
        details.setSpacing(9)
        details.addWidget(QLabel("75% CUSTOM MECHANICAL KEYBOARD", objectName="sectionEyebrow"))
        details.addWidget(QLabel("L99 smart screen", objectName="heroTitle"))
        description = QLabel(
            "Compact 75% layout with RGB lighting, a 3.98-inch vertical color IPS display, and a touch control strip."
        )
        description.setObjectName("subtleLabel")
        description.setWordWrap(True)
        details.addWidget(description)
        details.addWidget(QLabel("2.4 GHz dongle · 05ac:024f     Wired USB · 0c45:800a", objectName="monoStat"))
        details.addStretch(1)
        hero_layout.addLayout(details, stretch=1)
        layout.addWidget(hero)

        rgb_card = QFrame(objectName="contentCard")
        rgb_layout = QVBoxLayout(rgb_card)
        rgb_layout.setContentsMargins(18, 16, 18, 16)
        rgb_layout.setSpacing(12)
        rgb_layout.addWidget(QLabel("RGB LIGHTING", objectName="sectionEyebrow"))
        effect_row = QHBoxLayout()
        effect_row.setSpacing(10)
        self.effect_combo = QComboBox()
        self.effect_combo.setObjectName("effectCombo")
        for effect_id, label in AULA_EFFECTS:
            self.effect_combo.addItem(f"{label}  ·  {effect_id}", effect_id)
        self.effect_combo.currentTextChanged.connect(self._sync_dashboard_summary)
        self.effect_combo.currentTextChanged.connect(self._sync_rgb_badge)
        effect_row.addWidget(self.effect_combo, stretch=2)
        self.direction_button = QPushButton("Direction · Normal")
        self.direction_button.setObjectName("secondaryAction")
        self.direction_button.setCheckable(True)
        self.direction_button.toggled.connect(self._sync_direction_label)
        effect_row.addWidget(self.direction_button)
        self.color_button = QPushButton("Pick RGB color")
        self.color_button.setObjectName("secondaryAction")
        self.color_button.clicked.connect(self.choose_color)
        effect_row.addWidget(self.color_button)
        self.color_swatch = QFrame(objectName="colorSwatch")
        self.color_swatch.setFixedSize(34, 34)
        effect_row.addWidget(self.color_swatch)
        rgb_layout.addLayout(effect_row)

        slider_row = QHBoxLayout()
        self.brightness_slider = self._make_labeled_slider("BRIGHTNESS", 1, 5, 5)
        self.speed_slider = self._make_labeled_slider("SPEED", 1, 5, 3)
        slider_row.addWidget(self.brightness_slider[0], stretch=1)
        slider_row.addWidget(self.speed_slider[0], stretch=1)
        rgb_layout.addLayout(slider_row)
        action_row = QHBoxLayout()
        self.apply_rgb_button = QPushButton("Apply RGB effect")
        self.apply_rgb_button.setObjectName("primaryAction")
        self.apply_rgb_button.setIcon(material_symbol_icon("palette", 18, self.tokens.on_primary))
        self.apply_rgb_button.clicked.connect(self.apply_aula_rgb)
        self.rgb_status_label = QLabel("Choose an effect and apply it to the keyboard.", objectName="subtleLabel")
        action_row.addWidget(self.apply_rgb_button)
        action_row.addWidget(self.rgb_status_label, stretch=1)
        rgb_layout.addLayout(action_row)
        layout.addWidget(rgb_card)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(12)
        settings_card = QFrame(objectName="contentCard")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setSpacing(10)
        settings_layout.addWidget(QLabel("KEYBOARD RESPONSE & SLEEP", objectName="sectionEyebrow"))
        response_header = QHBoxLayout()
        response_header.addWidget(QLabel("Key response time", objectName="subtleLabel"))
        response_header.addStretch(1)
        self.response_level_label = QLabel("LEVEL 3  ·  ~8 ms  ·  BALANCED", objectName="monoStat")
        response_header.addWidget(self.response_level_label)
        settings_layout.addLayout(response_header)
        self.response_level_slider = QSlider(Qt.Orientation.Horizontal)
        self.response_level_slider.setRange(1, 5)
        self.response_level_slider.setSingleStep(1)
        self.response_level_slider.setPageStep(1)
        self.response_level_slider.setValue(3)
        self.response_level_slider.valueChanged.connect(self._sync_response_level_label)
        settings_layout.addWidget(self.response_level_slider)
        sleep_row = QHBoxLayout()
        sleep_row.addWidget(QLabel("Wireless sleep", objectName="subtleLabel"))
        self.sleep_timeout_combo = QComboBox()
        for label, value in (("Never Sleep", 0), ("1 Minute", 1), ("5 Minutes", 2), ("30 Minutes", 3)):
            self.sleep_timeout_combo.addItem(label, value)
        sleep_row.addWidget(self.sleep_timeout_combo, stretch=1)
        settings_layout.addLayout(sleep_row)
        settings_action = QHBoxLayout()
        self.apply_settings_button = QPushButton("Apply Settings")
        self.apply_settings_button.setObjectName("primaryAction")
        self.apply_settings_button.clicked.connect(self.apply_aula_settings)
        self.settings_status_label = QLabel("Choose a response level and sleep timeout.", objectName="subtleLabel")
        self.settings_status_label.setWordWrap(True)
        settings_action.addWidget(self.apply_settings_button)
        settings_action.addWidget(self.settings_status_label, stretch=1)
        settings_layout.addLayout(settings_action)
        settings_row.addWidget(settings_card, stretch=3)

        gaming_card = QFrame(objectName="contentCard")
        gaming_layout = QVBoxLayout(gaming_card)
        gaming_layout.setContentsMargins(16, 14, 16, 14)
        gaming_layout.setSpacing(10)
        gaming_layout.addWidget(QLabel("GAMING SHORTCUTS", objectName="sectionEyebrow"))
        gaming_layout.addWidget(QLabel("Windows-key lock", objectName="cardTitle"))
        self.win_lock_button = QPushButton("Win Key · State unknown")
        self.win_lock_button.setObjectName("secondaryAction")
        self.win_lock_button.setCheckable(True)
        self.win_lock_button.setMinimumHeight(42)
        self.win_lock_button.clicked.connect(self.set_aula_win_lock)
        gaming_layout.addWidget(self.win_lock_button, alignment=Qt.AlignmentFlag.AlignLeft)
        gaming_hint = QLabel(
            "Lock state is not reported by the keyboard. This button sends the selected state through the 2.4 GHz receiver.",
            objectName="subtleLabel",
        )
        gaming_hint.setWordWrap(True)
        gaming_layout.addWidget(gaming_hint)
        self.win_lock_status_label = QLabel("Waiting for a lock command.", objectName="subtleLabel")
        self.win_lock_status_label.setWordWrap(True)
        gaming_layout.addWidget(self.win_lock_status_label)
        gaming_layout.addStretch(1)
        settings_row.addWidget(gaming_card, stretch=2)
        layout.addLayout(settings_row)

        screen_card = QFrame(objectName="contentCard")
        screen_layout = QVBoxLayout(screen_card)
        screen_layout.setContentsMargins(18, 16, 18, 16)
        screen_layout.setSpacing(11)
        screen_header = QHBoxLayout()
        screen_header.addWidget(QLabel("SMART SCREEN & RTC", objectName="sectionEyebrow"))
        screen_header.addStretch(1)
        self.screen_feed_badge = QLabel("LCD FEED  ·  IDLE", objectName="statusChip")
        self.screen_feed_badge.setProperty("state", "searching")
        screen_header.addWidget(self.screen_feed_badge)
        screen_layout.addLayout(screen_header)
        screen_description = QLabel(
            "Stream host CPU/GPU readings to the keyboard display or send a one-time clock and status update."
        )
        screen_description.setObjectName("subtleLabel")
        screen_description.setWordWrap(True)
        screen_layout.addWidget(screen_description)
        metrics = QHBoxLayout()
        self.cpu_stat = QLabel("CPU  ·  --%  ·  --°C", objectName="metricTile")
        self.gpu_stat = QLabel("GPU  ·  --%  ·  --°C", objectName="metricTile")
        metrics.addWidget(self.cpu_stat)
        metrics.addWidget(self.gpu_stat)
        metrics.addStretch(1)
        screen_layout.addLayout(metrics)
        screen_actions = QHBoxLayout()
        self.screen_feed_button = QPushButton("Start real-time screen feed")
        self.screen_feed_button.setObjectName("primaryAction")
        self.screen_feed_button.setIcon(material_symbol_icon("monitor_heart", 18, self.tokens.on_primary))
        self.screen_feed_button.clicked.connect(self.toggle_aula_sysmon)
        self.sync_rtc_button = QPushButton("Sync clock & send stats once")
        self.sync_rtc_button.setObjectName("secondaryAction")
        self.sync_rtc_button.clicked.connect(self.sync_aula_rtc)
        self.screen_action_status = QLabel("Keyboard LCD controls ready.", objectName="subtleLabel")
        screen_actions.addWidget(self.screen_feed_button)
        screen_actions.addWidget(self.sync_rtc_button)
        screen_layout.addLayout(screen_actions)
        screen_layout.addWidget(self.screen_action_status)
        layout.addWidget(screen_card)
        layout.addStretch(1)
        return page

    def _make_labeled_slider(self, label: str, minimum: int, maximum: int, value: int) -> tuple[QFrame, QSlider]:
        container = QFrame(objectName="sliderPanel")
        column = QVBoxLayout(container)
        column.setContentsMargins(10, 8, 10, 8)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel(label, objectName="sectionEyebrow"))
        title_row.addStretch(1)
        value_label = QLabel(str(value), objectName="monoStat")
        title_row.addWidget(value_label)
        column.addLayout(title_row)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.valueChanged.connect(value_label.setNum)
        column.addWidget(slider)
        return container, slider

    def _sync_rgb_badge(self, _text: str = "") -> None:
        if hasattr(self, "effect_combo"):
            name = self.effect_combo.currentText().split("  ·  ", 1)[0].upper()
            self.rgb_mode_badge.setText(f"RGB · {name}")

    def _sync_direction_label(self, inverted: bool) -> None:
        self.direction_button.setText(
            "Direction · Inverted" if inverted else "Direction · Normal"
        )

    def _sync_response_level_label(self, level: int) -> None:
        delays = {1: "~2 ms · FASTEST", 2: "~5 ms", 3: "~8 ms · BALANCED", 4: "~12 ms", 5: "~16 ms · STABLE"}
        self.response_level_label.setText(f"LEVEL {level}  ·  {delays.get(level, '')}")

    # ---- receiver recovery -------------------------------------------------
    def create_recovery_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 24)
        layout.setSpacing(14)
        layout.addWidget(QLabel("Rapoo Receiver Dongle 1", objectName="pageTitle"))
        hero = QFrame(objectName="heroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.setSpacing(11)
        hero_layout.addWidget(QLabel("TELINK TLSR8355 · BOOTLOADER RECOVERY", objectName="sectionEyebrow"))
        hero_layout.addWidget(QLabel("Diagnostic guide", objectName="heroTitle"))
        details = QLabel(
            "Dongle 1 (24ae:3040) is enumerating in ROM bootloader mode. The receiver stores an OTA entry flag in non-volatile flash.\n\n"
            "1 · Connect the receiver and Rapoo mouse to a Windows PC.\n"
            "2 · Open A HUB Office → Settings → Receiver Pairing (对码).\n"
            "3 · Complete the vendor pairing flow to clear the bootloader flag.\n"
            "4 · Reconnect the receiver here; normal mode should enumerate as 24ae:1870.\n\n"
            "The current Linux diagnostic can detect 24ae:3040. It does not write receiver firmware."
        )
        details.setObjectName("subtleLabel")
        details.setWordWrap(True)
        hero_layout.addWidget(details)
        action_row = QHBoxLayout()
        self.scan_dongle_button = QPushButton("Scan USB devices")
        self.scan_dongle_button.setObjectName("primaryAction")
        self.scan_dongle_button.setIcon(material_symbol_icon("usb", 18, self.tokens.on_primary))
        self.scan_dongle_button.clicked.connect(self.scan_dongle1)
        self.dongle_scan_status = QLabel("Scan to check for 24ae:3040.", objectName="subtleLabel")
        action_row.addWidget(self.scan_dongle_button)
        action_row.addWidget(self.dongle_scan_status, stretch=1)
        hero_layout.addLayout(action_row)
        layout.addWidget(hero)
        layout.addStretch(1)
        return page

    # ---- live Rapoo status and DPI ----------------------------------------
    def start_telemetry_worker(self) -> None:
        self.telemetry_worker = RapooTelemetryThread(self)
        self.telemetry_worker.telemetry_received.connect(self.on_rapoo_telemetry)
        self.telemetry_worker.device_status_changed.connect(self.on_rapoo_status_change)
        self.telemetry_worker.start()

    def load_initial_cache(self) -> None:
        try:
            if CACHE_FILE.exists():
                payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                self.on_rapoo_telemetry(payload)
        except (OSError, ValueError, TypeError):
            pass

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def on_rapoo_status_change(self, mode: str, path: str) -> None:
        labels = {
            "wireless": ("RAPOO  ·  ONLINE", "CONNECTED  ·  2.4 GHz", "2.4 GHz wireless receiver", "wireless"),
            "wired": ("RAPOO  ·  WIRED", "CONNECTED  ·  USB-C", "USB-C wired link", "wired"),
            "bootloader": ("RAPOO RECEIVER  ·  DFU", "RECEIVER  ·  RECOVERY MODE", "Dongle 1 bootloader mode", "bootloader"),
        }
        chip_text, card_text, link_text, visual_state = labels.get(
            mode, ("RAPOO  ·  OFFLINE", "NOT CONNECTED", "No Rapoo HID endpoint detected", "disconnected")
        )
        self.top_mouse_chip.setText(chip_text)
        self.top_mouse_chip.setProperty("state", visual_state)
        self.dashboard_mouse_status.setText(card_text)
        self.dashboard_mouse_status.setProperty("state", visual_state)
        self.mouse_status_badge.setText(card_text)
        self.mouse_status_badge.setProperty("state", visual_state)
        self.link_mode_label.setText(f"LINK MODE  ·  {link_text}" + (f"  ·  {path}" if path else ""))
        self._refresh_style(self.top_mouse_chip)
        self._refresh_style(self.dashboard_mouse_status)
        self._refresh_style(self.mouse_status_badge)

    def on_rapoo_telemetry(self, payload: dict) -> None:
        try:
            battery = max(0, min(100, int(payload.get("battery", payload.get("battery_percent", 0)))))
        except (ValueError, TypeError):
            battery = 0
        self.battery_value.setText(f"{battery}%")
        self.dashboard_battery_label.setText(f"BATTERY  ·  {battery}%")
        tone = "good" if battery >= 60 else "medium" if battery >= 25 else "low"
        self.battery_bar.setProperty("tone", tone)
        self._refresh_style(self.battery_bar)
        self._animate_progress(self.battery_bar, battery)
        self._animate_progress(self.dashboard_battery_bar, battery)

        power = str(payload.get("power_state", "Online / Active"))
        self.power_state_badge.setText(power)
        self.power_state_badge.setProperty("state", "charging" if "charg" in power.lower() else "normal")
        self._refresh_style(self.power_state_badge)
        dpi_value = int(payload.get("dpi_value") or 0)
        stage = int(payload.get("dpi_stage") or DPI_MAP.get(dpi_value, 0))
        self.dashboard_dpi_label.setText(f"DPI  ·  {dpi_value:,}" if dpi_value else "DPI  ·  --")
        self.dpi_live_label.setText(f"LIVE STAGE  ·  {stage:02d} / 07" if stage else "LIVE STAGE  ·  UNKNOWN")
        for current_stage, tile in self.dpi_tiles.items():
            tile.set_active(current_stage == stage and stage > 0)
        if stage:
            self._requested_dpi_stage = None
            for tile in self.dpi_tiles.values():
                tile.set_requested(False)
            self.dpi_help_label.setText(f"Receiver reports stage {stage} · {dpi_value:,} DPI. Select a preset for a reference; use the mouse DPI switch to change hardware.")
        rf_address = payload.get("mouse_rf_id") or payload.get("rf_address")
        if rf_address:
            self.link_rf_label.setText(f"RF ADDRESS  ·  {rf_address}")
        timestamp = payload.get("timestamp") or dt.datetime.now().strftime("%H:%M:%S")
        self.link_time_label.setText(f"LAST POLL  ·  {timestamp}")

    def _animate_progress(self, bar: QProgressBar, value: int) -> None:
        animation = self._bar_animations.get(bar)
        if animation is None:
            animation = QPropertyAnimation(bar, b"value", self)
            self._bar_animations[bar] = animation
        else:
            animation.stop()
        animation.setDuration(620)
        animation.setStartValue(bar.value())
        animation.setEndValue(max(bar.minimum(), min(bar.maximum(), int(value))))
        animation.setEasingCurve(self._spring_curve())
        animation.start()

    def trigger_mouse_refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Refreshing link…")
        old_worker = self.telemetry_worker
        if old_worker:
            old_worker.stop()
            old_worker.wait(1200)
            old_worker.deleteLater()
        self.start_telemetry_worker()
        self.load_initial_cache()
        QTimer.singleShot(1100, self._finish_mouse_refresh)

    def _finish_mouse_refresh(self) -> None:
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Refresh Live Link")

    # ---- Rapoo pairing -----------------------------------------------------
    def start_pairing_wizard(self) -> None:
        if self.pairing_worker and self.pairing_worker.isRunning():
            return
        self.pair_button.setEnabled(False)
        self.pair_status_label.setText("Preparing receiver and mouse token…")
        self.pairing_worker = RapooPairingWorker(self)
        self.pairing_worker.sig_status.connect(self.pair_status_label.setText)
        self.pairing_worker.sig_finished.connect(self.on_pairing_finished)
        self.pairing_worker.start()

    def on_pairing_finished(self, success: bool, message: str) -> None:
        self.pair_button.setEnabled(True)
        self.pair_status_label.setText(message)
        if success:
            self.load_initial_cache()
            self.on_rapoo_status_change("wireless", "")

    # ---- AULA RGB and LCD controls ----------------------------------------
    def start_aula_telemetry_worker(self) -> None:
        if self.aula_telemetry_worker and self.aula_telemetry_worker.isRunning():
            return
        worker = AulaTelemetryThread(interval=8.0, parent=self)
        worker.battery_updated.connect(self.on_aula_battery_updated)
        worker.device_status_changed.connect(self.on_aula_device_status)
        worker.battery_unavailable.connect(self.on_aula_battery_unavailable)
        worker.poll_finished.connect(self.on_aula_poll_finished)
        self.aula_telemetry_worker = worker
        worker.start()

    def load_aula_cache(self) -> None:
        try:
            payload = json.loads(AULA_CACHE_FILE.read_text(encoding="utf-8"))
            battery = max(0, min(100, int(payload["battery"])))
        except (OSError, ValueError, TypeError, KeyError):
            return
        self._show_aula_battery(battery)
        timestamp = str(payload.get("timestamp", ""))
        self.aula_last_poll_label.setText(f"LAST POLL  ·  CACHED {timestamp[-8:] or '--'}")
        self.aula_battery_note.setText("Cached reading · waiting for a live battery poll.")
        mode = str(payload.get("mode", "disconnected"))
        path = str(payload.get("path", ""))
        if mode in ("wireless", "wired"):
            self.on_aula_device_status(mode, path)

    def refresh_aula_link(self) -> None:
        if not self.aula_telemetry_worker or not self.aula_telemetry_worker.isRunning():
            self.start_aula_telemetry_worker()
        self._aula_refresh_pending = True
        self.aula_refresh_button.setEnabled(False)
        self.aula_refresh_button.setText("Refreshing…")
        self.aula_battery_note.setText("Requesting a fresh keyboard battery reading…")
        if self.aula_telemetry_worker:
            self.aula_telemetry_worker.request_poll()

    def on_aula_poll_finished(self) -> None:
        if not self._aula_refresh_pending:
            return
        self._aula_refresh_pending = False
        self.aula_refresh_button.setEnabled(True)
        self.aula_refresh_button.setText("Refresh Link")

    def on_aula_device_status(self, mode: str, path: str) -> None:
        self.aula_connection_mode = mode
        self.aula_connection_path = path
        labels = {
            "wireless": (
                "AULA L99 · ONLINE", "2.4 GHz Wireless · Dongle 05ac:024f", "wireless"
            ),
            "wired": (
                "AULA L99 · WIRED", "Wired USB · 0c45:800a", "wired"
            ),
            "disconnected": (
                "AULA L99 · OFFLINE", "No AULA L99 HID interface found", "disconnected"
            ),
        }
        top_text, detail, state = labels.get(mode, labels["disconnected"])
        self.top_aula_chip.setText(top_text)
        self.top_aula_chip.setProperty("state", state)
        self.aula_connection_badge.setText(top_text)
        self.aula_connection_badge.setProperty("state", state)
        self.aula_connection_detail.setText(f"{detail}  ·  {path}" if path else detail)
        self._refresh_style(self.top_aula_chip)
        self._refresh_style(self.aula_connection_badge)

    def on_aula_battery_updated(self, battery: int) -> None:
        battery = max(0, min(100, int(battery)))
        self._show_aula_battery(battery)
        timestamp = dt.datetime.now()
        stamp = timestamp.strftime("%H:%M:%S")
        self.aula_last_poll_label.setText(f"LAST POLL  ·  {stamp}")
        self.aula_battery_note.setText("Live battery reading received from the keyboard.")
        try:
            AULA_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            AULA_CACHE_FILE.write_text(
                json.dumps({
                    "battery": battery,
                    "mode": self.aula_connection_mode,
                    "path": self.aula_connection_path,
                    "timestamp": timestamp.isoformat(timespec="seconds"),
                }),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _show_aula_battery(self, battery: int) -> None:
        self.aula_battery_value = battery
        self.aula_battery_value_label.setText(f"{battery}%")
        self.aula_dashboard_battery_label.setText(f"BATTERY  ·  {battery}%")
        tone = "good" if battery >= 60 else "medium" if battery >= 25 else "low"
        self.aula_battery_bar.setProperty("tone", tone)
        self._refresh_style(self.aula_battery_bar)
        self._animate_progress(self.aula_battery_bar, battery)
        self._animate_progress(self.aula_dashboard_battery_bar, battery)

    def on_aula_battery_unavailable(self, message: str) -> None:
        self.aula_battery_note.setText(message)
        if self.aula_battery_value is None:
            self.aula_battery_value_label.setText("--%")

    def choose_color(self) -> None:
        initial = QColor(f"#{self.current_color}")
        selected = QColorDialog.getColor(initial, self, "Choose keyboard lighting color")
        if selected.isValid():
            self.current_color = selected.name(QColor.NameFormat.HexRgb)[1:].upper()
            self.color_button.setText(f"Color · #{self.current_color}")
            self._style_color_swatch()

    def apply_aula_rgb(self) -> None:
        effect_id = int(str(self.effect_combo.currentData()), 0)
        rgb = tuple(int(self.current_color[offset:offset + 2], 16) for offset in (0, 2, 4))
        values = {
            "mode": effect_id,
            "rgb": rgb,
            "direction": int(self.direction_button.isChecked()),
            "brightness": self.brightness_slider[1].value(),
            "speed": self.speed_slider[1].value(),
        }
        self.rgb_status_label.setText("Sending lighting effect to AULA L99…")
        self._start_aula_command("lighting", values)

    def apply_aula_settings(self) -> None:
        values = {
            "sleep_level": int(self.sleep_timeout_combo.currentData()),
            "response_level": self.response_level_slider.value(),
        }
        self.settings_status_label.setText("Applying sleep and response settings…")
        self._start_aula_command("settings", values)

    def set_aula_win_lock(self, locked: bool) -> None:
        self._pending_win_lock = bool(locked)
        self.win_lock_status_label.setText(
            f"Sending Windows-key {'lock' if locked else 'unlock'} command…"
        )
        self._start_aula_command("win_lock", {"locked": bool(locked)})

    def _start_aula_command(self, command: str, values: dict) -> None:
        if self.aula_command_worker and self.aula_command_worker.isRunning():
            return
        self._set_aula_command_controls_enabled(False)
        worker = AulaCommandThread(command, values, self)
        worker.command_finished.connect(self.on_aula_command_finished)
        worker.rtc_metrics.connect(self.on_aula_rtc_metrics)
        worker.finished.connect(self._release_aula_command_worker)
        worker.finished.connect(worker.deleteLater)
        self.aula_command_worker = worker
        worker.start()

    def _set_aula_command_controls_enabled(self, enabled: bool) -> None:
        for button in (
            self.apply_rgb_button,
            self.apply_settings_button,
            self.win_lock_button,
            self.sync_rtc_button,
        ):
            button.setEnabled(enabled)

    def _release_aula_command_worker(self) -> None:
        worker = self.sender()
        if worker is self.aula_command_worker:
            self.aula_command_worker = None
            self._set_aula_command_controls_enabled(True)

    def on_aula_command_finished(self, command: str, success: bool, message: str) -> None:
        if command == "lighting":
            self.rgb_status_label.setText(message)
            if success:
                self._sync_rgb_badge()
                self._sync_dashboard_summary()
        elif command == "settings":
            self.settings_status_label.setText(message)
        elif command == "win_lock":
            if success:
                self._win_lock_confirmed = self._pending_win_lock
                self.win_lock_button.blockSignals(True)
                self.win_lock_button.setChecked(bool(self._win_lock_confirmed))
                self.win_lock_button.setText(
                    f"Win Key · {'Locked' if self._win_lock_confirmed else 'Unlocked'}"
                )
                self.win_lock_button.blockSignals(False)
            else:
                self.win_lock_button.blockSignals(True)
                self.win_lock_button.setChecked(bool(self._win_lock_confirmed))
                self.win_lock_button.setText(
                    f"Win Key · {'Locked' if self._win_lock_confirmed else 'Unlocked'}"
                    if self._win_lock_confirmed is not None else "Win Key · State unknown"
                )
                self.win_lock_button.blockSignals(False)
            self.win_lock_status_label.setText(message)
        elif command == "rtc":
            self.screen_action_status.setText(message)

    def on_aula_rtc_metrics(self, cpu_load: int, cpu_temp: int, gpu_load: int, gpu_temp: int) -> None:
        self.last_aula_metrics = (cpu_load, cpu_temp, gpu_load, gpu_temp)
        self.cpu_stat.setText(f"CPU  ·  {cpu_load}%  ·  {cpu_temp}°C")
        self.gpu_stat.setText(f"GPU  ·  {gpu_load}%  ·  {gpu_temp}°C")

    def toggle_aula_sysmon(self) -> None:
        if self.sysmon_thread and self.sysmon_thread.isRunning():
            self.sysmon_thread.stop()
            self.sysmon_thread.wait(1800)
            self.sysmon_thread.deleteLater()
            self.sysmon_thread = None
            self._aula_feed_error = None
            self.screen_feed_button.setText("Start real-time screen feed")
            self.screen_feed_badge.setText("LCD FEED  ·  IDLE")
            self.screen_feed_badge.setProperty("state", "searching")
            self.screen_action_status.setText("Screen feed stopped.")
        else:
            self._aula_feed_error = None
            self.sysmon_thread = AulaSystemMonitorThread(interval=2.5, parent=self)
            self.sysmon_thread.stats_updated.connect(self.on_aula_stats_updated)
            self.sysmon_thread.start()
            self.screen_feed_button.setText("Stop real-time screen feed")
            self.screen_feed_badge.setText("LCD FEED  ·  STARTING")
            self.screen_feed_badge.setProperty("state", "connected")
            self.screen_action_status.setText("Sampling host metrics and updating the L99 display.")
        self._refresh_style(self.screen_feed_badge)
        self._sync_dashboard_summary()

    def on_aula_stats_updated(
        self, cpu_load: int, cpu_temp: int, gpu_load: int, gpu_temp: int, status: str
    ) -> None:
        self.last_aula_metrics = (cpu_load, cpu_temp, gpu_load, gpu_temp)
        self.cpu_stat.setText(f"CPU  ·  {cpu_load}%  ·  {cpu_temp}°C")
        self.gpu_stat.setText(f"GPU  ·  {gpu_load}%  ·  {gpu_temp}°C")
        self.screen_action_status.setText(status)
        if status.startswith(("Feed error", "Feed unavailable")):
            self._aula_feed_error = status
            self.screen_feed_badge.setText("LCD FEED  ·  ERROR")
            self.screen_feed_badge.setProperty("state", "warning")
            if status.startswith("Feed unavailable"):
                self.screen_feed_button.setText("Start real-time screen feed")
        elif self.sysmon_thread and self.sysmon_thread.isRunning():
            self._aula_feed_error = None
            self.screen_feed_badge.setText("LCD FEED  ·  STREAMING")
            self.screen_feed_badge.setProperty("state", "connected")
        self._refresh_style(self.screen_feed_badge)
        self._sync_dashboard_summary()

    def sync_aula_rtc(self) -> None:
        self.screen_action_status.setText("Sampling host status and sending one RTC update…")
        self._start_aula_command("rtc", {})

    # ---- asynchronous process helpers ------------------------------------
    def _start_tool_process(
        self,
        key: str,
        program: str,
        arguments: list[str],
        callback: Callable[[int, str, str], None],
        *,
        working_directory: Path = APP_DIR,
        tool_path: bool = True,
    ) -> None:
        previous = self.action_processes.get(key)
        if previous and previous.state() != QProcess.ProcessState.NotRunning:
            return
        process = QProcess(self)
        process.setWorkingDirectory(str(working_directory))
        environment = QProcessEnvironment.systemEnvironment()
        if tool_path:
            existing = environment.value("PYTHONPATH", "")
            environment.insert("PYTHONPATH", str(TOOLS_DIR) + (os.pathsep + existing if existing else ""))
        process.setProcessEnvironment(environment)
        self.action_processes[key] = process
        self.process_callbacks[key] = callback
        process.finished.connect(lambda code, _status, name=key: self._process_finished(name, code))
        process.errorOccurred.connect(lambda error, name=key: self._process_error(name, error))
        process.start(program, arguments)

    def _process_finished(self, key: str, exit_code: int) -> None:
        process = self.action_processes.pop(key, None)
        callback = self.process_callbacks.pop(key, None)
        if process is None:
            return
        stdout = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
        stderr = bytes(process.readAllStandardError()).decode("utf-8", "replace")
        if callback:
            callback(exit_code, stdout, stderr)
        process.deleteLater()

    def _process_error(self, key: str, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart:
            return
        process = self.action_processes.pop(key, None)
        callback = self.process_callbacks.pop(key, None)
        message = process.errorString() if process else "Could not start command."
        if callback:
            callback(-1, "", message)
        if process:
            process.deleteLater()

    def scan_dongle1(self) -> None:
        self.scan_dongle_button.setEnabled(False)
        self.dongle_scan_status.setText("Scanning USB device list…")
        self._start_tool_process(
            "scan", "lsusb", [], self._finish_dongle_scan,
            working_directory=APP_DIR, tool_path=False,
        )

    def _finish_dongle_scan(self, exit_code: int, stdout: str, stderr: str) -> None:
        self.scan_dongle_button.setEnabled(True)
        if exit_code != 0:
            self.dongle_scan_status.setText(stderr.strip() or "Could not run lsusb.")
        elif "24ae:3040" in stdout.lower():
            self.dongle_scan_status.setText("Dongle 1 detected · 24ae:3040 bootloader mode")
        else:
            self.dongle_scan_status.setText("No 24ae:3040 bootloader device found.")

    # ---- Caelestia theme loading and cleanup ------------------------------
    def apply_styles(self) -> None:
        t = self.tokens
        css = f"""
            QMainWindow {{ background-color: {t.background}; color: {t.text}; }}
            QWidget {{ color: {t.text}; font-family: 'Rubik', 'Noto Sans', sans-serif; font-size: 13px; }}
            QFrame#dashboardSurface {{ background: {t.surface}; border: 1px solid {t.outline_variant}; border-radius: 28px; }}
            QWidget#shellStatusBar, QFrame#dashboardDrawer, QFrame#deviceNavigation {{ background: transparent; border: none; }}
            QLabel#brandTitle {{ color: {t.primary}; font-size: 18px; font-weight: 800; letter-spacing: 1.1px; }}
            QLabel#brandSubtitle {{ color: {t.subtext0}; font-size: 9px; font-weight: 700; letter-spacing: 1.05px; }}
            QPushButton#dynamicIsland {{ background: {t.primary}; color: {t.on_primary}; border: 1px solid {t.primary}; border-radius: 23px; min-height: 44px; padding: 0 18px; font-weight: 700; letter-spacing: 0.25px; }}
            QPushButton#dynamicIsland:hover {{ background: {t.primary_container}; border-color: {t.primary_container}; }}
            QPushButton#dynamicIsland:checked {{ background: {t.primary}; color: {t.on_primary}; }}
            QLabel#statusChip, QLabel#themePill {{ background: {t.secondary_container}; color: {t.text}; border: 1px solid {t.outline_variant}; border-radius: 16px; min-height: 24px; padding: 3px 10px; font-size: 9px; font-weight: 700; letter-spacing: 0.35px; }}
            QLabel#statusChip[state="wireless"], QLabel#statusChip[state="wired"], QLabel#statusChip[state="connected"] {{ background: {t.primary_container}; color: {t.on_primary_container}; border-color: {t.primary_container}; }}
            QLabel#statusChip[state="bootloader"], QLabel#statusChip[state="warning"] {{ background: {t.secondary}; color: {t.on_primary}; }}
            QLabel#sectionEyebrow, QLabel#productEyebrow {{ color: {t.primary}; font-size: 9px; font-weight: 800; letter-spacing: 0.9px; }}
            QLabel#subtleLabel {{ color: {t.subtext0}; font-size: 11px; }}
            QLabel#cardTitle {{ color: {t.text}; font-size: 14px; font-weight: 700; }}
            QLabel#pageTitle {{ color: {t.text}; font-size: 23px; font-weight: 700; letter-spacing: -0.35px; }}
            QLabel#heroTitle {{ color: {t.text}; font-size: 21px; font-weight: 700; letter-spacing: -0.4px; }}
            QLabel#monoStat, QLabel#monoQuiet, QLabel#tileStageLabel, QLabel#tileStateLabel {{ color: {t.subtext0}; font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace; font-size: 9px; font-weight: 600; letter-spacing: 0.15px; }}
            QLabel#monoQuiet {{ font-size: 10px; }}
            QFrame#peripheralOverviewCard, QFrame#contentCard {{ background: {t.surface_container}; border: 1px solid {t.outline_variant}; border-radius: 22px; }}
            QFrame#peripheralOverviewCard:hover {{ background: {t.surface_high}; border-color: {t.primary}; }}
            QFrame#heroCard {{ background: {t.surface_high}; border: 1px solid {t.outline_variant}; border-radius: 24px; }}
            QFrame#photoStage, QFrame#overviewPhotoStage {{ background: {t.surface_lowest}; border: 1px solid {t.outline_variant}; border-radius: 18px; }}
            QLabel#productPhoto {{ background: transparent; border: none; color: {t.subtext0}; }}
            QLabel#featureChip {{ background: {t.secondary_container}; color: {t.text}; border: 1px solid {t.outline_variant}; border-radius: 15px; min-height: 25px; padding: 3px 10px; font-size: 10px; font-weight: 600; }}
            QLabel#metricBig {{ color: {t.primary}; font-size: 42px; font-weight: 800; letter-spacing: -1.2px; }}
            QLabel#statePill {{ background: {t.surface_highest}; color: {t.text}; border: 1px solid {t.outline_variant}; border-radius: 17px; padding: 7px 11px; font-size: 10px; font-weight: 600; }}
            QLabel#statePill[state="charging"] {{ background: {t.primary_container}; color: {t.on_primary_container}; }}
            QProgressBar#batteryBar, QProgressBar#hubBatteryBar {{ background: {t.surface_highest}; border: none; border-radius: 6px; text-align: center; }}
            QProgressBar#batteryBar {{ min-height: 12px; }} QProgressBar#hubBatteryBar {{ min-height: 7px; max-height: 7px; }}
            QProgressBar#batteryBar::chunk, QProgressBar#hubBatteryBar::chunk {{ background: {t.primary}; border-radius: 6px; }}
            QProgressBar#batteryBar[tone="medium"]::chunk {{ background: {t.secondary}; }} QProgressBar#batteryBar[tone="low"]::chunk {{ background: {t.secondary_container}; }}
            QFrame#dpiTile {{ background: {t.surface_lowest}; border: 1px solid {t.outline_variant}; border-radius: 17px; }}
            QFrame#dpiTile:hover {{ background: {t.surface_high}; border-color: {t.primary}; }}
            QFrame#dpiTile[active="true"] {{ background: {t.primary_container}; border: 2px solid {t.primary}; }}
            QFrame#dpiTile[requested="true"] {{ border: 2px solid {t.secondary}; }}
            QFrame#dpiTile[active="true"] QLabel#tileStageLabel, QFrame#dpiTile[active="true"] QLabel#tileDpiLabel, QFrame#dpiTile[active="true"] QLabel#tileStateLabel {{ color: {t.on_primary_container}; }}
            QLabel#tileDpiLabel {{ color: {t.text}; font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace; font-size: 17px; font-weight: 700; }}
            QLabel#tileStateLabel {{ font-size: 8px; font-weight: 800; }}
            QFrame#sliderPanel {{ background: {t.surface_lowest}; border: 1px solid {t.outline_variant}; border-radius: 16px; }}
            QPushButton#primaryAction, QPushButton#secondaryAction {{ min-height: 36px; border-radius: 18px; padding: 0 15px; font-size: 11px; font-weight: 700; }}
            QPushButton#primaryAction {{ background: {t.primary}; color: {t.on_primary}; border: 1px solid {t.primary}; }}
            QPushButton#primaryAction:hover {{ background: {t.primary_container}; border-color: {t.primary_container}; }}
            QPushButton#secondaryAction {{ background: {t.surface_high}; color: {t.text}; border: 1px solid {t.outline_variant}; }}
            QPushButton#secondaryAction:hover {{ background: {t.surface_highest}; border-color: {t.primary}; }}
            QPushButton#secondaryAction:checked {{ background: {t.primary_container}; color: {t.on_primary_container}; border-color: {t.primary}; }}
            QPushButton:disabled {{ color: {t.subtext0}; background: {t.surface_container}; border-color: {t.outline_variant}; }}
            QPushButton#deviceTabButton {{ background: {t.surface_container}; color: {t.subtext0}; border: 1px solid {t.outline_variant}; border-radius: 20px; min-height: 38px; padding: 0 15px; font-size: 11px; font-weight: 600; }}
            QPushButton#deviceTabButton:hover {{ background: {t.surface_high}; border-color: {t.primary}; }}
            QPushButton#deviceTabButton:checked {{ background: {t.primary}; color: {t.on_primary}; border-color: {t.primary}; }}
            QComboBox {{ background: {t.surface_lowest}; color: {t.text}; border: 1px solid {t.outline_variant}; border-radius: 16px; min-height: 34px; padding: 0 12px; }}
            QComboBox QAbstractItemView {{ background: {t.surface_high}; color: {t.text}; selection-background-color: {t.primary_container}; selection-color: {t.on_primary_container}; border: 1px solid {t.outline_variant}; }}
            QSlider::groove:horizontal {{ height: 6px; background: {t.surface_highest}; border-radius: 3px; }}
            QSlider::sub-page:horizontal {{ background: {t.primary}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {t.primary}; border: 2px solid {t.on_primary}; width: 16px; margin: -6px 0; border-radius: 9px; }}
            QFrame#colorSwatch {{ background: #{self.current_color}; border: 1px solid {t.outline_variant}; border-radius: 10px; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: {t.surface_lowest}; width: 7px; margin: 2px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {t.outline_variant}; min-height: 28px; border-radius: 4px; }}
            QScrollBar::handle:vertical:hover {{ background: {t.primary}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar:horizontal {{ height: 0; width: 0; border: none; }}
            QToolTip {{ background: {t.surface_high}; color: {t.text}; border: 1px solid {t.outline_variant}; padding: 5px; }}
            QMessageBox, QColorDialog {{ background: {t.surface}; color: {t.text}; }}
        """
        app = QApplication.instance()
        if app:
            app.setStyleSheet(css)
        self.dynamic_island.setIcon(material_symbol_icon("devices_other", 20, t.on_primary))
        self.scheme_source_label.setText("CAELESTIA THEME" if t.source != "dark M3 fallback" else "M3 DARK FALLBACK")
        self.scheme_source_label.setToolTip(f"Colors loaded from {t.source}")
        self._style_color_swatch()

    def _style_color_swatch(self) -> None:
        self.color_swatch.setStyleSheet(
            f"background-color: #{self.current_color}; border: 1px solid {self.tokens.outline_variant}; border-radius: 10px;"
        )

    def _install_theme_watcher(self) -> None:
        self.theme_watcher = QFileSystemWatcher(self)
        self.theme_watcher.fileChanged.connect(self._schedule_theme_reload)
        self.theme_watcher.directoryChanged.connect(self._schedule_theme_reload)
        self.theme_reload_timer = QTimer(self)
        self.theme_reload_timer.setSingleShot(True)
        self.theme_reload_timer.setInterval(250)
        self.theme_reload_timer.timeout.connect(self._reload_theme)
        self._sync_theme_watch_paths()

    def _sync_theme_watch_paths(self) -> None:
        desired = [STATE_DIR.parent, STATE_DIR, SCHEME_FILE]
        watched = set(self.theme_watcher.files() + self.theme_watcher.directories())
        for path in desired:
            path_string = str(path)
            if path.exists() and path_string not in watched:
                self.theme_watcher.addPath(path_string)

    def _schedule_theme_reload(self, _path: str = "") -> None:
        self._sync_theme_watch_paths()
        self.theme_reload_timer.start()

    def _reload_theme(self) -> None:
        self.tokens = ThemeTokens.load()
        self.apply_styles()
        self._sync_theme_watch_paths()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.theme_reload_timer.stop() if hasattr(self, "theme_reload_timer") else None
        self.theme_watcher.deleteLater() if hasattr(self, "theme_watcher") else None
        workers = [
            self.telemetry_worker,
            self.sysmon_thread,
            self.pairing_worker,
            self.aula_telemetry_worker,
            self.aula_command_worker,
        ]
        for worker in workers:
            if worker and worker.isRunning():
                worker.stop()
        for worker in workers:
            if worker and worker.isRunning():
                worker.wait(1800)
        if any(worker and worker.isRunning() for worker in workers):
            event.ignore()
            self.setEnabled(False)
            QTimer.singleShot(250, self.close)
            return
        for process in tuple(self.action_processes.values()):
            if process.state() != QProcess.ProcessState.NotRunning:
                process.terminate()
                if not process.waitForFinished(700):
                    process.kill()
                    process.waitForFinished(500)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Nexus Peripheral Control")
    app.setOrganizationName("Nexus")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
