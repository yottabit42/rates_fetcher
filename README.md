# Fund Scraper

A robust web scraping automation project designed to extract data points (such as financial rates) from dynamically rendered JavaScript webpages using Python, Playwright, and Bash. The project also includes a secure, lightweight Python web server to host the extracted results.

## Overview

The system consists of two main components:
1. **Scraper:** A highly resilient Python script (`scrape.py`) driven by `rebrowser-playwright` that parses a TSV file (`targets.tsv`). It uses persistent, localized browser profiles to defeat aggressive CDNs and dynamically evaluates XPaths within the browser DOM to extract financial rates. To ensure fault tolerance, the scraper:
   - Evaluates up to 3 fallback mechanisms per target (Playwright -> `curl_cffi` TLS Spoofing -> Fidelity Legacy JSONP APIs).
   - Operates on a 3-attempt retry loop per target.
   - Preserves previously saved data by strictly skipping output overwrites if a target explicitly fails.
   - Throttles requests by pausing for 10 seconds between targets to avoid bot-detection triggers.
2. **Server:** A custom Python web server (`server.py`) that securely serves only the generated `.txt` files on port 57275. It actively blocks path traversal attacks and prevents access to source code or configuration files.

## Project Structure

- `scrape.py`: Core python script to scrape targets.
- `run_scraper.sh`: Bash entry point to install dependencies and execute the scraper.
- `server.py`: Secure Python web server to host outputs.
- `run_server.sh`: Bash entry point to start the web server.
- `targets.tsv`: TSV file containing target mappings in the format `Filename \t URL \t XPath`.
- `Dockerfile` & `docker-compose.yml`: Containerization configuration.

## Usage

This project can be run either locally on your host machine or via Docker Compose.

### Running Locally

**Prerequisites:** Python 3 and `pip` must be installed.

1. **Run the Scraper:**
   ```bash
   # This will automatically install playwright, chromium dependencies, and run the scrape
   ./run_scraper.sh
   ```
   Outputs will be saved as `<Filename>.txt` in the current directory, with the date on the first line and the scraped value on the second line.

2. **Run the Server:**
   ```bash
   # This starts the secure server on port 57275
   ./run_server.sh
   ```
   You can then access the outputs via `http://localhost:57275/VMFXX.txt`.

### Running via Docker Compose

The project includes a `docker-compose.yml` that maps the host directory `/mnt/vol1/docker/data/rates_fetcher` to `/app` inside the containers. Ensure you place these project files in that directory on your host, or modify the volume paths in the `docker-compose.yml` to match your local directory structure.

#### Traefik Setup

This `docker-compose.yml` file is configured with routing labels for a Traefik reverse proxy. It expects an external network named `proxy` to exist. The proxy domain is set to `rf.mcawesome.org`.

1. **Deploy the Stack:**
   ```bash
   docker-compose up -d
   ```
   This will start both the continuously running `server` and the `scraper` container.

2. **Scraper Schedule:**
   The `scraper` will run automatically the moment the container starts, and it's also scheduled via `cron` to run every day at noon. Output will be saved to your mounted host directory.

## Licensing

This project is licensed under the BSD 3-Clause License. See the [LICENSE](LICENSE) file for more details.
