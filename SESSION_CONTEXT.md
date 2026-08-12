# Session Context — Pokemon Monitor v2
## Last updated: 2026-08-12 19:40

---

## SESSION 2026-08-12: Bulletproof Proxy + PRO Bot Upgrades

### Trigger: JapanCollectibles restock at 14:09 — bot FAILED (0/4) 
**Root cause:** tinyproxy on mi-9t died, autossh tunnel was forwarding empty port.
Bot got `ERR_PROXY_CONNECTION_FAILED` on all 4 accounts.

### What was built:

#### Infrastructure — BULLETPROOF PROXY SYSTEM
| Component | Status | Details |
|-----------|--------|---------|
| Tailscale VPS ↔ mi-9t | ✅ | VPS: 100.100.246.13, Phone: 100.127.72.24 |
| 4 proxy paths | ✅ | tunnel, tailscale, socks5, direct — ALL tested on japancollectibles.shop |
| VPS watchdog (cron 1min) | ✅ | Tailscale SSH fallback to phone |
| Phone watchdog (cron 1min) | ✅ | Restarts tinyproxy + autossh |
| Phone boot script | ✅ | Termux:Boot auto-starts everything |
| Wake-lock | ✅ | Prevents Android Doze kill |
| FlareSolverr (Docker) | ✅ | v3.5.0 port 8191, CF managed bypass |
| SOCKS5 proxy (port 1080) | ✅ | SSH dynamic forwarding via Tailscale |
| IP rotation script | ⚠️ | Script works, airplane mode toggles, but Orange PL gives static IP in CGNAT |
| Health alerts (Discord) | ✅ | Alerts ONLY on state change (down/up), no spam |

#### Bot Upgrades — ALL BOTS NOW HAVE:
| Feature | Details |
|---------|---------|
| proxy_router.py | Smart per-account proxy selection |
| bot_engine.py | Shared logic: humanizer, retry, fingerprint, cookies |
| solver.py | Universal challenge solver (CF, CAPTCHA, rate-limit, IP ban) |
| session_warmer.py | Pre-warm cookies every hour (saves 15-20s on drop) |
| turbo_mode.py | Cross-shop turbo polling on restock |
| Per-account fingerprint | Unique viewport/UA/locale per account |
| Proxy fallback | If proxy dead → switch path → never 0/4 again |
| Humanizer delay | 12-25s random between accounts (was 2s!) |

#### Bot Status:
| Bot | Upgraded | Platform |
|-----|----------|----------|
| tcgumisia_autobuy | ✅ Full (bot_engine) | Sellingo |
| japancollectibles_autobuy | ✅ (proxy_router) | Sky-Shop |
| kartexpol_autobuy | ✅ (bot_engine) | Shoper |
| strefatcg_autobuy | ✅ (bot_engine) | Shoper |
| smyk_autobuy | ✅ (bot_engine) | SMYK custom |
| tantis_autobuy | ✅ (proxy_router) | WooCommerce+CF |
| empik_autobuy | ✅ (proxy_url for nodriver) | Empik/nodriver |
| mediaexpert_autobuy | ⚠️ Not upgraded yet | nodriver |

#### Test Result:
- **tcgumisia test order SUCCESS** — Marian Wasilewski, 30th 2-Pack 90 PLN
- Full flow: login → ATC → InPost → BLIK → "Zamawiam" → tpay.com redirect ✅
- Time: ~2 min with login, ~45s with pre-warmed cookies

#### Cleanup:
- 268,841 lines deleted (30+ old/unused files)
- Repo clean: only active code remains

---

## CRON JOBS (VPS):
| Interval | Job |
|----------|-----|
| * * * * * | proxy_watchdog.sh (auto-heal via Tailscale) |
| */2 * * * * | health_alert.py (Discord on critical failures) |
| */5 * * * * | start_socks5.sh (ensure SOCKS5 alive) |
| */5 * * * * | docker start flaresolverr |
| 0 * * * * | session_warmer.py (refresh cookies for all accounts) |

## CRON JOBS (mi-9t phone):
| Interval | Job |
|----------|-----|
| * * * * * | watchdog.sh (tinyproxy + autossh + wake-lock) |
| 0 */4 * * * | rotate_ip.sh (airplane mode — won't change IP on Orange) |

---

## PROXY POOL:
| Name | URL | Type | IP |
|------|-----|------|-----|
| mobile_tunnel | http://127.0.0.1:8888 | HTTP | 37.47.128.183 (Orange mobile) |
| mobile_tailscale | http://100.127.72.24:8888 | HTTP | 37.47.128.183 |
| mobile_socks | socks5://127.0.0.1:1080 | SOCKS5 | 37.47.128.183 |
| direct | None | Direct | 146.59.45.228 (VPS IPv4) |
| flaresolverr | http://localhost:8191 | CF bypass | N/A |

## PER-ACCOUNT ROUTING:
| Account | Primary proxy |
|---------|---------------|
| esemento@ | mobile_tunnel |
| blackmat36@ | mobile_socks |
| tjbtaniojuzbylo@ | mobile_tailscale |
| y24015411@ | direct (VPS) |

---

## AKTYWNE BOTY AUTO-BUY:
Same triggers as before, now with proxy_router + fingerprint + retry + cookies.
All 7 triggers in detector.py fire correctly (confirmed via tcgumisia test).

---

## Git Branch: infra/bulletproof-proxy (PR #9)
All changes merged to main on VPS. GitHub PR open for review.

## Files Added This Session:
- proxy_router.py, solver.py, bot_engine.py, session_warmer.py
- turbo_mode.py, health_alert.py
- check_proxy.sh, start_socks5.sh, rotate_mobile_ip.sh, proxy_watchdog.sh
- infra/deploy_vps.sh, infra/deploy_phone.sh, infra/README.md
- sanitize.py (restored after accidental deletion)

---

## KNOWN ISSUES:
1. IP rotation doesn't change IP (Orange PL static CGNAT) — need residential proxy or different SIM
2. mediaexpert_autobuy.py not yet upgraded to proxy_router
3. Session warmer hasn't done full cycle yet (first run was test only)
4. turbo_mode.py written but NOT yet wired into detector.py
5. All 4 proxy paths give SAME mobile IP (37.47.128.183) — only "direct" is different (VPS)
