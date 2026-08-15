# Infrastruktura — Pokemon Monitor v2

## VPS (Produkcja)
| Parametr | Wartość |
|----------|---------|
| Provider | OVHcloud |
| OS | Debian |
| RAM | 8 GB |
| CPU | 4 cores |
| Python | 3.11 (venv at ./venv/) |
| Path | /opt/pokemon-monitor-v2/ |
| Service | pokemon-monitor-v2.service (systemd, auto-restart) |
| ExecStart | venv/bin/python3 main.py |
| Environment | PYTHONUNBUFFERED=1, DISPLAY=:99, LimitNOFILE=65535 |

## PostgreSQL
| Parametr | Wartość |
|----------|---------|
| Host | localhost |
| User | pokemonitor |
| Password | mon2026pg |
| Database | pokemonitor |
| Library | asyncpg |
| DSN | postgresql://pokemonitor:mon2026pg@localhost/pokemonitor |

### Tabele:
| Tabela | Opis | PK |
|--------|------|-----|
| products | Główna: id, shop, name, price, url, image, stock, available, last_seen, created_at | (id, shop) |
| shop_state | Stan per-shop: snapshot_done, last_scan, scan_count, error_count | shop |
| event_log | Historia eventów: NEW/RESTOCK/SOLD_OUT/PRICE_CHANGE/BOT_* | id (serial) |
| price_history | Zmiany cen w czasie | id (serial) |
| orders | Tracking zamówień botów: triggered→atc_ok→checkout_ok→confirmed/failed | id (serial) |
| shop_intel | Inteligencja per-shop: restock count, turbo mode, correlations | — |

**UWAGA**: data/products.db i config.py DB_PATH = LEGACY/UNUSED (stary SQLite, nie używać!)

### Komendy DB:
```sql
-- Reset shopa:
DELETE FROM products WHERE shop='X';
DELETE FROM shop_state WHERE shop='X';

-- Wyczyść produkty z nowych exclude:
DELETE FROM products WHERE shop='X' AND lower(name) LIKE '%deck%';

-- Statystyki:
SELECT shop, count(*) FROM products GROUP BY shop ORDER BY count DESC;
SELECT event_type, count(*) FROM event_log WHERE ts > now() - interval '24h' GROUP BY event_type;
```

---

## Mobile Proxy (Xiaomi Mi 9T)

### Hardware:
- Telefon: Xiaomi Mi 9T
- SIM: Orange PL (800GB/miesiąc)
- IP: **37.47.128.183** (STATIC! Airplane mode NIE rotuje)
- Dual SIM slot wolny — plan: druga SIM (Play/T-Mobile prepaid ~5 PLN) dla dynamicznego IP

### Software na telefonie (Termux):
| Serwis | Port | Opis |
|--------|------|------|
| Tinyproxy | 8888 | HTTP proxy |
| sshd | 8022 | SSH server |
| Tailscale | — | VPN mesh (IP: 100.127.72.24) |

### Dostęp z VPS:
| Metoda | Adres | Użycie |
|--------|-------|--------|
| HTTP Proxy | 127.0.0.1:8888 | Scrapery (empik, mediaexpert, strefakart, tcgumisia poller) |
| SOCKS5 | 127.0.0.1:1080 | Boty autobuy, ogólne proxy |
| SSH Tunnel | localhost:2222 | Reverse tunnel (fallback) |
| Tailscale Direct | 100.127.72.24:8022 | Primary connection |

### Start SOCKS5:
```bash
sshpass -p '123' ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 -o ConnectTimeout=10 -f -N \
  -D 127.0.0.1:1080 -p 8022 100.127.72.24
```

### WAŻNE:
- SOCKS5 wymaga `socks5h://` (NIE `socks5://`) — socks5h resolves DNS przez proxy
- Zombie SOCKS5 fix: `pkill -9 -f "ssh.*1080"` (zwykły kill nie wystarcza)
- start_socks5.sh ma 2 fallback paths: Tailscale direct (8022) → reverse tunnel (2222)
- Cron co 5 min sprawdza i naprawia
- Tunnel + Tailscale flap every 15-60min, recovery supervisor auto-fixes <1min

### Problemy z IP:
- Orange PL = **STATIC** IP — airplane mode NIE rotuje
- Bonito.pl **ZBANOWAŁO** ten IP (37.47.128.183)
- Rozwiązanie docelowe: druga SIM (Play/T-Mobile) = dynamiczny IP z rotacją

---

## FlareSolverr
| Parametr | Wartość |
|----------|---------|
| URL | http://localhost:8191 |
| Deploy | Docker container |
| Użycie | CF bypass (battlestash, strefamtg, sklepkleks, empik) |
| Sesje | Reusable per-shop (np. sesja 'promoklocki' dla price_compare) |

### Shops używające FlareSolverr:
- empik (FlareSolverr + aiohttp + regex)
- battlestash (FlareSolverr, SLOW)
- strefamtg (FlareSolverr + filtr pokemon, SLOW)
- sklepkleks (FlareSolverr, SLOW)
- promoklocki.pl (price_compare.py, sesja reusable)

---

## Xvfb (Virtual Display)
| Parametr | Wartość |
|----------|---------|
| Display | :99 |
| Użycie | nodriver (headless=False wymaga display) |
| WAŻNE | DISPLAY=:99 w env — dict(**os.environ, DISPLAY=':99') CRASHUJE gdy DISPLAY już w env! Używaj {**os.environ, 'DISPLAY': ':99'} |

---

## Discord

### Webhooks (pliki .txt w repo):
| Plik | Kanał |
|------|-------|
| discord_webhook_jc.txt | Główny (japancollectibles + fallback) |
| discord_webhook_kartexpol.txt | Kartexpol |
| discord_webhook_strefatcg.txt | StrefaTCG |
| discord_webhook_empik.txt | Empik |
| discord_webhook_smyk.txt | Smyk + MediaExpert |
| discord_webhook_tantis.txt | Tantis |
| discord_webhook_limango.txt | Limango (LEGO) |
| discord_webhook_stats.txt | 📊・daily-stats + health alerts |

### Discord Router:
| Parametr | Wartość |
|----------|---------|
| Path | /opt/pokemon-monitor-v2/discord_router/ |
| Service | discord-router.service |
| Venv | symlink do /opt/discord-router/venv |
| Source channel | 1526349733935710218 |
| Guild | 1498746165657731143 |
| Bot token | discord_router/.env (gitignored) |

### Routing:
| Warunek | Kategoria |
|---------|-----------|
| shop in LEGO_SHOPS (limango) | 🧱 LEGO |
| shop in FOREIGN_SHOPS (efantasy) | 🌍 Zagraniczne |
| Default | Auto-create channel per shop name |

### Image Proxy (weserv.nl):
Shops z hotlink protection/slow CDN → `https://images.weserv.nl/?url=ORIGINAL`:
pikashop, bookland, gameover, basanti, cardwolf, aleplanszowki, dragoneye,
twojekarty, poketrader, missaga, karcianybunkier, magiccafe, hearts,
jaskiniatrolla, piwniczaki, sklepkleks

---

## Systemd Services

### pokemon-monitor-v2.service:
```ini
[Unit]
Description=Pokemon Monitor v2
After=network.target postgresql.service

[Service]
Type=simple
WorkingDirectory=/opt/pokemon-monitor-v2
ExecStart=/opt/pokemon-monitor-v2/venv/bin/python3 main.py
Environment=PYTHONUNBUFFERED=1 DISPLAY=:99
LimitNOFILE=65535
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Komendy:
```bash
# Restart:
sudo systemctl restart pokemon-monitor-v2

# Logi:
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager

# Status:
sudo systemctl status pokemon-monitor-v2

# PRZED restartem ZAWSZE:
./venv/bin/python3 -c "import main"  # jeśli fail → NIE restartuj!
```

---

## Git & Deploy

### VPS Git Auth:
```bash
git config --global credential.helper '!gh auth git-credential'
# gh zalogowany jako debian, git push BEZ sudo (token per-user)
```

### Deploy pattern:
```bash
cd /opt/pokemon-monitor-v2
git stash          # local edits (detector.py/trigger changes)
git pull --rebase origin main
git stash pop      # re-apply local edits
sudo systemctl restart pokemon-monitor-v2
sudo systemctl restart discord-router
```

### Push from sandbox (Kiro):
- Kiro ma auth via gateway — push z sandbox, pull na VPS
- NIGDY push bezpośrednio na main — zawsze branch + PR

---

## Network Topology

```
[VPS OVH]
  ├── PostgreSQL (localhost:5432)
  ├── FlareSolverr Docker (localhost:8191)
  ├── Xvfb :99
  ├── SSH tunnel → Phone (localhost:2222 / Tailscale:8022)
  │     ├── HTTP Proxy (127.0.0.1:8888)
  │     └── SOCKS5 (127.0.0.1:1080)
  ├── pokemon-monitor-v2.service (4 processes)
  │     ├── FAST (111 shops, async HTTP)
  │     ├── SLOW (19 shops, FlareSolverr)
  │     ├── NODRIVER (10 shops, Chrome subprocess)
  │     └── ENGINES (1 engine, proxy poller)
  └── discord-router.service

[Xiaomi Mi 9T]
  ├── Orange PL SIM (800GB, static IP 37.47.128.183)
  ├── Termux: tinyproxy:8888 + sshd:8022
  └── Tailscale (100.127.72.24)

[GitHub]
  └── esemento-droid/pokemon-monitor-v2 (main branch)
      ← push from Kiro sandbox
      → pull on VPS
```
