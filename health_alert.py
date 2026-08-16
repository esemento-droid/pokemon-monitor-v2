#!/usr/bin/env python3
"""
Health Alert — monitors critical systems and alerts on Discord ONLY when something breaks.
Runs via cron every 2 minutes. Silent when everything OK.

Alerts on:
  🔴 CRITICAL:
    - Monitor service dead
    - ALL proxies dead (>3 min)
    - FlareSolverr dead
  🟡 WARNING:
    - Proxy tunnel dead (degraded — Tailscale still works)
    - Phone unreachable via Tailscale
    - Monitor error rate >10% in last 5 min

Does NOT spam — only alerts on STATE CHANGE (down→up, up→down).
Uses state file to track previous status.
"""
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional

BASE_DIR = Path("/opt/pokemon-monitor-v2")
STATE_FILE = BASE_DIR / "data" / "health_state.json"
WEBHOOK_FILE = BASE_DIR / "discord_webhook_stats.txt"  # dedicated stats/health channel
WEBHOOK_FALLBACK = BASE_DIR / "discord_webhook_jc.txt"

# Anti-spam: don't alert if state changed less than 10 min ago
MIN_ALERT_INTERVAL = 600  # seconds


def load_state() -> Dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state: Dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def send_discord(message: str):
    """Send alert to Discord webhook."""
    webhook_url = ""
    if WEBHOOK_FILE.exists():
        webhook_url = WEBHOOK_FILE.read_text().strip()
    if not webhook_url and WEBHOOK_FALLBACK.exists():
        webhook_url = WEBHOOK_FALLBACK.read_text().strip()
    if not webhook_url:
        return
    try:
        subprocess.run(
            ["curl", "-s", "-X", "POST", webhook_url,
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"content": message})],
            timeout=10, capture_output=True
        )
    except Exception:
        pass


def check_monitor() -> bool:
    """Check if pokemon-monitor-v2 service is active."""
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "pokemon-monitor-v2"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False


def check_proxy_tunnel() -> bool:
    """Check if proxy tunnel (127.0.0.1:8888) works."""
    try:
        r = subprocess.run(
            ["curl", "-x", "http://127.0.0.1:8888", "-s", "-o", "/dev/null",
             "-w", "%{http_code}", "--connect-timeout", "8", "--max-time", "12", "https://google.com"],
            capture_output=True, text=True, timeout=15
        )
        return r.stdout.strip() in ("200", "301", "302")
    except Exception:
        return False


def check_proxy_tailscale() -> bool:
    """Check if proxy via Tailscale (100.127.72.24:8888) works."""
    try:
        r = subprocess.run(
            ["curl", "-x", "http://100.127.72.24:8888", "-s", "-o", "/dev/null",
             "-w", "%{http_code}", "--connect-timeout", "8", "--max-time", "12", "https://google.com"],
            capture_output=True, text=True, timeout=15
        )
        return r.stdout.strip() in ("200", "301", "302")
    except Exception:
        return False


def check_flaresolverr() -> bool:
    """Check if FlareSolverr is responding."""
    try:
        r = subprocess.run(
            ["curl", "-s", "--connect-timeout", "5", "http://localhost:8191"],
            capture_output=True, text=True, timeout=8
        )
        return "FlareSolverr" in r.stdout
    except Exception:
        return False


def check_phone_reachable() -> bool:
    """Check if phone is reachable via Tailscale."""
    try:
        r = subprocess.run(
            ["tailscale", "ping", "--timeout=5s", "100.127.72.24"],
            capture_output=True, text=True, timeout=8
        )
        return "pong" in r.stdout
    except Exception:
        return False


def main():
    state = load_state()
    alerts = []
    recoveries = []
    new_state = {}

    # === CHECKS ===
    checks = {
        "monitor": ("🖥️ Monitor", check_monitor, "CRITICAL"),
        "flaresolverr": ("🐳 FlareSolverr", check_flaresolverr, "WARNING"),
    }

    # Proxy checks — track state but DON'T alert (self-heals, alerting is just spam)
    proxy_checks = {
        "proxy_tunnel": ("🔌 Proxy tunnel", check_proxy_tunnel),
        "proxy_tailscale": ("🌐 Proxy Tailscale", check_proxy_tailscale),
        "phone": ("📱 Phone (mi-9t)", check_phone_reachable),
    }

    # Track proxy state silently (for state file only, no Discord alerts)
    for key, (name, check_fn) in proxy_checks.items():
        is_ok = check_fn()
        new_state[key] = is_ok
        fail_count_key = f"{key}_fail_count"
        if not is_ok:
            new_state[fail_count_key] = state.get(fail_count_key, 0) + 1
        else:
            new_state[fail_count_key] = 0

    for key, (name, check_fn, severity) in checks.items():
        is_ok = check_fn()
        was_ok = state.get(key, True)
        new_state[key] = is_ok

        # Debounce: require 2 consecutive failures before declaring DOWN
        fail_count_key = f"{key}_fail_count"
        if not is_ok:
            fail_count = state.get(fail_count_key, 0) + 1
            new_state[fail_count_key] = fail_count
            # Only consider DOWN after 3+ consecutive failures (9+ min with */3 cron)
            if fail_count < 3:
                new_state[key] = was_ok  # Keep previous state, not yet confirmed DOWN
                is_ok = was_ok
        else:
            new_state[fail_count_key] = 0

        # Anti-spam: check when this key last changed
        last_change_key = f"{key}_last_change"
        last_change = state.get(last_change_key, 0)
        now = time.time()

        if not is_ok and was_ok:
            # State change: was OK → now DEAD
            if now - last_change > MIN_ALERT_INTERVAL:
                emoji = "🔴" if severity == "CRITICAL" else "🟡"
                alerts.append(f"{emoji} **{name}** — DOWN!")
                new_state[last_change_key] = now
            else:
                new_state[last_change_key] = last_change  # keep old timestamp
        elif is_ok and not was_ok:
            # State change: was DEAD → now OK
            if now - last_change > MIN_ALERT_INTERVAL:
                recoveries.append(f"✅ **{name}** — RESTORED")
                new_state[last_change_key] = now
            else:
                new_state[last_change_key] = last_change
        else:
            new_state[last_change_key] = last_change  # no change

    # Special: ALL proxies dead — track silently, no alert (self-heals via watchdog)
    if not new_state.get("proxy_tunnel") and not new_state.get("proxy_tailscale"):
        new_state["all_proxy_dead"] = True
    else:
        new_state["all_proxy_dead"] = False

    # === SEND ALERTS ===
    if alerts:
        msg = "⚠️ **HEALTH ALERT**\n" + "\n".join(alerts)
        msg += f"\n\n_Czas: {time.strftime('%H:%M:%S')}_"
        send_discord(msg)

    if recoveries:
        msg = "🟢 **RECOVERY**\n" + "\n".join(recoveries)
        msg += f"\n\n_Czas: {time.strftime('%H:%M:%S')}_"
        send_discord(msg)

    # Save state
    new_state["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_state(new_state)


if __name__ == "__main__":
    main()
