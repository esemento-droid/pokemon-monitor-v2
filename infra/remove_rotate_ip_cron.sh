#!/bin/bash
# Remove useless rotate_ip.sh cron from phone (Orange PL = static IP, rotation does nothing)
# This cron causes proxy outages every 4h (08:00, 12:00, 16:00, 20:00) by toggling airplane mode
sshpass -p '123' ssh -o StrictHostKeyChecking=no -p 8022 100.127.72.24 'crontab -l | grep -v rotate_ip | crontab -'
echo "Done. Verifying:"
sshpass -p '123' ssh -o StrictHostKeyChecking=no -p 8022 100.127.72.24 'crontab -l'
