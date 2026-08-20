#!/bin/bash
# Run on VPS — disables airplane mode cron on phone (Mi 9T)
# Removes night_sleep and failsafe cron entries from phone's crontab
# Usage: bash infra/disable_airplane_cron.sh

PHONE="100.127.72.24"
PORT="8022"
PASS="123"

echo "=== Disabling airplane mode cron on phone ==="
echo ""

# Show current crontab
echo "Current phone crontab:"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PORT $PHONE 'crontab -l 2>/dev/null' | tee /tmp/phone_cron_before.txt
echo ""

# Remove airplane-related lines (night_sleep, failsafe, airplane)
echo "Removing airplane entries..."
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PORT $PHONE '
CRON=$(crontab -l 2>/dev/null)
echo "$CRON" | grep -iv "airplane\|night_sleep\|failsafe" | crontab -
echo "New crontab:"
crontab -l 2>/dev/null
'

echo ""
echo "=== Done. Airplane mode cron disabled. ==="
