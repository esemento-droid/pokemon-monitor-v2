# Pokemon Monitor v2 - Stan 29.07.2026 (po refaktorze)

## ARCHITEKTURA: SUBPROCESS (Netflix-style)
- orchestrator.py → spawni runner.py jako osobne procesy
- ProcessPoolExecutor(max_workers=15)
- Każdy scraper = osobny proces, osobny GIL, zero blokowania
- PostgreSQL (asyncpg, pool 2-10 connections)
- Discord: fire-and-forget queue (send_nowait)
- Systemd: ExecStart=orchestrator.py

## BAZA DANYCH: PostgreSQL
- Host: localhost
- User: pokemonitor / Pass: mon2026pg / DB: pokemonitor
- Tabele: products (id+shop PK), shop_state (snapshot_done, last_scan, scan_count, error_count)
- Stary SQLite: /opt/pokemon-monitor-v2/data/products.db (backup)

## WYNIKI: avg 4s, 0 errors, 1200+ scans/10min

## PLIKI GLOWNE:
- orchestrator.py - planuje i odpala procesy (max 15 concurrent)
- runner.py - uruchamia JEDEN scraper, detect, save, exit
- database.py - asyncpg PostgreSQL pool
- discord_sender.py - fire-and-forget queue
- detector.py - send_nowait (nie blokuje)
- config.py - CHECK_MIN=5, CHECK_MAX=20, TIMEOUT=90
- sanitize.py - walidacja typow

## AKTYWNE SCRAPERY (93):
API (WC Store): boosterland, pokepaka, kryptakart, pokenest, hejmistrzu, battlestash, dropnews, perfectblue, tubacards, colligere, paladynat, pokeverse
API (inne): gnom(GraphQL), mugiwara(Ecwid), juniorkurczak(Ecwid), rozetka(REST), foon(AJAX)
Shoper turbo: kartomaniak, kupteraz, pokebeast, carddojo, futurex, tcglove, lukillo, cardfan, mrpuggy, kartomat, tcgtrener, canislupus, arena, time4magic, bastacentershop, panmysza, pokecollect, mycards, alpakagra, grybezpradu, tcgheaven, kantodrop
Shoper old: przyczolek
PrestaShop: poketeka, vanaheim, epiccard, trolle3, hobbity, aleplanszowki, pegazgry
Custom: artshock, ataf, czytam, lochyikoty, zaurketto, xzone, truecollector, fanbase, matfel, mironet, rozmaitosci, pokeelite, strefatcg, tcgumisia, hms, smyk, stapis, taniaksiazka, moriongames, granaczas, redraft, magplanszowy, pokemaniak, pokespot, tcghobby, japancollectibles, graal, poketrader, pikaspace, gamiq, planszoklocki
Playwright: basanti, blindbox, dragonus, dvdmax, flamberg, hearts, pikashop, piwniczaki, tantis, wilczek
Sync: kuzniakart
Inne: missaga, pokesmart

## DISABLED (Shopify Cloudflare - czekaja na proxy):
skladgier, pokelab, pokeloot, planetaprezent

## KERNEL TUNING:
net.core.somaxconn=4096
net.ipv4.tcp_max_syn_backlog=4096
net.ipv4.ip_local_port_range=1024 65535
net.ipv4.tcp_tw_reuse=1
net.ipv4.tcp_fin_timeout=15

## TODO:
1. Mobile proxy → odblokuje Shopify (skladgier, pokelab, pokeloot, planetaprezent)
2. mrpuggy: dynamiczna paginacja (teraz hardcoded 27 stron, batch-5)
3. Nowe scrapery: drop .py do shops/ i orchestrator automatycznie je znajdzie
4. Autobuyer dla mediaexpert (po proxy)
