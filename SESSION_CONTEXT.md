# Session Context — Pokemon Monitor v2
## Last updated: 2026-08-16 07:40

---

## SESJA 2026-08-16 — Podsumowanie

### Nowy scraper: tcg-zielona.pl
- **Metoda**: WooCommerce Store API via FlareSolverr (API za Cloudflare z VPS IP)
- **Endpoint**: `/wp-json/wc/store/v1/products?category=pokemon-tcg`
- **Produkty**: 17 (30th Celebration, Destined Rivals ETB — wszystkie preorder/niedostępne)
- **Grupa**: SLOW (dodany do SLOW_SHOPS w main.py, bo FlareSolverr)
- **Plik**: `shops/tcgzielona.py`
- **Uwaga**: Z sandboxa API działa BEZ CF, ale z VPS daje 403 — MUSI iść przez FlareSolverr
- **proxy_router.py**: `tcg-zielona` jest w SHOP_REQUIRES_FLARESOLVERR (linia 69) — legacy, scraper sam obsługuje

### Nowa funkcja: NEW_LISTING event (niedostępne nowe produkty)
- **Cel**: Powiadomienie na Discord gdy sklep doda nowy produkt który jeszcze nie jest dostępny (preorder/upcoming)
- **Jak**: detector.py — nowe produkty z `available=False` wysyłają event `NEW_LISTING` zamiast być cicho pomijane
- **Embed**: 📋 NOWA WRZUTKA, kolor żółty (16776960)
- **Benefit**: Wczesne przygotowanie botów zanim produkt przejdzie na available → RESTOCK
- **Pliki**: `detector.py`, `discord_sender.py`
- **Dotyczy**: WSZYSTKICH 145 sklepów (zmiana w centralnym detektorze)

### Fix: mediaexpert brak URL w powiadomieniach
- **Problem**: Selektor JS `a[href*="mediaexpert"]` nie matchował relatywnych linków (na ich stronie linki to `/gaming-i-streaming/...`)
- **Fix**: Zmieniono na `a[href*="/"]` + `link.href` (zwraca pełny absolutny URL z browsera)
- **Plik**: `shops/mediaexpert.py` (EXTRACT_JS)
- **Skutek uboczny**: `mediaexpert_trigger.py` też działał źle (abort on empty url) — teraz OK

### Fix: sklepkleks obrazki nie ładują na Discord
- **Problem**: URL obrazków zawierał unicode chars (`pokémon` z `é`) — Discord/weserv.nl nie parsowały
- **Fix**: `urllib.parse.quote()` na image URL + pełny URL-encode dla parametru weserv.nl
- **Plik**: `discord_sender.py`

### Fix: pokespot obrazki + duplikaty
- **Problem 1**: Obrazki nie ładowały na Discord (hotlink/webp issues)
- **Fix 1**: Dodano pokespot do PROXY_SHOPS (weserv.nl proxy)
- **Problem 2**: Scraper zwracał 251 produktów (wiele duplikatów, brak dedup)
- **Fix 2**: Dodano `seen = set()` z dedup po `product-id`
- **Wynik**: 251 → 112 produktów (poprawnie)
- **Pliki**: `discord_sender.py`, `shops/pokespot.py`

### Fix: health alert spam (proxy flapping)
- **Problem**: Alert "ALL PROXIES DEAD" co 2 min mimo że proxy wraca po 1-3 min (normalna fluktuacja mobile)
- **Fix 1**: Debounce — wymagane 3 consecutive fails (9+ min) zanim ogłosi DOWN
- **Fix 2**: Timeout curl 5s → 8s connect + 12s max (mobile bywa wolne)
- **Fix 3**: MIN_ALERT_INTERVAL 300s → 600s (10 min)
- **Fix 4**: Cron co 2 min → co 3 min
- **Plik**: `health_alert.py`, crontab
- **Stan**: */3 cron, debounce=3, state z fail_count polami

### Boosterland — weryfikacja
- **Status**: Działa prawidłowo, 9 produktów z kategorii `pokemon`
- **Pitch Black BB**: NIE MA na stronie (sklep go nie dodał/usunął) — nie jest bug scrapera
- **Brakujące produkty w DB** (15 vs 9): to stare usunięte produkty, DB je pamięta

### Infrastruktura — weryfikacja
- **Proxy tunnel**: ✅ HTTP 200 (0.49s)
- **Tailscale direct**: ✅ HTTP 200 (0.52s)
- **SOCKS5**: ✅ HTTP 200 (0.40s)
- **FlareSolverr**: ✅ Up 3 days
- **Tailscale ping mi-9t**: ✅ 25-41ms
- **Phone (mi-9t)**: tinyproxy ✅, autossh ✅ (2×), crond ✅, uptime 9 days
- **Mobile IP**: 37.47.128.183 (static Orange PL)

### Dokumentacja
- **RULES.md**: Wzmocniona zasada paste.rs — wynik zwrotny TEŻ ZAWSZE przez paste.rs
- **INFRASTRUCTURE.md**: Dodane role telefonów:
  - Galaxy S23 Ultra (100.67.200.62) = telefon usera, Termius + chat
  - Mi 9T (100.127.72.24) = proxy phone, dedykowany tunnel
- **Learning saved**: paste.rs workflow, device roles

---

## Stan końcowy: 145 shopów (FAST 115 + SLOW 19 + NODRIVER 10 + ENGINE 1)

### Nowe/zmienione pliki:
- `shops/tcgzielona.py` — NOWY
- `shops/mediaexpert.py` — fix URL selector
- `shops/pokespot.py` — dedup fix
- `detector.py` — NEW_LISTING event
- `discord_sender.py` — NEW_LISTING + URL-encode + pokespot proxy
- `health_alert.py` — debounce 3 fails + longer timeouts
- `main.py` — tcg-zielona w SLOW_SHOPS
- `RULES.md` — paste.rs workflow
- `INFRASTRUCTURE.md` — phone roles + topology

---

## ZASADY SCRAPERÓW:

1. **SEALED ENGLISH ONLY** — booster boxes, ETBs, tins, collections, blisters, bundles
2. **DOSTĘPNOŚĆ** — testuj na live site, użyj "koszyk"/"dodaj" jako primary indicator
3. **RESTOCKI + ZMIANY CEN** — muszą działać (wykrywać przejścia available false→true)
4. **OBRAZKI NA DISCORD** — testuj HTTP HEAD, dodaj do weserv.nl proxy jeśli 403/timeout/unicode
5. **SZYBKO, STABILNIE, BEZ BANÓW** — API-first, max 6-10 req/min per shop, proxy jeśli rate limit
6. **PRODUKTY DO AKCEPTACJI** — ZAWSZE pokaż userowi listę PRZED deploy
7. **EXCLUDE KOMPLETNY** — decks, JP/KR/CHI, accessories, other games, LEGO, gry planszowe, singles
8. **FILTR CENOWY** — <10 PLN = single, wycinaj
9. **TESTUJ NA VPS** — nie sandbox (inny IP, proxy, CF)
10. **NEW_LISTING** — powiadomienie o nowych niedostępnych produktach (preorder/upcoming) na Discord

---

## TODO następna sesja:

### Nowe scrapery (z listy usera):
libristo.pl, plastiq.pl, moriqal.pl, eduksiazka.pl, loficards.pl, dystryktzero,
kiddin, gralnia.pl, maginarium, monsteriada, abondegames.pl, archivebyx.com,
xjoy.pl, mepel.pl

### Boty:
- bookland.pl — autobuy bot (scraper gotowy)
- mediaexpert — seller filtering jeśli marketplace wróci

### Infra:
- Automatyzacja IP reset (Android airplane mode) — Orange PL = static, nie pomaga
- bonito.pl (IP banned, czeka na drugą SIM z dynamicznym IP)
- Druga SIM (Play/T-Mobile) w Mi 9T dla dynamicznego IP
