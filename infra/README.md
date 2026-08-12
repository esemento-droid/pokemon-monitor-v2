# Infrastructure — Proxy, Solvers, IP Rotation

## Deploy on VPS:
```bash
cd /opt/pokemon-monitor-v2 && git pull origin main
bash infra/deploy_vps.sh
```

## Deploy on Phone (mi-9t, via VPS SSH):
```bash
cd /opt/pokemon-monitor-v2
bash infra/deploy_phone.sh
```

## Components:
- `proxy_router.py` — Smart proxy selection per account/shop
- `solver.py` — Universal challenge solver (CF, CAPTCHA, rate-limit, IP ban)
- `proxy_watchdog.sh` — VPS-side auto-heal (Tailscale backup)
- `rotate_mobile_ip.sh` — On-demand IP rotation trigger
- `start_socks5.sh` — SOCKS5 persistent proxy
- `check_proxy.sh` — Quick proxy health check
- `infra/deploy_vps.sh` — Full VPS infra deploy
- `infra/deploy_phone.sh` — Full phone infra deploy
- `infra/phone/` — Scripts deployed to mi-9t

## Architecture:
```
VPS (146.59.45.228)
├── Proxy Router → picks best proxy per request
├── FlareSolverr (Docker :8191) → CF bypass
├── SOCKS5 (:1080) → SSH dynamic forward to phone
├── HTTP tunnel (:8888) → tinyproxy on phone via autossh
├── Tailscale direct (100.127.72.24:8888) → backup path
└── Solver → auto-handles any challenge bot encounters

Phone mi-9t (100.127.72.24)
├── Tinyproxy (:8888) → HTTP proxy via mobile data
├── Autossh → reverse tunnel to VPS
├── Watchdog (cron 1min) → restarts dead services
├── IP rotation (cron 4h) → airplane mode toggle
└── Boot script → everything starts on reboot
```
