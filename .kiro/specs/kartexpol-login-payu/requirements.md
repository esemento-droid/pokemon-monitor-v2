# Requirements Document

## Introduction

Rewrite the Kartexpol auto-buy bot from a guest-checkout + traditional bank transfer approach to a login-based + Przelewy24/BLIK payment approach. The new bot follows the same architecture as the proven Strefa-TCG auto-buy bot (`strefatcg_autobuy.py`): Patchright headless=False browser automation with login, batch cart, completed-product tracking, and Przelewy24 payment redirect. The goal is to automatically purchase Pokemon TCG 30th Anniversary products on kartexpol.pl across 4 registered accounts whenever a matching product becomes available.

## Glossary

- **Kartexpol_Bot**: The Patchright-based auto-buy bot script (`kartexpol_autobuy.py`) that logs into kartexpol.pl, adds matching products to cart, and completes checkout with Przelewy24 payment
- **Kartexpol_Trigger**: The trigger module (`kartexpol_trigger.py`) integrated into the detector that collects matching products in batch and launches Kartexpol_Bot
- **Completed_Tracker**: A JSON file (`kartexpol_completed.json`) that records which accounts have already purchased which products to prevent duplicate orders
- **Shoper_Platform**: The e-commerce platform powering kartexpol.pl (same engine as strefa-tcg.pl)
- **Patchright**: A patched Playwright fork with anti-detection features used for browser automation
- **Przelewy24**: An online payment gateway that provides a BLIK payment option on its redirect page
- **Batch_Mode**: A pattern where multiple matching products are collected during one scan cycle and placed into a single cart per account
- **Production_Account**: One of 4 registered user accounts on kartexpol.pl used for purchasing
- **Test_Account**: A dedicated account (`t11008543@gmail.com`) used for dry-run testing without real payment
- **Xvfb**: X Virtual Framebuffer providing a virtual display (DISPLAY=:99) required for headless=False browser execution
- **Discord_Webhook**: A webhook URL stored in a file used to send purchase notifications to a Discord channel

## Requirements

### Requirement 1: Account Login

**User Story:** As the bot operator, I want the bot to log into registered Kartexpol accounts, so that orders are placed under known accounts with saved addresses and purchase history.

#### Acceptance Criteria

1. WHEN the bot starts processing an account, THE Kartexpol_Bot SHALL navigate to the Kartexpol login page (BASE_URL/pl/login) with a page load timeout of 30 seconds and authenticate using the account email and password
2. WHEN the Shoper_Platform displays a cookie consent overlay, THE Kartexpol_Bot SHALL dismiss the overlay by clicking the consent button or removing overlay elements via JavaScript before attempting login
3. IF a login attempt does not result in a "wyloguj" link appearing in the page content within 10 seconds after form submission, THEN THE Kartexpol_Bot SHALL consider the attempt failed, wait 3 seconds, and retry up to a maximum of 3 attempts per account
4. IF login fails after 3 attempts for an account, THEN THE Kartexpol_Bot SHALL log the failure with the account email and failure reason, skip that account, and proceed to the next account in the queue
5. WHEN login succeeds, THE Kartexpol_Bot SHALL verify the authenticated state by confirming the presence of a "wyloguj" (logout) link in the page content before proceeding to the ordering flow
6. THE Kartexpol_Bot SHALL use JavaScript-based value injection for form fields (email, password) followed by form submission via JavaScript, because Shoper body overlays block standard Playwright click and fill interactions
7. IF navigation to the login page fails or times out, THEN THE Kartexpol_Bot SHALL treat it as a failed login attempt and apply the retry logic defined in criterion 3

### Requirement 2: Cart Management

**User Story:** As the bot operator, I want the bot to clear the existing cart and add all target products, so that each order contains exactly the intended 30th anniversary products.

#### Acceptance Criteria

1. WHEN an account is logged in, THE Kartexpol_Bot SHALL navigate to the basket page and remove all existing items before adding new products
2. WHEN clearing the cart, THE Kartexpol_Bot SHALL iteratively follow the `a.prodremove` href links until no items remain in the basket or a maximum of 20 removal iterations is reached
3. WHEN adding a product to cart, THE Kartexpol_Bot SHALL navigate to the product page, wait up to 10 seconds for page load, and click the `.addtobasket` button using JavaScript
4. IF a product cannot be added to cart (page fails to load, button disabled, button not found, or page returns an error), THEN THE Kartexpol_Bot SHALL log a warning including the product URL and continue with the remaining products
5. WHEN one or more products are provided, THE Kartexpol_Bot SHALL add all of them to a single cart before proceeding to checkout
6. IF no products were successfully added to the cart after attempting all provided product URLs, THEN THE Kartexpol_Bot SHALL abort the order for the current account and log an error indicating zero products added

### Requirement 3: Checkout Flow

**User Story:** As the bot operator, I want the bot to complete the full checkout with Przelewy24 payment, so that the order reaches the payment gateway where I can pay with BLIK manually.

#### Acceptance Criteria

1. WHEN at least one product has been added to the cart, THE Kartexpol_Bot SHALL navigate to the basket page, verify the basket is non-empty (page contains "ZAMAWIAM" text), and click the "ZAMAWIAM" (order) button to proceed to checkout step 2
2. IF the basket page does not contain the "ZAMAWIAM" button or the page does not advance to a URL containing "step2" within 10 seconds of clicking, THEN THE Kartexpol_Bot SHALL log the error with the current URL and page content snippet, logout, and proceed to the next account
3. WHEN on checkout step 2 (delivery), THE Kartexpol_Bot SHALL select the first paczkomat radio button (input[type="radio"][name="machine"]) that is present in the DOM, check all checkbox inputs (input[type="checkbox"]) on the page, and click the element containing text "PODSUMOWANIE" to proceed to checkout step 3
4. IF checkout step 2 does not advance to a URL containing "step3" within 10 seconds of clicking "PODSUMOWANIE", THEN THE Kartexpol_Bot SHALL log the error with the current URL, logout, and proceed to the next account
5. WHEN on checkout step 3 (confirmation) with URL containing "step3", THE Kartexpol_Bot SHALL click the "POTWIERDZAM ZAKUP" button (button.order) to finalize the order
6. WHEN the "POTWIERDZAM ZAKUP" button has been clicked, THE Kartexpol_Bot SHALL wait up to 15 seconds and detect a redirect to the Przelewy24 payment page (URL containing "przelewy24" or "secure.przelewy24.pl") as confirmation of successful order placement
7. IF the page URL does not contain "przelewy24" within 15 seconds after clicking "POTWIERDZAM ZAKUP", THEN THE Kartexpol_Bot SHALL treat the order as failed, log the final URL and a 200-character page content snippet, logout, and proceed to the next account

### Requirement 4: Completed Purchase Tracking

**User Story:** As the bot operator, I want the bot to track which products each account has already purchased, so that the same product is not ordered twice on the same account.

#### Acceptance Criteria

1. THE Completed_Tracker SHALL persist purchase records as a JSON file mapping product IDs (string keys) to arrays of account email addresses that have completed that purchase, creating an empty JSON object if the file does not exist on first read
2. WHEN an order is confirmed as placed for a product on an account (the checkout flow reaches Przelewy24 redirect), THE Kartexpol_Bot SHALL immediately write that product-account combination to the Completed_Tracker JSON file before proceeding to the next account
3. WHEN preparing the product list for an account, THE Kartexpol_Bot SHALL exclude any product whose product ID already appears in the Completed_Tracker with that account's email in its completed list
4. WHEN all products in the batch are already marked as completed for an account, THE Kartexpol_Bot SHALL skip that account without attempting login or checkout and SHALL log an entry containing the account name and the text "already completed, skipping"
5. IF all 4 Production_Accounts' emails are present in the completed list for a product ID, THEN THE Kartexpol_Trigger SHALL not include that product in the batch passed to the buy bot
6. IF the Completed_Tracker JSON file exists but contains malformed JSON, THEN THE Completed_Tracker SHALL treat the state as empty (no prior completions) and log a warning indicating the parse failure

### Requirement 5: Trigger Integration (Batch Mode)

**User Story:** As the bot operator, I want the trigger to collect all matching 30th anniversary products during a scan cycle and launch the bot once with all URLs, so that multiple products can be ordered in a single cart.

#### Acceptance Criteria

1. WHEN the detector reports a NEW_PRODUCT, RESTOCK, or PRICE_CHANGE event for a product on shop "kartexpol", THE Kartexpol_Trigger SHALL evaluate the product against 30th anniversary keywords
2. THE Kartexpol_Trigger SHALL match products whose name contains any of the following keywords (case-insensitive substring match): "30th", "30 celebration", "30-lecie", "30 lecie", "30 rocznica"
3. IF a product matches keywords, is marked as available, and has not been completed for all 4 configured accounts (as recorded in a persistent completed-products store), THEN THE Kartexpol_Trigger SHALL add the product to the batch collector, deduplicating by product URL so each product appears at most once per batch
4. WHEN the detector finishes processing all events for a scan cycle (end of detect_and_send) and the batch collector contains at least one product, THE Kartexpol_Trigger SHALL flush the batch by launching Kartexpol_Bot as a single subprocess invocation with all collected product URLs passed as arguments
5. THE Kartexpol_Trigger SHALL launch the bot subprocess with the Patchright environment variable (DISPLAY=:99) set and redirect stdout and stderr to dedicated log files
6. IF the batch collector is empty at the end of a scan cycle, THEN THE Kartexpol_Trigger SHALL skip bot launch and take no action
7. IF the bot subprocess fails to launch (e.g., bot script not found or OS error), THEN THE Kartexpol_Trigger SHALL log an error message indicating the failure reason and not retry within that scan cycle

### Requirement 6: Discord Notifications

**User Story:** As the bot operator, I want to receive Discord notifications when the trigger fires and when orders are placed, so that I know to go pay with BLIK on the Przelewy24 page.

#### Acceptance Criteria

1. WHEN the trigger flushes a batch with one or more products, THE Kartexpol_Trigger SHALL send a Discord message containing each matched product name and a line announcing that the bot is starting for a specified number of accounts
2. WHEN an order is placed successfully for an account, THE Kartexpol_Bot SHALL send a Discord message containing the account holder name, the order ID, the number of products ordered, and a prompt indicating that BLIK payment is required
3. WHEN all accounts have been processed, THE Kartexpol_Bot SHALL send a summary Discord message listing each account with its pass/fail status and the total count of successful orders out of total attempts
4. THE Kartexpol_Bot SHALL read the Discord webhook URL from the file `discord_webhook_kartexpol.txt`
5. IF the Discord webhook file is missing, the file is empty, or the HTTP POST to the webhook does not complete within 10 seconds, THEN THE Kartexpol_Bot SHALL log a warning and continue order processing without interruption

### Requirement 7: Multi-Account Sequential Processing

**User Story:** As the bot operator, I want the bot to process all 4 production accounts sequentially in separate browser contexts, so that each account gets its own isolated session.

#### Acceptance Criteria

1. THE Kartexpol_Bot SHALL process 4 Production_Accounts sequentially (one after another), where each account completes its full buy flow (success or failure) before the next account begins
2. WHEN processing each account, THE Kartexpol_Bot SHALL create a new browser context with a desktop Chrome user agent string matching the format "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
3. WHEN an account finishes (success or failure), THE Kartexpol_Bot SHALL close that browser context and wait 2 seconds before starting the next account
4. WHEN the `--test` flag is provided, THE Kartexpol_Bot SHALL process only the Test_Account instead of the 4 Production_Accounts
5. WHEN the `--accounts N` flag is provided where N is an integer between 1 and 4, THE Kartexpol_Bot SHALL process only the first N Production_Accounts in order
6. WHEN the `--start N` flag is provided where N is an integer between 1 and 4, THE Kartexpol_Bot SHALL begin processing from account number N (1-indexed), skipping accounts before N
7. IF `--accounts N` or `--start N` is provided with a value outside the range 1–4, THEN THE Kartexpol_Bot SHALL exit with an error message indicating the valid range is 1–4
8. WHEN both `--start S` and `--accounts A` flags are provided, THE Kartexpol_Bot SHALL process accounts starting from position S, processing at most A accounts (stopping at account 4 if S + A - 1 exceeds 4)

### Requirement 8: Environment and Runtime

**User Story:** As the bot operator, I want the bot to run reliably on the VPS with Xvfb, so that Patchright headless=False works without a physical display.

#### Acceptance Criteria

1. IF the DISPLAY environment variable is not set to `:99` or Xvfb is not running, THEN THE Kartexpol_Bot SHALL exit with a non-zero exit code and print an error message indicating the missing display dependency
2. THE Kartexpol_Bot SHALL launch Patchright Chromium with headless=False and anti-detection arguments (`--disable-blink-features=AutomationControlled`, `--no-sandbox`)
3. THE Kartexpol_Bot SHALL append each login attempt, add-to-cart action, checkout step, and order result to the log file `kartexpol_autobuy.log` with ISO 8601 timestamps
4. THE Kartexpol_Bot SHALL accept one or more product URLs as positional command-line arguments
5. IF no product URLs are provided as arguments, THEN THE Kartexpol_Bot SHALL exit with a non-zero exit code and print a usage message indicating that at least one URL is required
6. THE Kartexpol_Bot SHALL support a `--qty N` argument specifying quantity per product per account, where N is an integer from 1 to 10, defaulting to 1
