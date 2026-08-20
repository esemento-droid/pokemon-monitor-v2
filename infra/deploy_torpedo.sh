#!/bin/bash
# Deploy JC Torpedo Daemon as systemd service
cd /opt/pokemon-monitor-v2

echo "=== Deploying JC Torpedo Daemon ==="

# Copy service file
sudo cp infra/jc-torpedo.service /etc/systemd/system/jc-torpedo.service

# Reload systemd
sudo systemctl daemon-reload

# Enable (auto-start on boot)
sudo systemctl enable jc-torpedo

# Start
sudo systemctl start jc-torpedo

# Check status
sleep 3
sudo systemctl status jc-torpedo --no-pager

echo ""
echo "=== Done. Logs: journalctl -u jc-torpedo -f ==="
