import sys
import re
import json
import csv
import os
import time
import requests as std_requests
from urllib.parse import urlparse
from datetime import datetime, date
from rebrowser_playwright.sync_api import sync_playwright
from curl_cffi import requests as cffi_requests
from lxml import html

try:
    import zoneinfo
except ImportError:
    zoneinfo = None

# Define your API keys here, or pass them via environment variables
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "YOUR_FREE_API_KEY")
SCRAPINGBEE_API_KEY = os.environ.get("SCRAPINGBEE_API_KEY", "YOUR_SCRAPINGBEE_API_KEY")
ZENROWS_API_KEY = os.environ.get("ZENROWS_API_KEY", "YOUR_ZENROWS_API_KEY")
SCRAPINGANT_API_KEY = os.environ.get("SCRAPINGANT_API_KEY", "YOUR_SCRAPINGANT_API_KEY")
SCRAPINGDOG_API_KEY = os.environ.get("SCRAPINGDOG_API_KEY", "YOUR_SCRAPINGDOG_API_KEY")
SCRAPEDO_API_KEY = os.environ.get("SCRAPEDO_API_KEY", "YOUR_SCRAPEDO_API_KEY")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scrape.py <targets.tsv> [key1] [key2] ...")
        sys.exit(1)

    targets_file = sys.argv[1]
    target_keys = set(sys.argv[2:])

    try:
        # Read with utf-8-sig to automatically strip Byte Order Marks (BOM) if present
        with open(targets_file, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Could not find '{targets_file}'.")
        sys.exit(1)

    # Determine today's date based on custom timezone environment variable
    # Using SCRAPER_TZ prevents conflicts with underlying Docker OS defaults
    tz_env = os.environ.get("SCRAPER_TZ") or os.environ.get("TZ")
    print(f"DEBUG: Environment Timezone variable evaluated to: '{tz_env}'")
    
    if tz_env and zoneinfo:
        try:
            tz = zoneinfo.ZoneInfo(tz_env)
            now = datetime.now(tz)
            today = now.strftime("%Y-%m-%d")
            print(f"DEBUG: Using zoneinfo. Current time in {tz_env} is: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"DEBUG: Evaluated 'today' date string: {today}")
        except Exception as e:
            print(f"Warning: Could not load timezone '{tz_env}' using zoneinfo: {e}. Falling back to tzset.")
            # Only set os.environ['TZ'] temporarily so time.tzset() picks it up if we use SCRAPER_TZ
            original_tz = os.environ.get('TZ')
            os.environ['TZ'] = tz_env
            if hasattr(time, 'tzset'):
                time.tzset()
            now = datetime.now()
            today = date.today().strftime("%Y-%m-%d")
            print(f"DEBUG: Fallback time after tzset is: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"DEBUG: Evaluated 'today' date string: {today}")
            # Restore original TZ just in case
            if original_tz is not None:
                os.environ['TZ'] = original_tz
            else:
                del os.environ['TZ']
    else:
        # Fallback for systems without zoneinfo (Python < 3.9) or missing tzdata
        if tz_env:
            original_tz = os.environ.get('TZ')
            os.environ['TZ'] = tz_env
            if hasattr(time, 'tzset'):
                time.tzset()
            
        now = datetime.now()
        today = date.today().strftime("%Y-%m-%d")
        print(f"DEBUG: No zoneinfo used. Current time is: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"DEBUG: Evaluated 'today' date string: {today}")
        
        if tz_env and hasattr(time, 'tzset'):
            if original_tz is not None:
                os.environ['TZ'] = original_tz
            else:
                del os.environ['TZ']

    data_out_file = "data.out"
    existing_data = {}

    if os.path.exists(data_out_file):
        try:
            with open(data_out_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 3:
                        existing_data[row[0]] = {"date": row[1], "value": row[2]}
        except Exception as e:
            print(f"Warning: Could not parse existing data.out ({e})")

    # Warn if any API key is missing
    placeholder_keys = [
        ("ScraperAPI", SCRAPER_API_KEY, "YOUR_FREE_API_KEY"),
        ("ScrapingBee", SCRAPINGBEE_API_KEY, "YOUR_SCRAPINGBEE_API_KEY"),
        ("ZenRows", ZENROWS_API_KEY, "YOUR_ZENROWS_API_KEY"),
        ("ScrapingAnt", SCRAPINGANT_API_KEY, "YOUR_SCRAPINGANT_API_KEY"),
        ("Scrapingdog", SCRAPINGDOG_API_KEY, "YOUR_SCRAPINGDOG_API_KEY"),
        ("Scrape.do", SCRAPEDO_API_KEY, "YOUR_SCRAPEDO_API_KEY"),
    ]

    for name, key, placeholder in placeholder_keys:
        if key == placeholder:
            print(f"WARNING: You are using a placeholder API key for {name}. Its fallback will fail.")

    # We keep Playwright launched in case all API layers fail
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="/tmp/playwright_user_data",
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        page = context.pages[0]

        for line in lines:
            # Aggressive cleanup for invisible characters
            line = line.strip().replace('\ufeff', '').replace('\r', '')
            if not line:
                continue

            parts = line.split('\t')
            if len(parts) < 3:
                parts = line.split(maxsplit=2)
                if len(parts) < 3:
                    print(f"Skipping malformed line: {line}")
                    continue

            key_name = parts[0].strip()
            
            if target_keys and key_name not in target_keys:
                continue

            # SKIP IF ALREADY UPDATED TODAY
            if key_name in existing_data and existing_data[key_name]["date"] == today:
                print(f"Skipping {key_name}: Already updated today ({today}).")
                continue

            # Aggressively clean the URL
            url = parts[1].strip(' "\'')
            xpath = parts[2].strip()

            print(f"Processing {key_name} from URL: [{url}]")

            text = None

            # ==========================================
            # PATH 1: FIDELITY API (Only for Fidelity)
            # ==========================================
            if 'fidelity.com' in url.lower():
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
                        print(f"  Fidelity Legacy JSON API failed with status code: {fq_response.status_code}. Details: {fq_response.text}")
                except Exception as ex:
                    print(f"  Fidelity Legacy JSON API failed: {ex}")

            # ==========================================
            # PATH 2: STANDARD WEB SCRAPING WATERFALL
            # ==========================================
            else:
                # --- METHOD 1: curl_cffi ---
                print(f"  Attempting curl_cffi for {key_name}...")
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    }
                    
                    response = cffi_requests.get(url, headers=headers, impersonate="chrome")
                    if response.status_code == 200:
                        tree = html.fromstring(response.content)
                        clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                        nodes = tree.xpath(clean_xpath)
                        if nodes:
                            text = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                        else:
                            print(f"  XPath '{clean_xpath}' not found in curl_cffi HTML payload.")
                    else:
                        print(f"  curl_cffi failed with status code: {response.status_code}. Details: {response.text[:1000]}")
                except Exception as ex:
                    print(f"  curl_cffi fallback failed: {ex}")

                # --- METHOD 2: Playwright (First Fallback) ---
                if text is None:
                    print(f"  Falling back to Playwright...")
                    try:
                        page.goto(url, wait_until="load", timeout=15000)
                        wait_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                        locator = page.locator(f"xpath={wait_xpath}").first
                        text = locator.text_content(timeout=10000)
                    except Exception as e:
                        print(f"  Playwright failed for {key_name} ({e}).")

                # --- METHOD 3: ScraperAPI Escalation ---
                if text is None:
                    scraper_tiers = [
                        ("Standard", {}),
                        ("Premium", {'premium': 'true'}),
                        ("Ultra Premium", {'ultra_premium': 'true'})
                    ]
                    
                    for tier_name, tier_params in scraper_tiers:
                        print(f"  Falling back to ScraperAPI ({tier_name}) for {key_name}...")
                        payload = {'api_key': SCRAPER_API_KEY, 'url': url, 'render': 'true'}
                        payload.update(tier_params)
                        
                        try:
                            api_response = std_requests.get('https://api.scraperapi.com/', params=payload, timeout=90)
                            if api_response.status_code == 200:
                                tree = html.fromstring(api_response.content)
                                clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                                nodes = tree.xpath(clean_xpath)
                                if nodes:
                                    text = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                                else:
                                    print(f"  XPath '{clean_xpath}' not found in ScraperAPI ({tier_name}) HTML payload.")
                            else:
                                print(f"  ScraperAPI ({tier_name}) failed with status code: {api_response.status_code}. Details: {api_response.text}")
                        except Exception as ex:
                            print(f"  ScraperAPI ({tier_name}) fallback failed: {ex}")
                        
                        if text is not None:
                            break

                # --- METHOD 4: ScrapingBee Escalation ---
                if text is None:
                    scrapingbee_tiers = [
                        ("Standard", {}),
                        ("Premium Proxy", {'premium_proxy': 'True'})
                    ]
                    
                    for tier_name, tier_params in scrapingbee_tiers:
                        print(f"  Falling back to ScrapingBee ({tier_name}) for {key_name}...")
                        payload = {'api_key': SCRAPINGBEE_API_KEY, 'url': url, 'render_js': 'True'}
                        payload.update(tier_params)
                        
                        try:
                            sb_response = std_requests.get('https://app.scrapingbee.com/api/v1/', params=payload, timeout=90) 
                            if sb_response.status_code == 200: 
                                tree = html.fromstring(sb_response.content)
                                clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                                nodes = tree.xpath(clean_xpath)
                                if nodes:
                                    text = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                                else:
                                    print(f"  XPath '{clean_xpath}' not found in ScrapingBee ({tier_name}) HTML payload.")
                            else:
                                print(f"  ScrapingBee ({tier_name}) failed with status code: {sb_response.status_code}. Details: {sb_response.text}")
                        except Exception as ex:
                            print(f"  ScrapingBee ({tier_name}) fallback failed: {ex}")
                            
                        if text is not None:
                            break

                # --- METHOD 5: ZenRows ---
                if text is None:
                    print(f"  Falling back to ZenRows for {key_name}...")
                    payload = {'apikey': ZENROWS_API_KEY, 'url': url, 'js_render': 'true', 'premium_proxy': 'true'}
                    try:
                        zr_response = std_requests.get('https://api.zenrows.com/v1/', params=payload, timeout=90)
                        if zr_response.status_code == 200:
                            tree = html.fromstring(zr_response.content)
                            clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                            nodes = tree.xpath(clean_xpath)
                            if nodes:
                                text = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                            else:
                                print(f"  XPath '{clean_xpath}' not found in ZenRows HTML payload.")
                        else:
                            print(f"  ZenRows failed with status code: {zr_response.status_code}. Details: {zr_response.text}")
                    except Exception as ex:
                        print(f"  ZenRows fallback failed: {ex}")

                # --- METHOD 6: ScrapingAnt ---
                if text is None:
                    print(f"  Falling back to ScrapingAnt for {key_name}...")
                    payload = {'url': url, 'browser': 'true'}
                    headers = {'x-api-key': SCRAPINGANT_API_KEY}
                    try:
                        sa_response = std_requests.get('https://api.scrapingant.com/v2/general', params=payload, headers=headers, timeout=90)
                        if sa_response.status_code == 200:
                            tree = html.fromstring(sa_response.content)
                            clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                            nodes = tree.xpath(clean_xpath)
                            if nodes:
                                text = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                            else:
                                print(f"  XPath '{clean_xpath}' not found in ScrapingAnt HTML payload.")
                        else:
                            print(f"  ScrapingAnt failed with status code: {sa_response.status_code}. Details: {sa_response.text}")
                    except Exception as ex:
                        print(f"  ScrapingAnt fallback failed: {ex}")

                # --- METHOD 7: Scrapingdog ---
                if text is None:
                    print(f"  Falling back to Scrapingdog for {key_name}...")
                    payload = {'api_key': SCRAPINGDOG_API_KEY, 'url': url, 'dynamic': 'true'}
                    try:
                        sd_response = std_requests.get('https://api.scrapingdog.com/scrape', params=payload, timeout=90)
                        if sd_response.status_code == 200:
                            tree = html.fromstring(sd_response.content)
                            clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                            nodes = tree.xpath(clean_xpath)
                            if nodes:
                                text = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                            else:
                                print(f"  XPath '{clean_xpath}' not found in Scrapingdog HTML payload.")
                        else:
                            print(f"  Scrapingdog failed with status code: {sd_response.status_code}. Details: {sd_response.text}")
                    except Exception as ex:
                        print(f"  Scrapingdog fallback failed: {ex}")

                # --- METHOD 8: Scrape.do ---
                if text is None:
                    print(f"  Falling back to Scrape.do for {key_name}...")
                    payload = {'token': SCRAPEDO_API_KEY, 'url': url, 'render': 'true'}
                    try:
                        sdo_response = std_requests.get('https://api.scrape.do/', params=payload, timeout=90)
                        if sdo_response.status_code == 200:
                            tree = html.fromstring(sdo_response.content)
                            clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                            nodes = tree.xpath(clean_xpath)
                            if nodes:
                                text = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                            else:
                                print(f"  XPath '{clean_xpath}' not found in Scrape.do HTML payload.")
                        else:
                            print(f"  Scrape.do failed with status code: {sdo_response.status_code}. Details: {sdo_response.text}")
                    except Exception as ex:
                        print(f"  Scrape.do fallback failed: {ex}")

            # ==========================================
            # VALIDATION & SAVE
            # ==========================================
            if text is not None:
                text = text.strip().lstrip('+$').rstrip('%').strip()
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

        # Close persistent browser context when done
        context.close()

    # Write aggregated data out to CSV
    try:
        with open(data_out_file, 'w', newline='', encoding='utf-8') as out_f:
            writer = csv.writer(out_f)
            for fund, info in existing_data.items():
                writer.writerow([fund, info["date"], info["value"]])
        print(f"Finished. Aggregated data saved to {data_out_file}.")
    except Exception as e:
        print(f"Error saving {data_out_file}: {e}")

if __name__ == "__main__":
    main()
