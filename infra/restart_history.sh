#!/bin/bash
# Pokazuje restarty monitora + przyczyny crashy
# bash infra/restart_history.sh | curl -sF 'file=@-' https://paste.rs

echo "=== RESTART HISTORY (ostatnia godzina) ==="
echo "Data: $(date)"
echo ""

echo "--- 1. Restarty systemd (ostatnia godzina) ---"
journalctl -u pokemon-monitor-v2 --since "1 hour ago" --no-pager | grep -iE "start|stop|activat|deactivat|killed|signal|Main process|OOM" | tail -30
echo ""

echo "--- 2. PID-y monitora (czy sie zmienily?) ---"
journalctl -u pokemon-monitor-v2 --since "1 hour ago" --no-pager | grep -oP 'python\[\d+\]' | sort -u
echo ""
echo "Aktualny PID:"
pgrep -a -f "python.*main.py" | head -5
echo ""

echo "--- 3. OOM killer (ostatnia godzina) ---"
dmesg --time-format iso 2>/dev/null | grep -i "oom\|killed process\|out of memory" | tail -10
journalctl --since "1 hour ago" --no-pager | grep -i "oom\|killed process\|out of memory" | tail -10
echo ""

echo "--- 4. Systemd status teraz ---"
systemctl status pokemon-monitor-v2 --no-pager 2>&1 | head -20
echo ""

echo "--- 5. Ostatnie FATAL/crash linie ---"
journalctl -u pokemon-monitor-v2 --since "1 hour ago" --no-pager | grep -iE "fatal|traceback|exception.*error|unhandled|crash|segfault" | tail -20
echo ""

echo "--- 6. Czas startu procesow ---"
ps -eo pid,lstart,args | grep "python.*main.py" | grep -v grep
echo ""

echo "--- 7. Ile razy monitor startowal (ostatnia godzina) ---"
journalctl -u pokemon-monitor-v2 --since "1 hour ago" --no-pager | grep -c "Starting\|Started\|Main PID"
echo ""

echo "=== KONIEC ==="
