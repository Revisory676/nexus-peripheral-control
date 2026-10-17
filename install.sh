#!/usr/bin/env bash
# Nexus Peripheral Control — System Installer Script
# Automates udev rules, binaries, desktop entries, and icon installation.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="/usr/local/bin"
DESKTOP_DIR="/usr/share/applications"
ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
LOCAL_DESKTOP_DIR="${HOME}/.local/share/applications"
LOCAL_ICON_DIR="${HOME}/.local/share/icons"

echo "=================================================="
echo "    Installing Nexus Peripheral Control Suite    "
echo "=================================================="

# Ensure executables are executable
chmod +x "${SCRIPT_DIR}/nexus_ctl.py"
chmod +x "${SCRIPT_DIR}/nexus_tui.py"
chmod +x "${SCRIPT_DIR}/nexus_gui.py"

# System binaries
echo "[*] Creating binary symlinks in ${BIN_DIR}..."
sudo ln -sf "${SCRIPT_DIR}/nexus_ctl.py" "${BIN_DIR}/nexus-ctl"
sudo ln -sf "${SCRIPT_DIR}/nexus_tui.py" "${BIN_DIR}/nexus-tui"
sudo ln -sf "${SCRIPT_DIR}/nexus_gui.py" "${BIN_DIR}/nexus-gui"

# User local binaries fallback
mkdir -p "${HOME}/.local/bin"
ln -sf "${SCRIPT_DIR}/nexus_ctl.py" "${HOME}/.local/bin/nexus-ctl"
ln -sf "${SCRIPT_DIR}/nexus_tui.py" "${HOME}/.local/bin/nexus-tui"
ln -sf "${SCRIPT_DIR}/nexus_gui.py" "${HOME}/.local/bin/nexus-gui"

# Udev rules installation
echo "[*] Installing udev rules..."
if [ -f "${SCRIPT_DIR}/drivers/rapoo-mt760/udev/90-rapoo-mt760.rules" ]; then
    sudo cp "${SCRIPT_DIR}/drivers/rapoo-mt760/udev/90-rapoo-mt760.rules" /etc/udev/rules.d/
elif [ -f "${SCRIPT_DIR}/udev/90-rapoo-mt760.rules" ]; then
    sudo cp "${SCRIPT_DIR}/udev/90-rapoo-mt760.rules" /etc/udev/rules.d/
fi

if [ -f "${SCRIPT_DIR}/Aula_L99_Linux/packaging/90-aula-l99.rules" ]; then
    sudo cp "${SCRIPT_DIR}/Aula_L99_Linux/packaging/90-aula-l99.rules" /etc/udev/rules.d/
fi

sudo udevadm control --reload-rules
sudo udevadm trigger

# Icon & Desktop Entry
echo "[*] Installing icons and desktop entries..."
mkdir -p "${LOCAL_ICON_DIR}" "${LOCAL_DESKTOP_DIR}"
if [ -f "${SCRIPT_DIR}/assets/icons/nexus-peripheral-control.png" ]; then
    cp "${SCRIPT_DIR}/assets/icons/nexus-peripheral-control.png" "${LOCAL_ICON_DIR}/nexus-peripheral-control.png"
    sudo mkdir -p "${ICON_DIR}"
    sudo cp "${SCRIPT_DIR}/assets/icons/nexus-peripheral-control.png" "${ICON_DIR}/nexus-peripheral-control.png"
fi

cp "${SCRIPT_DIR}/nexus-peripheral-control.desktop" "${LOCAL_DESKTOP_DIR}/nexus-peripheral-control.desktop"
if [ -d "${DESKTOP_DIR}" ]; then
    sudo cp "${SCRIPT_DIR}/nexus-peripheral-control.desktop" "${DESKTOP_DIR}/nexus-peripheral-control.desktop" 2>/dev/null || true
fi

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "${LOCAL_DESKTOP_DIR}" || true

echo ""
echo "✓ Installation complete!"
echo "  - CLI:     nexus-ctl --help"
echo "  - TUI:     nexus-tui"
echo "  - GUI:     nexus-gui"
echo "=================================================="
