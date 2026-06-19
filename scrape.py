import sys
import re
import time
import json
import csv
import os
import random
import requests as std_requests
from datetime import date
from rebrowser_playwright.sync_api import sync_playwright
from curl_cffi import requests
from lxml import html

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 scrape.py <targets.tsv>")
        sys.exit(1)

    targets_file = sys.argv[1]

    try:
        with open(targets_file, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Could not find '{targets_file}'.")
        sys.exit(1)

    today = date.today().strftime("%Y-%m-%d")
    data_out_file = "data.out"

    # Load existing data to preserve failed iterations
    existing_data = {}
    if os.path.exists(data_out_file):
        try:
            with open(data_out_file, 'r', newline='') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 3:
                        existing_data[row[0]] = {"date": row[1], "value": row[2]}
        except Exception as e:
            print(f"Warning: Could not parse existing data.out ({e})")

    with sync_playwright() as p:
        # Chromium requires --no-sandbox to run as root inside a Docker container
        # Use a persistent context to bypass strict anti-bot protections by mimicking a localized user profile
        context = p.chromium.launch_persistent_context(
            user_data_dir="/tmp/playwright_user_data",
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.pages[0]

        for line in lines:
            line = line.strip()
            if not line:
                continue

            parts = line.split('\t')
            if len(parts) < 3:
                # Try splitting by whitespace if tab splitting doesn't give enough parts
                parts = line.split(maxsplit=2)
                if len(parts) < 3:
                    print(f"Skipping malformed line: {line}")
                    continue

            key_name = parts[0]
            url = parts[1]
            xpath = parts[2]

            print(f"Processing {key_name} from {url}...")

            text = None
            for attempt in range(3):
                if attempt > 0:
                    print(f"  Retry attempt {attempt + 1}/3 for {key_name}...")

                # Branch logic based on target URL
                if 'fidelity.com' in url.lower():
                    # FAST PATH: Fidelity API Only
                    print(f"  Attempting Fidelity Legacy JSON API for {key_name}...")
                    try:
                        fq_url = f"https://fastquote.fidelity.com/service/quote/json?productid=embeddedquotes&symbols={key_name}"
                        fq_headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                        }
                        fq_response = std_requests.get(fq_url, headers=fq_headers, timeout=10)
                        if fq_response.status_code == 200:
                            clean_json = fq_response.text.strip()[1:-1]
                            data = json.loads(clean_json)
                            if "QUOTES" in data and key_name in data["QUOTES"]:
                                text = data["QUOTES"][key_name].get("YIELD_7_DAY")
                                if not text:
                                    print(f"  JSON API response did not contain YIELD_7_DAY for {key_name}.")
                            else:
                                print(f"  JSON API response missing expected QUOTES payload for {key_name}.")
                        else:
                            print(f"  Fidelity Legacy JSON API failed with status code: {fq_response.status_code}")
                    except Exception as ex:
                        print(f"  Fidelity Legacy JSON API failed: {ex}")

                    delay = random.randint(2, 7)
                    print(f"  Sleeping {delay}s after Fidelity API retrieval attempt...")
                    time.sleep(delay)

                else:
                    # STANDARD PATH: Playwright -> curl_cffi fallback
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=10000)
                        
