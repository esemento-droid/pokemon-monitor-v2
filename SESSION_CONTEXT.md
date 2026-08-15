# Session Context — Pokemon Monitor v2
## Last updated: 2026-08-15 13:20

---

## SESJA 2026-08-15 — Podsumowanie

### Image Fixy (21 shopów z listy):
- **PR #12**: 12 scraperów (relative URLs, złe selektory, brak ekstrakcji)
- **PR #13**: bookland (403 CDN params), gameover (404 data-src), pikashop (hotlink→weserv.nl)
- **PR #14**: weserv.nl proxy dla 16 shopów w discord_sender.py + jaskiniatrolla availability
- Shops z proxy: pikashop, bookland, gameover, basanti, cardwolf, aleplanszowki, dragoneye, twojekarty, poketrader, missaga, karcianybunkier, magiccafe, hearts, jaskiniatrolla, piwniczaki, sklepkleks

### Nowy scraper:
- **sklepkleks.com** — FlareSolverr, 17 sealed, SLOW group, exclude: labyrinth

### Empik exclude fix:
- Dodane: `" jap"` (łapie JAP na końcu), `"kollection"`, `"portfolio"`, `"binder"`, `"talia"`

### Tcgumisia rate limit fix:
- WYŁĄCZONY engine (3s same IP = 429 spam, powodował 56→14→0 skoków)
- DODANY proxy poller: engines/tcgumisia_proxy_poller.py (mobile IP, /pre-order, 10s)
- Teraz: HTML scraper (VPS IP, /pokemon) + proxy poller (mobile IP, /pre-order) = zero 429

### Hearts availability fix:
- Bug: `"brak towar"` nigdy nie matchowało → `"brak"` 

### Swiatkart availability fix:
- Bug: avail_tag selector nie istniał → zawsze available=True
- Fix: "koszyk"/"dodaj" = available, "brak"/"niedost" = unavailable
- Przeniesiony z SLOW do FAST (5-15s zamiast 45-90s)

### Re-enabled scrapers (4):
- **strefakart** — przepisany na WooCommerce API + mobile proxy (FAST, 247 produktów)
- **battlestash** — FlareSolverr (SLOW, 32 produktów)
- **strefamtg** — FlareSolverr + filtr pokemon (SLOW, ~105 produktów)
- **mediaexpert** — nodriver + mobile proxy (NODRIVER, 7 produktów)

### Stan końcowy: 140 sklepów (FAST 111 + SLOW 19 + NODRIVER 10)

---

## ZASADY SCRAPERÓW:

1. **SEALED ENGLISH ONLY** — booster boxes, ETBs, tins, collections, blisters, bundles
2. **DOSTĘPNOŚĆ** — testuj na live site, użyj "koszyk"/"dodaj" jako primary indicator
3. **RESTOCKI + ZMIANY CEN** — muszą działać (wykrywać przejścia available false→true)
4. **OBRAZKI NA DISCORD** — testuj HTTP HEAD, dodaj do weserv.nl proxy jeśli 403/timeout
5. **SZYBKO, STABILNIE, BEZ BANÓW** — API-first, max 6-10 req/min per shop, proxy jeśli rate limit
6. **PRODUKTY DO AKCEPTACJI** — ZAWSZE pokaż userowi listę PRZED deploy
7. **EXCLUDE KOMPLETNY** — decks, JP/KR/CHI, accessories, other games, LEGO, gry planszowe, singles
8. **FILTR CENOWY** — <10 PLN = single, wycinaj
9. **TESTUJ NA VPS** — nie sandbox (inny IP, proxy, CF)

---

## TODO następna sesja:

### Nowe scrapery (z listy usera):
libristo.pl, plastiq.pl, moriqal.pl, eduksiazka.pl, loficards.pl, dystryktzero, 
kiddin, gralnia.pl, maginarium, monsteriada, abondegames.pl, archivebyx.com, 
xjoy.pl, mepel.pl, strefakart (duplikat — już done)

### Boty:
- bookland.pl — autobuy bot (scraper gotowy)
- mediaexpert — seller filtering jeśli marketplace wróci

### Infra:
- Automatyzacja IP reset (Android airplane mode)
- bonito.pl (IP banned, czeka na reset)
