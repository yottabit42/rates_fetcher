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
```

### Running Locally

**Prerequisites:** Python 3 and `pip` must be installed.

1. **Run the Scraper:**
   ```bash
   # This will automatically install playwright, chromium dependencies, and run the scrape
   ./run_scraper.sh
   ```
   
   Outputs will be saved as a CSV file named `data.out` in the current directory, with the following field order: fund key, date of successful retrieval, rate.

   #### Advanced Usage (Specific Targets)

   If you only want to update specific keys without re-scraping the entire file, you can run the Python script directly. The script requires your targets file as the first argument, followed by any specific keys you want to isolate:

   ```bash
   # Run for all targets in the file
   python3 scrape.py targets.tsv
   
   # Run only for specific target keys (e.g., 7555, M219, 8561)
   python3 scrape.py targets.tsv 7555 M219 8561
   ```

2. **Run the Server:**
   ```bash
   # This starts the secure server on port 57275
   ./run_server.sh
   ```
   You can then access the outputs via `http://localhost:57275/data.out`.

### Running via Docker Compose

The project includes a `docker-compose.yml` that:

  1. Maps the host directory defined in the `${DATA_PATH}` environmental variable to `/app` inside the containers. Ensure you place these project files in that directory on your host, or modify the volume paths in the `docker-compose.yml` to match your local directory structure.
  2. Maps the internal and external network ports defined in the `${INT_PORT}` and `${EXT_PORT}` environmental variables, respectively. Port 57275 is used by default if the environmental variable is undefined.
  3. Passes the required `SCRAPER_API_KEY` and `SCRAPINGBEE_API_KEY` environment variables to the container environment.

#### Traefik Setup

This `docker-compose.yml` file is configured with routing labels for a Traefik reverse proxy. It expects an external network named `proxy` to exist. The proxy domain is set to the `${TRAEFIK_HOST}` environmental variable.

1. **Deploy the Stack:**
   ```bash
   docker-compose up -d
   ```
   This will start both the continuously running `server` and the `scraper` container.

   The `Dockerfile` needs to be located in a location as expected by your stack. For example, if using Dockge, the `Dockerfile` should be copied or moved to the Dockge stack path for the container. The Docker container will automatically build on first start, but it can also be manually rebuilt using the following command:
   ```bash
   docker compose build --no-cache
   ```

3. **Scraper Schedule:**
   The `scraper` will run automatically the moment the container starts, and it's also scheduled via `cron` to run every day at noon (in the local container timezone, typically UTC). Output will be saved to your mounted host directory.

## Licensing

This project is licensed under the BSD 3-Clause License. See the [LICENSE](LICENSE) file for more details.
