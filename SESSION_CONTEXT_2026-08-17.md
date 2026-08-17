# Session Context — 2026-08-17 (Proxy Optimization + Night IP Test)

## Co zrobiono:

### 1. Proxy fixes (PR #30 — merged)
- `proxy_router.py`: socks5:// → socks5h:// (DNS via proxy), get_playwright_proxy() konwertuje z powrotem na socks5:// dla Chromium
- `proxy_router.py`: request_ip_rotation() skipuje gdy Orange PL static IP
- `start_socks5.sh`: real connectivity test + zombie detection (pkill -9) + fallback path
- `rotate_mobile_ip.sh`: skip gdy static IP, --force flag
- `infra/deploy_phone.sh`: phone-side rotate_ip.sh ma ten sam guard

### 2. Phone watchdog fix
- Stary watchdog na telefonie miał "VPS UNREACHABLE" check → force-restart autossh CO MINUTĘ
- Powodowało 43+ niepotrzebnych restartów/godzinę → przerwy w tunelu → timeouty scraperów
- Nowy watchdog: TYLKO pgrep — restartuje wyłącznie gdy proces naprawdę padnie
- VPS-side proxy_watchdog.sh naprawia tunel z drugiej strony (nie potrzeba podwójnego)

### 3. Night IP test (deployed, czeka na 3:00)
- Cel: sprawdzić czy 2h airplane mode na Orange PL zmieni IP
- Skrypt na telefonie (cron 3:00): airplane ON → sleep 2h → airplane OFF → check IP → restart
- 7 warstw bezpieczeństwa (wake-lock, sleep-loop, failsafe cron 5:15, watchdog flag, DNS fix, retry VPS report, boot script)
- Wynik: `bash infra/night_ip_test.sh check` po 5:10

## Stan systemu:

### Proxy:
- ✅ 3 paths: tunnel (8888), tailscale (100.127.72.24:8888), SOCKS5 (1080)
- ✅ Mobile IP: 37.47.130.139 (Orange PL, zmienił się z 37.47.128.183 sam w 10 dni)
- ✅ mobile_proxy_ip.txt zaktualizowany
- ✅ FlareSolverr: OK

### Scrapery:
- 138/171 shopów zwraca produkty (3h window)
- 100 shopów ma 10+ skanów/3h (zdrowe)
- 12 shopów martwe (pokesmart SSL, tantis_old deprecated, mediaexpert nodriver fail, limango, rgfk syntax error)
- 51 shopów struggling (<30% success) — wolne serwery po ich stronie, nie proxy
- tcgumisia-proxy: 511 skanów, 100% success

### Telefon (Mi 9T):
- Uptime: 10+ dni
- tinyproxy OK, autossh OK, crond OK
- rotate_ip.sh: v2 (ma static IP guard)
- watchdog.sh: v2 (pgrep only, bez false restarts)
- Cron: watchdog co 1 min, rotate co 4h (skip z guardem), night_sleep o 3:00, failsafe o 5:15

### VPS:
- pokemon-monitor-v2.service: active
- Cron: proxy_watchdog co 1 min, start_socks5 co 5 min, health_alert co 3 min
- Disk: 16GB free (78% used)
- RAM: 110MB free / 7.6GB total

## Pliki dodane/zmienione w tej sesji:
- `proxy_router.py` — socks5h, Playwright conversion, rotation guard
- `start_socks5.sh` — zombie detection, real test, fallback
- `rotate_mobile_ip.sh` — static IP skip
- `infra/deploy_phone.sh` — nowy watchdog + rotate_ip guard
- `infra/phone_health_check.sh` — quick health check
- `infra/full_health_check.sh` — comprehensive system check
- `infra/scraper_stats.py` — all shops stats from journalctl
- `infra/deep_check.py` — dead shops + frequency + watchdog analysis
- `infra/night_ip_test.sh` — nocny test IP (deploy/check/cancel)

## Następne kroki:
1. **Rano po 5:10** → `bash infra/night_ip_test.sh check` → czy IP się zmienił?
2. **Jeśli TAK** → można schedulować nightly rotation (darmowe!)
3. **Jeśli NIE** → potrzeba Play SIM (starter 5 PLN + doładowanie 50 PLN = 800 GB, dynamiczne IP)
4. **Martwe shopy** → pokesmart (SSL dead), mediaexpert (nodriver fail), rgfk (syntax error) — do zbadania osobno
5. **RAM 110MB free** → trzymać oko, może trzeba coś odciąć

## Ważne adresy/dane:
- VPS: 146.59.45.228 (OVH, Debian)
- Phone Tailscale: 100.127.72.24
- Phone SSH: port 8022, pass: 123
- Mobile IP: 37.47.130.139 (Orange PL)
- DB: postgresql://pokemonitor:mon2026pg@localhost/pokemonitor
- Repo: github.com/mr68pknctx/pokemon-monitor-v2 (alias: esemento-droid)
