# Fund Scraper

A robust web scraping automation project designed to extract data points (such as financial rates) from dynamically rendered JavaScript webpages and heavily protected endpoints. Built with Python, Playwright, and Bash, the script utilizes a multi-tiered fallback architecture to bypass sophisticated anti-bot Web Application Firewalls (WAFs). The project also includes a secure, lightweight Python web server to host the extracted results.

## Overview

The system consists of two main components:
1. **Scraper:** A Python script (`scrape.py`) that parses a TSV file (`targets.tsv`), navigates to specific URLs, evaluates XPaths within the browser or HTML context, and writes the output to a CSV file. 
    - **Waterfall Architecture:** To ensure reliable data retrieval against strict bot protections (like Akamai), the scraper employs a sequential fallback mechanism:
        1. **Fidelity Fast Path:** Direct JSON API extraction for supported Fidelity symbols.
        2. **Playwright:** Headless Chromium browser mimicking a localized user profile.
        3. **curl_cffi:** TLS/JA3 fingerprint spoofing (impersonating Chrome).
        4. **ScraperAPI Escalation:** Iterates through Standard, Premium, and Ultra Premium residential proxy tiers.
        5. **ScrapingBee Escalation:** Iterates through Standard and Premium Proxy tiers as an absolute last resort.
    - **Validation:** The script automatically cleans the extracted data (trimming leading `+` and `$`, and trailing `%` characters) and validates the result as a positive floating-point number before updating the previous records.
2. **Server:** A custom Python web server (`server.py`) that securely serves only the generated output CSV file, by default on port 57275. It actively blocks path traversal attacks and prevents access to source code or configuration files.

## Project Structure

- `scrape.py`: Core python script to scrape targets. Accepts specific target keys as command-line arguments to limit the scope of the scrape.
- `run_scraper.sh`: Bash entry point to install dependencies and execute the scraper.
- `server.py`: Secure Python web server to host outputs.
- `run_server.sh`: Bash entry point to start the web server.
- `targets.tsv`: TSV file containing target mappings in the format `Filename\tURL\tXPath`.
- `Dockerfile` & `docker-compose.yml`: Containerization configuration.
- `.env` (User created): Holds environmental variables and API keys for proxy services.

## Usage

This project can be run either locally on your host machine or via Docker Compose. 

### API Keys
To utilize the proxy fallback mechanisms (ScraperAPI and ScrapingBee), you must provide your API keys via environment variables. Create a `.env` file or export them directly in your shell:
```bash
SCRAPER_API_KEY="your_scraperapi_key"
SCRAPINGBEE_API_KEY="your_scrapingbee_key"
