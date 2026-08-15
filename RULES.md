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
- NIGDY nie wklejaj komend bezpośrednio w tekst odpowiedzi
- ZAWSZE upload do paste.rs i daj URL
- Output z VPS MUSI iść do paste.rs (user nie może kopiować z terminala)
- Nawet proste komendy — ZAWSZE przez paste.rs
- Żeby zobaczyć wynik: `curl -sL paste.rs/WYNIK_URL`

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
