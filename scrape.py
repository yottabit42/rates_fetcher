import sys
import re
import time
import json
import csv
import os
import random
import requests as std_requests
from urllib.parse import urlparse
from datetime import date
from rebrowser_playwright.sync_api import sync_playwright
from curl_cffi import requests as cffi_requests
from lxml import html

# Define your API keys here, or pass them via environment variables
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "YOUR_FREE_API_KEY")
SCRAPINGBEE_API_KEY = os.environ.get("SCRAPINGBEE_API_KEY", "YOUR_SCRAPINGBEE_API_KEY")

def main():
    # Allow 2 or more arguments: script.py, targets.tsv, and optional keys
    if len(sys.argv) < 2:
        print("Usage: python3 scrape.py <targets.tsv> [key1] [key2] ...")
        sys.exit(1)

    targets_file = sys.argv[1]
    # Store target keys in a set for fast lookup
    target_keys = set(sys.argv[2:])

    try:
        with open(targets_file, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Could not find '{targets_file}'.")
        sys.exit(1)

    today = date.today().strftime("%Y-%m-%d")
    data_out_file = "data.out"

    # Load existing data to preserve failed iterations and untouched keys
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

    if SCRAPER_API_KEY == "YOUR_FREE_API_KEY" or SCRAPINGBEE_API_KEY == "YOUR_SCRAPINGBEE_API_KEY":
        print("WARNING: You are using placeholder API keys. API Fallbacks will fail until these are updated.")

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
                parts = line.split(maxsplit=2)
                if len(parts) < 3:
                    print(f"Skipping malformed line: {line}")
                    continue

            key_name = parts[0]
            
            # Skip this key if specific target keys were provided and this isn't one of them
            if target_keys and key_name not in target_keys:
                continue

            url = parts[1]
            xpath = parts[2]

            print(f"Processing {key_name} from {url}...")
            text = None

            # 1. FAST PATH: Fidelity JSON API
            if 'fastquote.fidelity.com' in url.lower():
                time.sleep(random.randint(1, 3))
                print(f"  Attempting Fidelity Legacy JSON API for {key_name}...")
                try:
                    fq_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    fq_response = std_requests.get(url, headers=fq_headers, timeout=10)
                    if fq_response.status_code == 200:
                        clean_json = fq_response.text.strip()[1:-1]
                        data = json.loads(clean_json)
                        if "QUOTES" in data and key_name in data["QUOTES"]:
                            quote_data = data["QUOTES"][key_name]
                            text = (
                                quote_data.get("YIELD_7_DAY") or 
                                quote_data.get("SEC_YIELD_30_DAY") or 
                                quote_data.get("YIELD") or 
                                quote_data.get("TRAILING_DIVIDEND_YIELD")
                            )
                            if not text:
                                print(f"  JSON API response did not contain expected yield keys for {key_name}.")
                        else:
                            print(f"  JSON API response missing expected QUOTES payload for {key_name}.")
                    else:
                        print(f"  Fidelity Legacy JSON API failed with status code: {fq_response.status_code}")
                except Exception as ex:
                    print(f"  Fidelity Legacy JSON API failed: {ex}")

            # 2. STANDARD PATH: Playwright -> curl_cffi -> ScraperAPI -> ScrapingBee (Waterfall)
            else:
                # --- METHOD 1: Playwright ---
                delay = random.randint(2, 6)
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

                # --- METHOD 2: curl_cffi ---
                if text is None:
                    print(f"  Falling back to curl_cffi for {key_name}...")
                    time.sleep(random.randint(2, 5))
                    try:
                        playwright_cookies = context.cookies()
                        cookie_dict = {cookie['name']: cookie['value'] for cookie in playwright_cookies}
                        parsed_url = urlparse(url)
                        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"

                        headers = {
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                            "Accept-Language": "en-US,en;q=0.9",
                            "Cache-Control": "max-age=0",
                            "Referer": base_url,
                            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                            "Sec-Ch-Ua-Mobile": "?0",
                            "Sec-Ch-Ua-Platform": '"Windows"',
                            "Sec-Fetch-Dest": "document",
                            "Sec-Fetch-Mode": "navigate",
                            "Sec-Fetch-Site": "same-origin",
                            "Sec-Fetch-User": "?1",
                            "Upgrade-Insecure-Requests": "1",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        
                        response = cffi_requests.get(url, headers=headers, impersonate="chrome", timeout=10)

                        if response.status_code == 200:
                            tree = html.fromstring(response.text)
                            clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                            nodes = tree.xpath(clean_xpath)
                            if nodes:
                                text = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                            else:
                                print(f"  XPath '{clean_xpath}' not found in curl_cffi HTML payload.")
                        else:
                            print(f"  curl_cffi failed with status code: {response.status_code}")
                    except Exception as ex:
                        print(f"  curl_cffi fallback failed: {ex}")

                # --- METHOD 3, 4, 5: ScraperAPI Escalation ---
                if text is None:
                    # Define the tiers to iterate through if previous attempts fail
                    scraper_tiers = [
                        ("Standard", {}),
                        ("Premium", {'premium': 'true'}),
                        ("Ultra Premium", {'ultra_premium': 'true'})
                    ]
                    
                    for tier_name, tier_params in scraper_tiers:
                        print(f"  Falling back to ScraperAPI ({tier_name}) for {key_name}...")
                        payload = {
                            'api_key': SCRAPER_API_KEY, 
                            'url': url,
                            'render': 'true'
                        }
                        # Add the premium flags based on the current tier
                        payload.update(tier_params)
                        
                        try:
                            # Timeout 90s because residential proxy rendering takes time
                            api_response = std_requests.get('https://api.scraperapi.com/', params=payload, timeout=90)

                            if api_response.status_code == 200:
                                tree = html.fromstring(api_response.text)
                                clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                                nodes = tree.xpath(clean_xpath)
                                if nodes:
                                    text = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                                else:
                                    print(f"  XPath '{clean_xpath}' not found in ScraperAPI ({tier_name}) HTML payload.")
                            else:
                                print(f"  ScraperAPI ({tier_name}) failed with status code: {api_response.status_code}.")
                                sys.stdout.write(api_response.text + "\n")
                        except Exception as ex:
                            print(f"  ScraperAPI ({tier_name}) fallback failed: {ex}")
                        
                        # Stop escalating tiers if we successfully grabbed the text
                        if text is not None:
                            break

                # --- METHOD 6 & 7: ScrapingBee Escalation ---
                if text is None:
                    scrapingbee_tiers = [
                        ("Standard", {}),
                        ("Premium Proxy", {'premium_proxy': 'True'})
                    ]
                    
                    for tier_name, tier_params in scrapingbee_tiers:
                        print(f"  Falling back to ScrapingBee ({tier_name}) for {key_name}...")
                        payload = {
                            'api_key': SCRAPINGBEE_API_KEY,
                            'url': url,
                            'render_js': 'True'
                        }
                        # Add the premium proxy flags based on the current tier
                        payload.update(tier_params)
                        
                        try:
                            # Timeout 90s for JS rendering on proxy servers
                            sb_response = std_requests.get('https://app.scrapingbee.com/api/v1/', params=payload, timeout=90)

                            if sb_response.status_code == 200:
                                tree = html.fromstring(sb_response.text)
                                clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                                nodes = tree.xpath(clean_xpath)
                                if nodes:
                                    text = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                                else:
                                    print(f"  XPath '{clean_xpath}' not found in ScrapingBee ({tier_name}) HTML payload.")
                            else:
                                print(f"  ScrapingBee ({tier_name}) failed with status code: {sb_response.status_code}.")
                                sys.stdout.write(sb_response.text + "\n")
                        except Exception as ex:
                            print(f"  ScrapingBee ({tier_name}) fallback failed: {ex}")
                            
                        # Stop escalating tiers if we successfully grabbed the text
                        if text is not None:
                            break

            # --- VALIDATION & SAVE ---
            if text is not None:
                # Strip spaces, remove leading '+' or '$', remove trailing '%', and strip any resulting spaces
                text = text.strip().lstrip('+$').rstrip('%').strip()
                
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
                print(f"  FATAL: Failed to extract data for {key_name} after exhausting all fallback methods. Skipping file update to preserve old data.")

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
    main()
