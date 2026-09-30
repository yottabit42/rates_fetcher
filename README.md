# Fund Scraper

A robust web scraping automation project designed to extract data points (such as financial rates and yields) from dynamically rendered JavaScript webpages using Python, `curl_cffi`, Playwright, and Selenium. The project also includes a secure, lightweight Python web server to host the extracted results.

## Overview

The system consists of two main components:
1. **Scraper (`scrape.py`):** An advanced, multi-tier scraping engine that parses a TSV file (`targets.tsv`), navigates to target URLs, and executes a resilient fallback waterfall to extract fund metrics (30-day SEC yields, Yield to Maturity, or 7-day yields) into a CSV file (`data.out`).
2. **Server (`server.py`):** A custom, secure Python web server that serves only the generated output CSV file (`data.out`), by default on port `57275`. It actively blocks path traversal attacks and prevents unauthorized access to source code or configuration files.

## Scraping Methodology

Rather than relying on paid third-party scraping APIs, `scrape.py` implements a 5-method resilient local extraction waterfall:

1. **Method 1: Fidelity Legacy JSON API (`Fastquote`)**
   - Directly queries `fastquote.fidelity.com` for mutual funds and supported instruments to obtain official 7-day yields (`YIELD_7_DAY`).
2. **Method 2: Direct In-Page & JSON-LD Extraction (`curl_cffi`)**
   - High-speed TLS/JA3 browser-impersonating HTTP client that fetches page payloads without headless browser overhead and bypasses anti-bot challenges (e.g. Cloudflare, Akamai):
     - **Vanguard:** Extracts `secYield` or `compoundYieldPct` directly from embedded page JSON state, bypassing client-side Shadow DOM rendering.
     - **WisdomTree:** Extracts 30-day SEC yield from semantic card structures and embedded state.
     - **iShares:** Extracts 30-Day SEC yield from structured JSON-LD and Walrus data attributes by default (use the `scrape` override flag in `targets.tsv` to target specific elements such as Yield to Maturity).
3. **Method 3: `curl_cffi` HTTP Impersonation with XPath**
   - Evaluates target XPaths from `targets.tsv` using `lxml` against the HTML payload returned by `curl_cffi`.
4. **Method 4: `rebrowser-playwright` Locator**
   - Headless Chromium browser context with patched CDP leak protections to defeat bot detection.
   - Evaluates target XPaths from `targets.tsv` in a headless browser when HTTP impersonation fails or pages require client-side execution.
5. **Method 5: Selenium WebDriver Fallback**
   - Headless Chrome driver with anti-automation flags suppressed (`--disable-blink-features=AutomationControlled`) as an ultimate fallback if Playwright or HTTP methods are blocked.

### Caching and Validation
- **Daily Idempotence:** If a fund has already been successfully retrieved for the current day (`today` based on `SCRAPER_TZ`), it is skipped during subsequent runs to save resources (unless explicitly passed as a command-line target).
- **Float Validation:** Extracted rates are stripped of currency symbols, plus signs, and percent signs, then validated as positive floating-point numbers before updating `data.out`. If an extraction fails, previous historical data is preserved.

## Project Structure

- `scrape.py`: Core multi-tier fund scraping engine.
- `targets.tsv`: TSV file containing target mappings in the format `Key\tURL\tXPath[\tOverrideFlag]`.
- `run_scraper.sh`: Bash wrapper to execute the scraper.
- `server.py`: Secure Python HTTP server serving only `data.out`.
- `run_server.sh`: Bash wrapper to launch the server on `${INT_PORT:-57275}`.
- `data.out`: Output CSV file formatted as `Key,Date,Value`.
- `Dockerfile` & `compose.yaml`: Containerization and service orchestration configurations.

## Usage

This project can be run either locally on your host machine or via Docker Compose.

### Running Locally

**Prerequisites:** Python 3 (with `curl_cffi`, `lxml`, `requests`, and optionally `rebrowser-playwright` or `selenium`).

1. **Run the Scraper:**
   ```bash
   # Run all targets in targets.tsv
   ./run_scraper.sh

   # Or run specific targeted funds:
   ./run_scraper.sh targets.tsv VBIL USFR SGOV IBIC
   ```
   Outputs will be saved as a CSV file named `data.out` in the current directory with the following fields: `fund_key,retrieval_date,rate`.

2. **Run the Server:**
   ```bash
   # Starts the secure server on port 57275 (or pass custom port as argument)
   ./run_server.sh
   ```
   Access the rates via `http://localhost:57275/data.out` or `http://localhost:57275/`.

### Running via Docker Compose

The included `compose.yaml` orchestrates both the `scraper` and the `server` containers:
- Mounts the project root directory `.:/app` into both containers so `targets.tsv`, scripts, and `data.out` remain directly in sync with the host.
- Binds external port `57275` (configurable via `${EXT_PORT}`) to container port `57275` (configurable via `${INT_PORT}`).

1. **Deploy the Stack:**
   ```bash
   docker compose up -d
   ```
   This will build the scraper container (with Playwright Chromium, Selenium, and dependencies pre-installed) and launch the web server.

   The `Dockerfile` needs to be located in a location as expected by your stack. For example, if using Dockge, the `Dockerfile` should be copied or moved to the Dockge stack path for the container. The Docker container will automatically build on first start, but it can also be manually rebuilt using the following command:
   ```bash
   docker compose build --no-cache
   ```

2. **Scraper Schedule:**
   - The `scraper` container runs once immediately on start.
   - A `cron` job inside the container runs the scraper daily at noon (`0 12 * * *`). The timezone is controlled by the `SCRAPER_TZ` environment variable (defaults to `America/Chicago`).

## Licensing

This project is licensed under the BSD 3-Clause License. See the [LICENSE](LICENSE) file for more details.
