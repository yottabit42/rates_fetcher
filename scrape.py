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
                    delay = random.randint(2, 7)
                    print(f"  Sleeping {delay}s before Fidelity API retrieval attempt...")
                    time.sleep(delay)

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

                else:
                    # STANDARD PATH: Playwright -> curl_cffi fallback
                    delay = random.randint(2, 7)
                    print(f"  Sleeping {delay}s before Playwright retrieval attempt...")
                    time.sleep(delay)

                    try:
                        # Wait until 'load' instead of 'domcontentloaded' to let redirects/hydration finish
                        page.goto(url, wait_until="load", timeout=15000)
                        wait_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                        
                        # Use the auto-retrying Locator API instead of a static ElementHandle
                        locator = page.locator(f"xpath={wait_xpath}").first
                        
                        # Extract text directly (Playwright auto-waits up to the timeout for the element)
                        text = locator.text_content(timeout=10000)
                            
                    except Exception as e:
                        print(f"  Playwright failed for {key_name} ({e}).")

                    if text is not None:
                        break

                    print(f"  Falling back to curl_cffi for {key_name}...")
                    
                    delay = random.randint(2, 7)
                    print(f"  Sleeping {delay}s before curl_cffi retrieval attempt...")
                    time.sleep(delay)
                    
                    try:
                        headers = {
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                            "Accept-Language": "en-US,en;q=0.9",
                            "Cache-Control": "max-age=0",
                        }
                        response = requests.get(url, headers=headers, impersonate="chrome", timeout=10)

                        if response.status_code == 200:
                            tree = html.fromstring(response.text)
                            nodes = tree.xpath(xpath)
                            if nodes:
                                if isinstance(nodes[0], str):
                                    text = nodes[0]
                                else:
                                    text = nodes[0].text_content()
                            else:
                                print(f"  XPath '{xpath}' not found in raw HTML payload for {key_name}.")
                        else:
                            print(f"  curl_cffi failed with status code: {response.status_code}")
                    except Exception as ex:
                        print(f"  curl_cffi fallback also failed: {ex}")

                # Break the retry loop if text was successfully acquired by any method
                if text is not None:
                    break

            if text is not None:
                text = text.strip().rstrip('%').strip()
                
                # Floating-point validation block
                is_positive_float = False
                try:
                    parsed_value = float(text)
                    if parsed_value > 0:
                        is_positive_float = True
                except ValueError:
                    pass
                
                if is_positive_float:
                    existing_data[key_name] = {"date": today, "value": text}
                    print(f"  Success: Extracted '{text}' for {key_name}.")
                else:
                    print(f"  FATAL: Extracted value '{text}' for {key_name} is not a positive floating-point number. Skipping update to preserve old data.")

            else:
                print(f"  FATAL: Failed to extract data for {key_name} after 3 attempts. Skipping file update to preserve old data.")

        context.close()

    # Write aggregated data out as CSV
    try:
        with open(data_out_file, 'w', newline='') as out_f:
            writer = csv.writer(out_f)
            for fund, info in existing_data.items():
                writer.writerow([fund, info["date"], info["value"]])
        print(f"Finished. Aggregated data saved to {data_out_file}.")
    except Exception as e:
        print(f"Error saving {data_out_file}: {e}")

if __name__ == "__main__":
    main
