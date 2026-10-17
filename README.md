# Nexus Peripheral Control 🪐

[![Platform: Linux](https://img.shields.io/badge/Platform-Linux%20%7C%20Wayland-orange.svg)](https://www.kernel.org/)
[![Design: Caelestia M3](https://img.shields.io/badge/Design-Caelestia%20M3%20Expressive-7f52ff.svg)](https://github.com/caelestia-dots)
[![Interface: CLI · TUI · GUI](https://img.shields.io/badge/Interfaces-CLI%20%7C%20TUI%20%7C%20GUI-blue.svg)](#interfaces)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A unified, native Linux hardware management suite crafted with the **Caelestia Material 3 Expressive** design language. Built specifically for modern Wayland desktop environments (Hyprland, Sway, etc.) and compatible across all Linux distributions.

Controls:
1. **Rapoo MT760 / MT760L / MT760 Mini** multi-mode ergonomic wireless mouse (`24ae:1870` / `24ae:4500` / `24ae:3040`).
2. **AULA L99 Mechanical Keyboard** with 3.98-inch IPS LCD Smart Screen (`05ac:024f` / `0c45:800a`).

---

## 🎨 Design Philosophy & Caelestia Dynamic Theming

Nexus Peripheral Control dynamically extracts active color tokens from `~/.local/state/caelestia/scheme.json` (falling back gracefully to dark M3 defaults when absent):
- **Fluid & Morphing Contiguous Surfaces:** Top status bar and collapsible Nexus dynamic island drawer form a single seamless visual unit with spring animations.
- **Bento Grid Layouts:** Deep squircle containers (`border-radius: 24px`) with pill badges (`border-radius: 9999px`).
- **Full Spectrum Sync:** Colors propagate synchronously across **CLI**, **TUI**, and **GUI**.

---

## 🖥️ Three First-Class Interfaces

Nexus Peripheral Control is designed to be used however you work:

```
┌──────────────────────────────────────────────────────────────┐
│                  NEXUS PERIPHERAL CONTROL                    │
├─────────────────┬───────────────────────┬────────────────────┤
│  🖥️ Desktop GUI  │   📟 Interactive TUI   │   ⚡ Scriptable CLI │
│    (PyQt6 M3)   │   (Textual Terminal)  │   (Rich & Scripts) │
└─────────────────┴───────────────────────┴────────────────────┘
```

### 1. 🖥️ Desktop GUI (`nexus-gui`)
- Native Wayland/PyQt6 application styled after Caelestia Expressive M3.
- Contiguous Dynamic Island drawer toggles an instant hardware glance.
- Interactive 7-stage DPI Bento grid with real-time active stage highlighting.
- Hardware battery bars with smooth easing curves and low-power warnings.

### 2. 📟 Interactive TUI (`nexus-tui`)
- Full-terminal interface powered by Textual.
- **`🏠 01 Home` Landing Screen:** Bento summary cards for each peripheral with one-click drill-down actions.
- Full keyboard-driven navigation (<kbd>1</kbd>–<kbd>5</kbd>, <kbd>Esc</kbd> / <kbd>H</kbd> to return home, <kbd>R</kbd> to refresh).
- Live telemetry polling and high-contrast color cards matching your active desktop palette.

### 3. ⚡ Scriptable CLI (`nexus-ctl`)
- Fast, rich-formatted CLI for terminal users and desktop status bars (Waybar, Polybar, Caelestia shell, Hyprland status).
- Native `--json` output flag for custom scripting.
- Built-in help system: `nexus-ctl help [command]`.

---

## 📦 Architecture & Driver Repositories

Nexus Peripheral Control binds standalone reverse-engineered Linux drivers into a single cohesive interface via Git Submodules:

* [**rapoo-mt760-linux**](https://github.com/Revisory676/rapoo-mt760-linux): Standalone userspace driver, telemetry decoder, 7-stage DPI switcher, and udev rules for the Rapoo MT760L.
* [**aula-l99-linux**](https://github.com/Revisory676/aula-l99-linux): Standalone driver, reverse-engineered 2.4GHz wireless battery queries, 20 RGB effects, debounce/sleep, and 3.98-in LCD screen tools for the AULA L99.

---

## 🚀 Quick Start & Installation

### 1. Clone with Submodules
```bash
git clone --recurse-submodules https://github.com/Revisory676/nexus-peripheral-control.git
cd nexus-peripheral-control
```

*(If you already cloned without submodules, run `git submodule update --init --recursive`)*.

### 2. Install System Dependencies
On **Arch Linux / CachyOS**:
```bash
sudo pacman -S python python-pyqt6 python-rich python-rich-argparse python-textual python-pyusb
```
On **Ubuntu / Debian**:
```bash
sudo apt install python3 python3-pyqt6 python3-rich python3-usb
pip install textual rich-argparse
```

### 3. Run Automated Installer
The included [`install.sh`](file:///home/revisory/Documents/antigravity/peaceful-mendeleev/install.sh) configures non-root udev rules, creates system symlinks (`nexus-ctl`, `nexus-tui`, `nexus-gui`), and installs the `.desktop` launcher:
```bash
./install.sh
```

---

## ⌨️ CLI Usage Reference

```bash
# Show live hardware status dashboard
nexus-ctl status

# Output status as JSON (for Waybar / Hyprland scripts)
nexus-ctl status --json

# Set Rapoo mouse DPI (e.g. 1600 DPI)
nexus-ctl mouse --dpi 1600

# Set AULA keyboard RGB effect, color, brightness, and speed
nexus-ctl kbd --mode 3 --color 00FFCC --brightness 5 --speed 4

# View detailed built-in help guide
nexus-ctl help
nexus-ctl help mouse
nexus-ctl help kbd
```

---

## ⌨️ TUI Keybindings

| Key | Action |
| :--- | :--- |
| <kbd>1</kbd> or <kbd>H</kbd> or <kbd>Esc</kbd> | Jump to **`🏠 01 Home`** Screen |
| <kbd>2</kbd> | Open Rapoo MT760L Page |
| <kbd>3</kbd> | Open AULA L99 Page |
| <kbd>4</kbd> | Open Receiver Recovery Tool |
| <kbd>5</kbd> | Open Caelestia Theme Inspector |
| <kbd>R</kbd> | Force telemetry refresh |
| <kbd>Q</kbd> | Quit application |

---

## 🛡️ License

This project is licensed under the [MIT License](LICENSE).
Copyright (c) 2026 Revisory.
