# Zasady Pracy — Pokemon Monitor v2

## ⚠️ KRYTYCZNE — NIE ŁAMAĆ NIGDY

### 1. NIGDY nie usuwaj plików bez sprawdzenia importów
```bash
grep -rn "filename" *.py main.py detector.py
```
- Usunięcie sanitize.py wyłożyło CAŁY monitor na produkcji (sesja 2026-08-12)
- Przed usunięciem CZEGOKOLWIEK — ZAWSZE sprawdź co tego importuje
- NIGDY nie zakładaj że plik jest "niepotrzebny" bo nie wiesz co go importuje

### 2. NIGDY nie edytuj produkcyjnych plików sedem/automatycznie
- detector.py, main.py — NIGDY sed na produkcji
- Sesja 2026-08-14: sed usunął '# DISABLED:' ale zepsuł indentację (24 spacji → 0) = SyntaxError
- Wymagało 3 dodatkowych fix komend
- Jeśli trzeba uncommentować — precyzyjny sed z DOKŁADNYM wzorcem spacji lub pełny patch

### 3. NIGDY nie rób cleanup/refactor na PRODUKCJI jednocześnie z wdrożeniem features
- To DWIE OSOBNE operacje
- Najpierw feature → test → deploy
- Potem (osobna sesja) cleanup → test → deploy

### 4. Przed KAŻDYM restartem monitora:
```bash
./venv/bin/python3 -c "import main"
```
- Jeśli fail → **NIE restartuj!**
- Sprawdź syntax, imports, dependencies

### 5. NIGDY nie modyfikuj istniejącego działającego kodu "przy okazji"
- Jeśli mówię "dodaję TYLKO nowe pliki" — to MUSI być prawda dosłownie
- NOWE = NOWE, STARE = NIE RUSZAĆ
- Jeśli chcę zmienić/usunąć coś starego → PYTAM USERA WPROST → osobna operacja po potwierdzeniu
- ZERO tolerancji na "ulepszenia" działającego kodu

### 5a. JAK COŚ SIĘ JEBIE — ZACZYNAJ OD SWOJEJ ZMIANY!
- **PIERWSZA rzecz do sprawdzenia**: co JA zmieniłem w tej sesji?
- Jeśli zmiana koreluje z problemem → **COFNIJ OD RAZU**, nie szukaj winy gdzie indziej
- NIE zakładaj że "sieć padła", "Android Doze", "Orange NAT" — to TY mogłeś rozjebać
- Sesja 2026-08-15: zmiana `ClientAliveInterval 120→15` rozjebała proxy. 3 godziny szukania winnego w sieci, telefonie, Doze mode — a to moja zmiana w sshd_config
- **ZASADA**: Jeśli coś działało przed sesją a teraz nie → problem jest w TYM co zmieniłeś. Cofnij. Potwierdź że wraca. Dopiero potem szukaj dalej.

### 6. NIGDY nie zmieniaj kodu triggerów/botów co DZIAŁA
- Nawet jeśli widzisz "lepszy" sposób — jeśli działa, NIE RUSZAJ
- Jedyne dozwolone zmiany:
  - Nowe pliki (nie edycja istniejących)
  - Bug fixy TYLKO gdy coś crashuje na live (minimalna zmiana — jedna linia, nie refactor)

---

## 📱 Workflow z Userem (Termius Mobile)

### paste.rs — ABSOLUTNY PRIORYTET
User pracuje na telefonie przez Termius — NIE MOŻE kopiować komend z chatu.

**OBOWIĄZKOWY PATTERN:**
```
Komenda IN:  curl -sL paste.rs/XXXXX | bash
Output OUT:  2>&1 | curl -s --data-binary @- https://paste.rs/
```

**Pełny format:**
```bash
curl -sL paste.rs/XXXXX | bash 2>&1 | curl -s --data-binary @- https://paste.rs/
```

**ZASADY:**
- NIGDY nie wklejaj komend bezpośrednio w tekst odpowiedzi — ZAWSZE upload do paste.rs i daj URL
- Output z VPS MUSI iść do paste.rs (user nie może kopiować z terminala)
- WYNIK ZWROTNY TEŻ PRZEZ paste.rs — user wkleja URL paste z outputem do chatu
- Nawet proste komendy — ZAWSZE przez paste.rs
- Żeby zobaczyć wynik: `curl -sL paste.rs/WYNIK_URL`
- Format dla usera: `curl -sL paste.rs/XXXXX | bash 2>&1 | curl -s --data-binary @- https://paste.rs/`
- User kopiuje WYNIKOWY URL paste.rs i wkleja do chatu — to jedyny sposób komunikacji wyników

---

## 🛒 Zasady Scraperów

### Przed deploy NOWEGO scrapera lub ZMIAN w exclude:
1. Odpal scraper ręcznie
2. Pokaż userowi PEŁNĄ listę produktów
3. Poczekaj na potwierdzenie/korekty exclude
4. DOPIERO WTEDY deploy + restart monitora

**User MUSI zobaczyć co scraper łapie zanim pójdzie live. NIGDY nie deployować bez weryfikacji.**

### Co scraper MUSI robić:
1. Łapać WSZYSTKIE angielskie sealed Pokemon TCG (booster boxes, ETBs, tins, collections, blisters, bundles, mini tins, UPCs)
2. Prawidłowo wykrywać DOSTĘPNOŚĆ — testuj na live site (koszyk/dodaj = available, brak/niedost = unavailable)
3. Wykrywać RESTOCKI (przejście unavailable→available) i ZMIANY CEN
4. Mieć OBRAZKI które wyświetlają się na Discord (testuj HTTP HEAD, weserv.nl proxy jeśli 403)
5. Być SZYBKI i STABILNY — API-first, max 6-10 req/min, proxy jeśli rate limit
6. EXCLUDE kompletny od startu (decks, JP/KR/CHI, accessories, other games, junk)
7. Filtr cenowy: <10 PLN = single → wycinaj
8. Testuj na VPS (nie sandbox) — inny IP, proxy, CF zachowują się inaczej

### EXCLUDE POLICY (per-shop, NIE centralna!):
User odrzucił centralną listę — każdy shop ma INDYWIDUALNY exclude (różny inventory/naming).

**Wymagane kategorie w KAŻDYM scraperze:**

| Kategoria | Słowa kluczowe |
|-----------|----------------|
| DECKS | battle deck, league battle, rival battle, v battle, world championship, wcs deck, battle academy |
| FOREIGN | japoński, japońsk, japanese, (jp), koreański, korean, chiński, chinese, (chi), s-chinese |
| ACCESSORIES | ultra pro, ultra-pro, playmat, portfolio, pro-binder, **sleeves** (plural!), toploader, album, koszulk, segregator, deck box, alcove |
| OTHER GAMES | lorcana, one piece, yu-gi-oh, digimon, naruto, star wars, magic the gathering, flesh & blood, dragon shield, weiss schwarz, force of will, riftbound |
| JUNK | zeszyt, puzzle, figurk, figure set |

### ⚠️ KRYTYCZNE EXCLUDE PUŁAPKI:
- **NIGDY "sleeve"** (singular) — łapie "Sleeved Booster" = sealed angielski produkt!
  - Używaj **"sleeves"** (plural = akcesorium)
- **NIGDY "binder"** (sam) — łapie "Binder Collection" = zestaw z boosterami!
  - Używaj **"pro-binder"** (łapie tylko albumy Ultra Pro)
- Binder Collection = borderline (zawiera boostery ale jest albumem) — NOT excluded globally

---

## 🤖 Zasady Botów

### Gdy mówię co zmieniam — musi być PRAWDA dosłownie:
- "Tylko dodaję nowe linie" = DOSŁOWNIE tylko nowe linie
- Jeśli zmieniam logikę flow → mówię wprost: "zmieniam X na Y, efekt: Z"
- NIGDY nie ukrywam zakresu zmian

### --test flag:
- = użyj konta testowego (Marian Wasilewski)
- = zamówienie jest REALNE (nie dry-run!)
- Bot przechodzi CAŁY flow i klika finalne potwierdzenie
- NIE odpalać konta testowego w trybie "produkcyjnym"

### Strefatcg trigger:
- Zakomentowany w detector.py od 2026-08-12 22:49
- NIE odblokować bez wyraźnej prośby usera
- max_price = 1580 PLN

---

## 🔧 Deploy & Git

### Push workflow:
1. Push z sandbox (Kiro ma auth via gateway)
2. Na VPS: `git pull` (credential helper: `!gh auth git-credential`, BEZ sudo)
3. NIGDY push bezpośrednio na main — zawsze branch + PR

### Deploy na VPS:
```bash
cd /opt/pokemon-monitor-v2
git stash                        # local edits
git pull --rebase origin main
git stash pop                    # re-apply local edits
./venv/bin/python3 -c "import main"   # TEST FIRST!
sudo systemctl restart pokemon-monitor-v2
sudo systemctl restart discord-router
```

### Jeśli VPS ma dirty working tree:
```bash
git stash
git pull --rebase origin main
git stash pop
```

---

## 📋 Misc Rules

### Env variable trap:
```python
# ❌ CRASH gdy DISPLAY już w env:
dict(**os.environ, DISPLAY=':99')

# ✅ POPRAWNIE:
{**os.environ, 'DISPLAY': ':99'}
```

### Price change filter:
- < 5 PLN AND < 3% = silent (logged to DB only, no Discord/triggers)
- Eliminuje micro-zmiany cenowe (grosze)

### Empik marketplace:
- Marketplace products tracked with available=True (Discord notifications)
- Bot trigger filters by stock='empik' ONLY (nie kupuj marketplace)

### LEGO routing:
- LEGO_SHOPS = {"limango", "taniaksiazka_lego"} → kategoria "🧱 LEGO"
- FOREIGN_SHOPS = {"efantasy"} → kategoria "🌍 Zagraniczne"



---

## 🚀 ŻELAZNA ZASADA SCRAPERÓW — QUALITY STANDARD

Każdy scraper MUSI spełniać WSZYSTKIE poniższe kryteria. Bez wyjątków. Nie idziemy dalej dopóki nie działa.

### OBOWIĄZKOWE (nie negocjowalne):

| # | Kryterium | Wymóg |
|---|-----------|-------|
| 1 | **CENA** | MUSI być. Nigdy "brak". Szukaj: GA4 dataLayer, JSON w HTML, /wp-json/, /webapi/, API endpoint, strona produktu. |
| 2 | **OBRAZEK** | MUSI się wyświetlać na Discord. Testuj HTTP HEAD. Jeśli 403/timeout → weserv.nl proxy. |
| 3 | **LINK** | Prawidłowy URL do produktu. Musi prowadzić do właściwej strony. |
| 4 | **STOCK** | MUSI zgadzać się ze stroną. Testuj na live: koszyk/dodaj = available, brak/niedost = unavailable. |
| 5 | **RESTOCK** | Przejście OUT→AVAIL MUSI triggerować Discord alert. |
| 6 | **NOWY PRODUKT** | Nowy produkt MUSI triggerować Discord alert. |
| 7 | **ZMIANA CENY** | Zmiana ceny (>5 PLN i >3%) MUSI triggerować alert. |

### SZYBKOŚĆ — priorytet metod (od najszybszej):

1. **API endpoint** (WooCommerce /wp-json/, Shoper /webapi/, Shopify /products.json, Sellingo /ajax/)
2. **JSON w HTML** (GA4 dataLayer items, embedded product JSON, script tags)
3. **aiohttp + BeautifulSoup** (czysty HTTP, brak JS)
4. **FlareSolverr** (dla Cloudflare)
5. **nodriver/patchright** (last resort — wolne, zasobożerne)

### STABILNOŚĆ:

- Retry na timeout (min 2 próby)
- Nie padać na jednym errorze
- Max 6-10 req/min per shop (nie bombardować)
- Proxy jeśli rate limit/ban

### PROCESS budowania nowego scrapera:

1. **Rozpoznanie** (30s):
   - Sprawdź platformę: view-source, generator meta, URL patterns
   - Platformy: WooCommerce (`/wp-json/`), Shoper (`/webapi/`, `,id*.html`), PrestaShop, Sky-Shop (`/api/`), Shopify (`/products.json`), osCommerce (`-c-`, `-p-`), IdoSell, RedCart, custom
   
2. **Szukaj API** (priorytet!):
   - WooCommerce: `curl /wp-json/wc/store/v1/products?per_page=1`
   - Shoper: `curl /webapi/front/products?limit=1`
   - Shopify: `curl /products.json?limit=1`
   - Sky-Shop: `curl /api/products?limit=1` (uwaga: może zwrócić stronę z docs)
   - Szukaj też: GA4 dataLayer, JSON w `<script>` tagach

3. **Test CF/blokady z VPS**:
   - Direct curl z VPS: jeśli 403 "Just a moment" → CF
   - Via proxy (127.0.0.1:8888): jeśli też 403 → FlareSolverr
   - FlareSolverr: jeśli przejdzie → SLOW group
   - FlareSolverr fail → nodriver (NODRIVER group)
   - **UWAGA**: sandbox IP ≠ VPS IP! Scraper może działać w sandbox ale fail na VPS!

4. **Parallel fetch** (gdy wiele stron):
   - ZAWSZE `asyncio.gather()` na stronach zamiast sekwencyjnego loop+sleep
   - Eliminuje timeouty (7 stron: 48s sequential → 0.3s parallel)
   - Limit: max 10 concurrent requests per shop

5. **Parsowanie — pułapki**:
   - Cena 0 / brak ceny → `price = "brak"`, `available = False` (preorder)
   - Relatywne URL → dodaj BASE_URL prefix
   - `img alt` może nie zawierać nazwy → fallback na `stripped_strings`, `link title`
   - Unicode w URL obrazków (é, ó) → `urllib.parse.quote()` w discord_sender
   - `.href` (absolute) vs `.getAttribute('href')` (relative) w nodriver/JS

6. **Dostępność — jak sprawdzić**:
   - "koszyk", "dodaj", "add to cart" = available
   - "niedost", "brak", "wyprzedane", "wycofan" = unavailable
   - Cena 0 bez buttona "dodaj" = unavailable (preorder)
   - `is_in_stock` w WooCommerce API
   - TESTUJ NA LIVE SITE przed deploy!

7. **Obrazki — checklist**:
   - HTTP HEAD → 200 + image content-type = OK
   - 403/timeout → dodaj shop do PROXY_SHOPS w discord_sender (weserv.nl)
   - Unicode w URL → quote() automatycznie (naprawione w discord_sender.py)
   - `.webp` format → Discord obsługuje, ale hotlink protection może blokować

8. **Deploy flow**:
   - Test na VPS via paste.rs
   - Pokaż pełną listę userowi
   - User akceptuje → git push → pull na VPS → restart
   - Dodaj do odpowiedniej grupy: FAST (default), SLOW_SHOPS (FlareSolverr), NODRIVER_SHOPS (Chrome)

### Grupy procesów — kiedy co:

| Metoda | Grupa | Dodaj do | Delay |
|--------|-------|----------|-------|
| aiohttp (HTTP/API) | FAST | (default, nie dodawaj nigdzie) | 5-15s |
| FlareSolverr | SLOW | `SLOW_SHOPS` w main.py | 45-120s |
| nodriver (Chrome) | NODRIVER | `NODRIVER_SHOPS` w main.py | subprocess via runner.py |
| Shopify /products.json | SLOW | `SHOPIFY_SHOPS` w main.py | 45-120s |

### Lessons learned (sesja 2026-08-16):

- **tcg-zielona**: API endpoint z sandboxa działa, z VPS = CF 403. ZAWSZE testuj na VPS!
- **libristo**: FlareSolverr nie przechodzi ich CF, tylko nodriver. Sprawdź obie opcje.
- **morigal**: osCommerce z `data-id`, `data-name`, `data-price` w atrybutach `<a>` — super łatwe parsowanie
- **pokespot**: brak `seen_ids` = duplikaty (251→112). ZAWSZE dedup.
- **loficards**: sekwencyjny fetch 7 stron = timeout. Parallel = 0.3s.
- **mediaexpert**: relatywne href + `getAttribute('href')` → pusty URL. Użyj `.href` w JS.

### NIE ODPUSZCZAJ:

- Jeśli cena nie jest na listingu → szukaj w API/JSON/dataLayer/product page
- Jeśli obrazek daje 403 → dodaj do weserv.nl proxy
- Jeśli CF blokuje → FlareSolverr/proxy/WARP
- Jeśli scraper daje 0 → debug natychmiast, nie "zostawiaj na później"
- Jeśli proxy pada → napraw, nie omijaj



---

## 🔒 INFRASTRUKTURA — CO DZIAŁA, NIE RUSZAĆ

### Mobile Proxy (127.0.0.1:8888)

**Stan: DZIAŁA STABILNIE. NIE RUSZAĆ.**

| Element | Wartość | NIE ZMIENIAJ |
|---------|---------|--------------|
| VPS sshd ClientAliveInterval | **120** | Było 120, działa. Zmiana na 15 rozjebała wszystko. |
| VPS sshd ClientAliveCountMax | **3** | Było 3, działa. |
| Phone autossh ServerAliveInterval | **30** | Sprawdzone, stabilne |
| Phone autossh ServerAliveCountMax | **3** | Sprawdzone, stabilne |
| Phone tinyproxy | 0.0.0.0:8888 (all interfaces) | Nasłuchuje na Tailscale + localhost |
| Reverse tunnel | `-R 8888:127.0.0.1:8888` | Z telefonu do VPS |
| Watchdog | v2 (proxy_watchdog.sh) | Cron co 1 min, 3-tier repair |
| Failsafe | Tailscale direct (100.127.72.24:8888) | Fallback gdy tunnel martwy |

**Jak to działa:**
1. Telefon (Termux) → autossh → reverse tunnel → VPS port 8888
2. Scrapery łączą się na 127.0.0.1:8888 → tunnel → tinyproxy → mobile IP
3. Jeśli tunnel padnie → watchdog (co 1 min) naprawia:
   - Tier 1: Tailscale direct OK? → restart autossh na telefonie
   - Tier 2: Tailscale dead? → full repair (restart tinyproxy + autossh)
   - Tier 3: Phone unreachable → log, exit

**CO NIE WOLNO ZMIENIAĆ:**
- sshd_config (ClientAlive*) — NIGDY
- proxy_watchdog.sh — NIGDY bez powodu
- autossh parametry na telefonie — NIGDY
- Architektura (reverse tunnel) — NIGDY "bo socat byłby lepszy"

### FlareSolverr
- Docker container, port 8191
- Stabilny (up days)
- Używany przez: battlestash, sklepkleks, strefamtg, empik

### Tailscale
- VPS: 100.100.246.13
- Mi 9T: 100.127.72.24 (direct 37.47.128.183:5175)
- ZAWSZE stabilny — mesh VPN, auto-reconnect

### SOCKS5 (127.0.0.1:1080)
- SSH dynamic forward przez Tailscale
- Cron co 5 min (start_socks5.sh)
- Używany przez boty autobuy

### Xvfb
- Display :99
- Wymagany przez nodriver/patchright (headless=False)
- DISPLAY=:99 w systemd env

---

## ⚡ DEBUGGING PROTOCOL

Kiedy coś się jebie na produkcji:

```
1. CO ZMIENIŁEM W TEJ SESJI?
   → Lista zmian (pliki, config, komendy)
   → Czy problem koreluje z moją zmianą?
   → TAK → COFNIJ OD RAZU. Nie szukaj dalej.

2. Dopiero jak cofnięcie NIE pomaga:
   → Sprawdź logi (journalctl --since "5 min ago")
   → Sprawdź procesy (ps aux, ss -tlnp)
   → Sprawdź connectivity (ping, curl)

3. NIGDY nie zakładaj przyczyny bez dowodu:
   ❌ "To pewnie sieć Orange"
   ❌ "Android Doze zabija"
   ❌ "NAT timeout"
   ✅ "Zmieniłem X, od tego momentu pada"
```
