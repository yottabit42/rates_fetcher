# Fund Scraper

A robust web scraping automation project designed to extract data points (such as financial rates) from dynamically rendered JavaScript webpages using Python, Playwright, and Bash. The project also includes a secure, lightweight Python web server to host the extracted results.

## Overview

The system consists of two main components:
1. **Scraper:** A Python script (`scrape.py`) driven by Playwright that parses a TSV file (`targets.tsv`), navigates to specific URLs, evaluates XPaths within the browser context, and writes the output to a CSV file.
2. **Server:** A custom Python web server (`server.py`) that securely serves only the generated output CSV file, by default on port 57275. It actively blocks path traversal attacks and prevents access to source code or configuration files.

## Project Structure

- `scrape.py`: Core python script to scrape targets.
- `run_scraper.sh`: Bash entry point to install dependencies and execute the scraper.
- `server.py`: Secure Python web server to host outputs.
- `run_server.sh`: Bash entry point to start the web server.
- `targets.tsv`: TSV file containing target mappings in the format `Filename\tURL\tXPath`.
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
   Outputs will be saved as a CSV file named `data.out` in the current directory, with the following field order: fund key, date of successful retrieval, rate.

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

#### Traefik Setup

This `docker-compose.yml` file is configured with routing labels for a Traefik reverse proxy. It expects an external network named `proxy` to exist. The proxy domain is set to the `${TRAEFIK_HOST}` environmental variable.

1. **Deploy the Stack:**
   ```bash
   docker-compose up -d
   ```
   This will start both the continuously running `server` and the `scraper` container.

2. **Scraper Schedule:**
   The `scraper` will run automatically the moment the container starts, and it's also scheduled via `cron` to run every day at noon (in the local container timezone, typically UTC). Output will be saved to your mounted host directory.

## Licensing

This project is licensed under the BSD 3-Clause License. See the [LICENSE](LICENSE) file for more details.
