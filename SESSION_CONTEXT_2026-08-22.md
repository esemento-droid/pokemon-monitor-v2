# Session Context — 2026-08-22 (Full Stability Overhaul)

## ZASTĘPUJE: SESSION_CONTEXT_2026-08-21.md

---

## ⚠️ OBOWIĄZKOWE NA START KAŻDEJ NOWEJ SESJI

```
cd /opt/pokemon-monitor-v2 && bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs
```

Kiro: wczytaj repo, context, rules, todo, najnowszy SESSION_CONTEXT i live_report — pełna diagnostyka zanim cokolwiek zrobisz.

---

## Co zrobiono w tej sesji (2026-08-22):

### PR #54 — Full Stability Overhaul (5 plików, 240+/142-)

#### 1. Camoufox crash recovery (xjoy/gralnia/battlestash)

| Co było | Co jest |
|---------|---------|
| Browser crashował po 1-2h, `_camoufox_browser = None`, lazy re-init natychmiastowy → failował → shop w cooldown | 3x retry z backoff (5s, 10s), wait na zombie cleanup, force-kill fallback, timeout na `__aenter__` |
| `_restart_browsers()` resetował TEŻ Camoufox (bo "nuclear") | Chromium restart oddzielony — Camoufox ma własny lazy recovery |
| xjoy usunięty z HARD_SHOPS ("try Chromium first") | xjoy z powrotem w HARD_SHOPS (Chromium evidentnie nie przechodzi) |

#### 2. CF Solver browser death loop

| Co było | Co jest |
|---------|---------|
| N concurrent solve() → każdy `ensure_future(_restart_browsers())` → wyścig restartów | `_restart_in_progress` guard — tylko 1 restart na raz |
| `_BrowserDeadError` → `continue` (próbuj drugi browser) | `break` (oba mogą być martwe, nie ryzykuj) |
| "Protocol error" nie wykrywany jako browser death | Dodany do detekcji + "Target.createTarget" |
| solve() próbuje nawet gdy restart trwa | Early-return `None` gdy `_restart_in_progress` |

#### 3. NODRIVER crash storm (tantis/mediaexpert prawie martwe)

| Co było | Co jest |
|---------|---------|
| Po respawn: consecutive_err rośnie → 10min cooldown | Reset `consecutive_err = 0` po udanym respawn |
| Stale page (po respawn innego workera) → crash → heal → double-respawn | Check `page.is_closed()` na start każdej iteracji |
| 5 workerów jednocześnie triggeruje `_respawn_browser()` | `asyncio.Lock` + 30s cooldown na respawn |
| Po respawn: normalne cooldown delays (90-600s) | Grace period: 3 skany z 15-30s delay zamiast 300s |

#### 4. Torpedo hourly restart

| Co było | Co jest |
|---------|---------|
| `session_warmer.py` logował na TE SAME konta JC co godzinę | JC usunięty z warmera (torpedo sam re-staguje) |
| `japancollectibles_torpedo` warmup z warmera | Usunięty (konflikt z daemon) |
| Każdy nuclear restart → Discord alert | Alert TYLKO gdy ≥50% kont staged (redukuje spam) |

#### 5. Torpedo health alert (NOWE)

- `health_alert.py`: dodany `check_torpedo_staged()`
- Sprawdza journalctl za ostatnie 10min: czy jest "✅ STAGED"
- Jeśli 0 staged przez 10+ min → 🔴 CRITICAL alert na Discord
- Debounce (3 kolejne fail checks = 9 min z */3 cron) zanim alert

---

## Stan oczekiwany po deploy:

### CF Solver — TRI-PATH (stabilny):
| Shop | Path | Oczekiwanie |
|------|------|-------------|
| sklepkleks, tcgzielona, morigal | Chromium proxy | ✅ Stabilne (guard chroni restart) |
| mepel, eduksiazka, dystryktzero | Chromium proxy/direct | ✅ Wychodzą z cooldown loop |
| xjoy, gralnia, battlestash | **Camoufox** | ✅ Auto-recovery po crashu (3x retry) |

### NODRIVER:
| Shop | Oczekiwanie |
|------|-------------|
| empik, proshop, libristo, boosterpoint | ✅ Heal w <30s (grace period) |
| tantis, strefamarzen | ✅ Powrót do normalnych skanów |
| mediaexpert | ✅ SCAN_DELAY=25s (szybki poll) |

### Torpedo:
- ✅ Bez hourly restart (warmer nie koliduje)
- ✅ Health alert jeśli 0 staged > 10min
- ✅ Self-poll co 5s + heartbeat co 5min + re-stage co 30min

---

## Architektura (bez zmian, stabilizacja):

```
main.py (5 procesów)
├── FAST-1 (~59 shopów) — asyncio/aiohttp
├── FAST-2 (~59 shopów) — asyncio/aiohttp
├── SLOW (~29 shopów) — CF Bridge :8191
│   ├── CF Solver TRI-PATH:
│   │   ├── Chromium proxy (patchright): sklepkleks, tcgzielona, morigal, mepel, eduksiazka, dystryktzero
│   │   ├── Chromium direct (patchright): fallback
│   │   └── Camoufox (Firefox): gralnia, xjoy, battlestash [AUTO-RECOVERY]
│   ├── _restart_in_progress guard (no concurrent restart storms)
│   ├── Camoufox: separate semaphore(2), separate recovery
│   └── Health check: co 5min (proactive)
├── NODRIVER (7 shopów) — browser_manager [RESPAWN LOCK + GRACE]
│   └── empik, mediaexpert, proshop, boosterpoint, strefamarzen, tantis, libristo
└── ENGINES (1: tcgumisia_proxy_poller)

jc-torpedo.service (osobny daemon)
├── Self-poll co 5s (ATC = stock check)
├── Heartbeat co 5min
├── Re-stage co 30min
├── Nuclear restart gdy 0 staged > 10min
└── health_alert.py: 🔴 CRITICAL jeśli 0 staged > 10min
```

---

## Komendy:

```bash
# Deploy (po merge PR):
cd /opt/pokemon-monitor-v2 && git stash && git pull --rebase origin main && git stash pop && ./venv/bin/python3 -c "import main" && sudo systemctl restart pokemon-monitor-v2 && sudo systemctl restart jc-torpedo

# Live report:
bash infra/live_report.sh && curl -sF 'file=@/tmp/live_report.txt' https://paste.rs

# Torpedo status:
journalctl -u jc-torpedo --since "10 min ago" --no-pager | grep -E "STAGED|FIRE|restart|0/"

# CF Solver status:
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager | grep -i "camoufox\|cf_solver\|restart"
```

---

## Triggery (BEZ ZMIAN):
kartexpol, tantis, empik, smyk, japancollectibles, jc_30th, mediaexpert, strefatcg (max 1501 PLN), tcgumisia (ONLY ETB 30th < 410 PLN)

## Boty (BEZ ZMIAN):
- kartexpol, strefatcg, japancollectibles → PARALLEL
- JC Torpedo → active (self-poll, session_warmer NIE KOLIDUJE)
- tantis, empik, smyk → single account
- tcgumisia → PAUSED

## PRy w tej sesji: #54
