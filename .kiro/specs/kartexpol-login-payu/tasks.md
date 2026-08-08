# Implementation Plan: Kartexpol Login + PayU (Przelewy24)

## Overview

Rewrite the Kartexpol auto-buy bot from guest-checkout aiohttp API to login-based Patchright browser automation with Przelewy24/BLIK payment redirect. The implementation follows the proven Strefa-TCG bot architecture (`strefatcg_autobuy.py`) since both sites run on the same Shoper platform. Three files are affected: `kartexpol_autobuy.py` (complete rewrite), `kartexpol_trigger.py` (rewrite to batch pattern), and a new test file `tests/test_kartexpol_properties.py`.

## Tasks

- [ ] 1. Implement core utilities and completed tracker in kartexpol_autobuy.py
  - [ ] 1.1 Create the new `kartexpol_autobuy.py` with imports, constants, account configuration, and completed tracker functions (`load_completed`, `save_completed`, `is_completed`, `mark_completed`)
    - Import asyncio, sys, os, json, logging, re, time, argparse, Path, patchright
    - Define BASE_URL = "https://www.kartexpol.pl", BOT_DIR, COMPLETED_FILE, LOG_FILE, WEBHOOK_FILE paths
    - Define ACCOUNTS list (4 production accounts with email, password placeholder, name)
    - Define TEST_ACCOUNT (t11008543@gmail.com)
    - Implement `load_completed()`: read JSON file, return {} if missing or malformed
    - Implement `save_completed(data)`: write dict to JSON with indent=2
    - Implement `is_completed(product_id, email)`: check if email in completed[product_id]
    - Implement `mark_completed(product_id, email)`: add email to completed[product_id] and save
    - Implement `send_discord(message)`: read webhook URL from file, POST with aiohttp, log warning on failure
    - Set up dual logging (stdout + file) matching strefatcg_autobuy.py pattern
    - _Requirements: 4.1, 4.2, 4.6, 6.4, 6.5, 8.3_

  - [ ]* 1.2 Write property test for completed tracker round-trip
    - **Property 1: Completed Tracker Round-Trip**
    - **Validates: Requirements 4.1, 4.2**
    - Use Hypothesis to generate random product IDs and emails
    - Verify mark_completed → is_completed returns True
    - Verify save_completed → load_completed preserves data
    - Use tmp_path fixture for isolated file I/O

  - [ ]* 1.3 Write property test for completed filtering exclusion
    - **Property 2: Completed Filtering Exclusion**
    - **Validates: Requirements 4.3, 4.5**
    - Generate sets of product URLs and completed tracker states
    - Verify filtered list never contains already-completed products for that account
    - Verify products completed for all 4 accounts are excluded from trigger batch

- [ ] 2. Implement browser automation functions in kartexpol_autobuy.py
  - [ ] 2.1 Implement `dismiss_overlay(page)` and `login(page, email, password)` functions
    - `dismiss_overlay`: Remove cookie consent overlays and restore pointer-events via JS evaluation
    - `login`: Navigate to /pl/login, dismiss overlays, inject email/password via JS, submit form via JS
    - Implement 3-attempt retry loop with 3-second waits
    - Detect "wyloguj" in page content as login success indicator
    - Return True on success, False after 3 failed attempts
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ] 2.2 Implement `clear_cart(page)` and `add_to_cart(page, product_url)` functions
    - `clear_cart`: Navigate to /pl/basket, loop up to 20 times following a.prodremove hrefs until cart empty
    - `add_to_cart`: Navigate to product URL, wait for load, click .addtobasket via JS evaluation
    - Return True/False for add_to_cart success
    - Handle missing/disabled buttons gracefully with logging
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 2.3 Implement `checkout(page, test_mode=False)` function
    - Step 1 (Basket): Verify "ZAMAWIAM" present, click button.order, verify step2 URL within 10s
    - Step 2 (Delivery): Select first paczkomat radio, check all checkboxes, click "PODSUMOWANIE", verify step3 URL
    - Step 3 (Confirmation): Click "POTWIERDZAM ZAKUP" (button.order), wait up to 15s for przelewy24 redirect
    - Return True if Przelewy24 URL detected, False otherwise
    - Handle test_mode (still clicks confirm but logs differently)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ] 2.4 Implement `logout(page)` function
    - Navigate to /pl/logout with domcontentloaded wait
    - Wrap in try/except, log any errors but don't raise
    - _Requirements: 7.3_

- [ ] 3. Implement main orchestration in kartexpol_autobuy.py
  - [ ] 3.1 Implement `run_for_account_batch(page, account, product_urls, test_mode=False)` function
    - Filter product URLs by excluding completed products for this account's email
    - If all completed, return "skipped" without login
    - Login → clear_cart → add_to_cart (loop) → checkout → mark completed → Discord notify
    - Return one of: "success", "skipped", "login_failed", "atc_failed", "checkout_failed"
    - _Requirements: 4.3, 4.4, 6.2_

  - [ ] 3.2 Implement `main()` with CLI argument parsing and sequential account processing
    - Parse args: positional URLs, --test, --accounts N, --start N, --qty N
    - Validate --accounts and --start are 1-4, --qty is 1-10
    - Exit with error if no URLs provided or invalid args
    - Check DISPLAY=:99 environment variable
    - Launch Patchright Chromium (headless=False, anti-detection args)
    - Process accounts sequentially in separate browser contexts
    - Close context + 2s delay between accounts
    - Send Discord summary after all accounts processed
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 8.1, 8.2, 8.4, 8.5, 8.6_

  - [ ]* 3.3 Write property test for account selection logic
    - **Property 5: Account Selection Logic**
    - **Validates: Requirements 7.5, 7.6, 7.7, 7.8**
    - Use Hypothesis to generate valid and invalid --start S and --accounts A values
    - Verify correct account slice is selected for valid inputs
    - Verify error exit for out-of-range values
    - Verify --test flag overrides to TEST_ACCOUNT only

  - [ ]* 3.4 Write property test for login retry bound
    - **Property 6: Login Retry Bound**
    - **Validates: Requirements 1.3, 1.4**
    - Use Hypothesis to generate sequences of login outcomes (success/failure)
    - Verify at most 3 attempts made
    - Verify early termination on success
    - Verify "login_failed" result after 3 failures
    - Mock page object for controlled testing

- [ ] 4. Checkpoint - Verify kartexpol_autobuy.py
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Rewrite kartexpol_trigger.py to batch pattern
  - [ ] 5.1 Rewrite `kartexpol_trigger.py` with batch collector matching `strefatcg_trigger.py` architecture
    - Define KEYWORDS_30TH, ALL_ACCOUNTS, BOT_PATH, COMPLETED_FILE, WEBHOOK_FILE constants
    - Implement `_matches_keywords(name)`: case-insensitive substring match against keyword list
    - Implement `_is_all_completed(product_id)`: check if all 4 accounts completed for a product
    - Implement `_load_completed()`: read kartexpol_completed.json, return {} if missing
    - Implement `check_kartexpol_trigger(event_type, product)`: filter by shop=="kartexpol", availability, keywords, completed status; add to _batch_products with URL deduplication
    - Implement `flush_kartexpol_batch()`: if batch non-empty, send Discord notification and launch bot subprocess with DISPLAY=:99, stdout/stderr redirected to log files
    - Clear batch after flush
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1_

  - [ ]* 5.2 Write property test for trigger keyword matching
    - **Property 3: Trigger Keyword Matching**
    - **Validates: Requirements 5.1, 5.2**
    - Use Hypothesis to generate product names with/without keywords
    - Verify match iff shop=="kartexpol" AND available==True AND name contains keyword
    - Verify no match when any condition fails

  - [ ]* 5.3 Write property test for batch URL deduplication
    - **Property 4: Batch URL Deduplication**
    - **Validates: Requirements 5.3**
    - Use Hypothesis to generate sequences of product events with repeated URLs
    - Verify batch contains at most one entry per unique URL
    - Verify first occurrence is retained

- [ ] 6. Checkpoint - Verify all components
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Wire components and finalize
  - [ ] 7.1 Update `detector.py` imports to use new trigger functions
    - Replace `check_kartexpol_autobuy` / `fire_kartexpol_buy` imports with `check_kartexpol_trigger` / `flush_kartexpol_batch`
    - Call `check_kartexpol_trigger(event_type, product)` in the product event loop
    - Call `flush_kartexpol_batch()` at the end of `detect_and_send()`
    - _Requirements: 5.4_

- [ ] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python 3, using Patchright (async Playwright fork) and Hypothesis for PBT
- Account passwords are placeholders — the user must configure real credentials before deployment
- The `--test` flag with `t11008543@gmail.com` enables integration testing against the live site without real purchases
- The existing `strefatcg_autobuy.py` serves as the reference implementation for structure and patterns

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1", "5.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "5.2", "5.3"] },
    { "id": 3, "tasks": ["3.1"] },
    { "id": 4, "tasks": ["3.2"] },
    { "id": 5, "tasks": ["3.3", "3.4"] },
    { "id": 6, "tasks": ["7.1"] }
  ]
}
```
