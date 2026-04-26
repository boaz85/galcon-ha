#!/bin/bash
# Install the Galcon MQTT bridge on Raspberry Pi OS (Bookworm)
set -e

INSTALL_DIR="/home/boaz/galcon-bridge"
SERVICE="galcon-bridge"

echo "=== Installing Galcon MQTT bridge ==="

# Dependencies
echo "Installing dependencies..."
sudo apt-get install -y python3-bleak python3-paho-mqtt

# Deploy files
echo "Deploying to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp galcon_bridge.py "$INSTALL_DIR/"

if [ ! -f "$INSTALL_DIR/galcon_bridge_config.json" ]; then
    cp galcon_bridge_config.json.template "$INSTALL_DIR/galcon_bridge_config.json"
    echo ""
    echo ">>> Edit $INSTALL_DIR/galcon_bridge_config.json with your MQTT credentials <<<"
    echo ""
fi

# Systemd service
echo "Installing systemd service..."
sudo cp galcon-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"

echo ""
echo "=== Done ==="
echo "Edit the config if needed: nano $INSTALL_DIR/galcon_bridge_config.json"
echo "Then start the service:    sudo systemctl start $SERVICE"
echo "Watch the logs:            sudo journalctl -fu $SERVICE"
