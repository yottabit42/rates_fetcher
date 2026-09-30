import sys
import re
import json
import csv
import os
import time
import html as html_lib
from urllib.parse import urlparse
from datetime import datetime, date
import requests as std_requests
from curl_cffi import requests as cffi_requests
from lxml import html

# Gracefully import Playwright if installed in current environment (e.g. inside Docker container)
try:
    from rebrowser_playwright.sync_api import sync_playwright
except ImportError:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sync_playwright = None

try:
    import zoneinfo
except ImportError:
    zoneinfo = None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scrape.py <targets.tsv> [key1] [key2] ...")
        sys.exit(1)

    targets_file = sys.argv[1]
    target_keys = set(sys.argv[2:])

    try:
        with open(targets_file, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Could not find '{targets_file}'.")
        sys.exit(1)

    # Determine today's date based on custom timezone environment variable
    tz_env = os.environ.get("SCRAPER_TZ") or os.environ.get("TZ")
    print(f"DEBUG: Environment Timezone variable evaluated to: '{tz_env}'")

    if tz_env and zoneinfo:
        try:
            tz = zoneinfo.ZoneInfo(tz_env)
            now = datetime.now(tz)
            today = now.strftime("%Y-%m-%d")
            print(f"DEBUG: Using zoneinfo. Current time in {tz_env} is: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except Exception as e:
            print(f"Warning: Could not load timezone '{tz_env}' using zoneinfo: {e}. Falling back to tzset.")
            original_tz = os.environ.get('TZ')
            os.environ['TZ'] = tz_env
            if hasattr(time, 'tzset'):
                time.tzset()
            today = date.today().strftime("%Y-%m-%d")
            if original_tz is not None:
                os.environ['TZ'] = original_tz
            else:
                del os.environ['TZ']
    else:
        if tz_env:
            original_tz = os.environ.get('TZ')
            os.environ['TZ'] = tz_env
            if hasattr(time, 'tzset'):
                time.tzset()
        today = date.today().strftime("%Y-%m-%d")

    print(f"DEBUG: Evaluated 'today' date string: {today}")

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


    # Initialize browser variables
    pw_instance = None
    pw_context = None
    page = None
    selenium_driver = None

    if sync_playwright is not None:
        try:
            pw_instance = sync_playwright().start()
            pw_context = pw_instance.chromium.launch_persistent_context(
                user_data_dir="/tmp/playwright_user_data",
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = pw_context.pages[0] if pw_context.pages else pw_context.new_page()
        except Exception as e:
            print(f"  Warning: Could not launch Playwright browser context: {e}")

    try:
        for line in lines:
            line = line.strip().replace('\ufeff', '').replace('\r', '')
            if not line:
                continue

            parts = line.split('\t')
            if len(parts) >= 3:
                key_name = parts[0].strip()
                url = parts[1].strip(' "\'')
                xpath = parts[2].strip()
                override_flag = parts[3].strip().lower() if len(parts) >= 4 else ""
            else:
                parts = line.split(maxsplit=3)
                if len(parts) < 3:
                    print(f"Skipping malformed line: {line}")
                    continue
                key_name = parts[0].strip()
                url = parts[1].strip(' "\'')
                xpath = parts[2].strip()
                override_flag = parts[3].strip().lower() if len(parts) >= 4 else ""

            if target_keys and key_name not in target_keys:
                continue

            # Skip if already updated today (unless explicitly requested in CLI args)
            if not target_keys and key_name in existing_data and existing_data[key_name]["date"] == today:
                print(f"Skipping {key_name}: Already updated today ({today}).")
                continue


            print(f"Processing {key_name} from URL: [{url}]")
            text = None

            # =========================================================
            # METHOD 1: FIDELITY LEGACY JSON API
            # =========================================================
            if not override_flag and ("fidelity.com" in url or "investor.vanguard.com/investment-products/mutual-funds" in url):
                print(f"  Attempting Fidelity Legacy JSON API for {key_name}...")
                api_url = f"https://fastquote.fidelity.com/service/quote/json?productid=embeddedquotes&symbols={key_name}"
                try:
                    fq_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    fq_response = std_requests.get(api_url, headers=fq_headers, timeout=8)
                    if fq_response.status_code == 200:
                        clean_json = fq_response.text.strip()[1:-1]
                        data = json.loads(clean_json)
                        if "QUOTES" in data and key_name in data["QUOTES"]:
                            text = data["QUOTES"][key_name].get("YIELD_7_DAY")
                            if text:
                                print(f"  Fidelity API succeeded for {key_name}: {text}")
                except Exception as ex:
                    print(f"  Fidelity API failed for {key_name}: {ex}")

            # =========================================================
            # METHOD 2: DIRECT IN-PAGE & JSON-LD EXTRACTION (via curl_cffi)
            # =========================================================
            html_content = None
            if text is None:
                try:
                    cffi_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9"
                    }
                    cffi_resp = cffi_requests.get(url, headers=cffi_headers, impersonate="chrome124", timeout=15)
                    if cffi_resp.status_code == 200:
                        html_content = cffi_resp.text
                except Exception as ex:
                    html_content = None

            if not override_flag and text is None and html_content:
                # 2A. Vanguard in-page JSON state
                if "investor.vanguard.com" in url:
                    unescaped = html_lib.unescape(html_content)
                    m = re.search(r'"secYield"\s*:\s*"([0-9.]+)%?"', unescaped)
                    if m:
                        text = m.group(1)
                        print(f"  Vanguard in-page state succeeded for {key_name}: {text}")
                    else:
                        m = re.search(r'"compoundYieldPct"\s*:\s*"([0-9.]+)%?"', unescaped)
                        if m:
                            text = m.group(1)
                            print(f"  Vanguard in-page state succeeded for {key_name}: {text}")

                # 2B. WisdomTree semantic card / embedded state
                if text is None and "wisdomtree.com" in url:
                    m = re.search(r'<h3[^>]*>([0-9.]+)%?</h3>\s*<p[^>]*>\s*30-day SEC yield', html_content, re.I)
                    if m:
                        text = m.group(1)
                        print(f"  WisdomTree semantic card succeeded for {key_name}: {text}")
                    else:
                        m = re.search(r'"thirtyDaySecYield"[^"]*"([0-9.]+)%?"', html_content, re.I)
                        if m:
                            text = m.group(1)
                            print(f"  WisdomTree embedded state succeeded for {key_name}: {text}")

                # 2C. iShares JSON-LD & Walrus data attributes
                if text is None and "ishares.com" in url:
                    m = re.search(r'30 Day SEC Yield as of",\s*"value"\s*:\s*"([0-9.]+)%?"', html_content)
                    if m:
                        text = m.group(1)
                        print(f"  iShares JSON-LD SEC Yield succeeded for {key_name}: {text}")
                    else:
                        m = re.search(r'data-id="fundamentalsAndRisk-thirtyDaySecYield-data"[^>]*>([0-9.]+)%?<', html_content)
                        if m:
                            text = m.group(1)
                            print(f"  iShares Walrus SEC Yield succeeded for {key_name}: {text}")

            # =========================================================
            # METHOD 3: curl_cffi HTTP IMPERSONATION WITH XPATH
            # =========================================================
            if text is None and html_content:
                print(f"  Attempting curl_cffi XPath for {key_name}...")
                try:
                    tree = html.fromstring(html_content.encode("utf-8", errors="ignore"))
                    clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                    nodes = tree.xpath(clean_xpath)
                    if nodes:
                        val = nodes[0] if isinstance(nodes[0], str) else nodes[0].text_content()
                        if val and val.strip():
                            text = val.strip()
                            print(f"  curl_cffi XPath succeeded for {key_name}: {text}")
                except Exception as ex:
                    print(f"  curl_cffi XPath evaluation failed: {ex}")

            # =========================================================
            # METHOD 4: rebrowser-playwright WITH SHADOW-DOM TRAVERSAL
            # =========================================================
            if text is None and page is not None:
                print(f"  Falling back to rebrowser-playwright for {key_name}...")
                try:
                    page.goto(url, wait_until="load", timeout=20000)
                    page.wait_for_timeout(1000)

                    clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                    try:
                        locator = page.locator(f"xpath={clean_xpath}").first
                        val = locator.text_content(timeout=5000)
                        if val and val.strip():
                            text = val.strip()
                            print(f"  Playwright locator succeeded for {key_name}: {text}")
                    except Exception as e:
                        print(f"  Playwright locator failed for {key_name}: {e}")
                except Exception as e:
                    print(f"  Playwright failed for {key_name}: {e}")

            # =========================================================
            # METHOD 5: SELENIUM WEBDRIVER FALLBACK
            # =========================================================
            if text is None:
                print(f"  Falling back to Selenium WebDriver for {key_name}...")
                try:
                    if selenium_driver is None:
                        from selenium import webdriver
                        from selenium.webdriver.chrome.options import Options
                        options = Options()
                        options.add_argument("--headless=new")
                        options.add_argument("--no-sandbox")
                        options.add_argument("--disable-dev-shm-usage")
                        options.add_argument("--disable-blink-features=AutomationControlled")
                        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                        options.add_experimental_option("excludeSwitches", ["enable-automation"])
                        options.add_experimental_option('useAutomationExtension', False)
                        selenium_driver = webdriver.Chrome(options=options)
                        selenium_driver.set_page_load_timeout(25)

                    from selenium.webdriver.common.by import By
                    selenium_driver.get(url)
                    time.sleep(2)
                    clean_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                    try:
                        elem = selenium_driver.find_element(By.XPATH, clean_xpath)
                        if elem and elem.text.strip():
                            text = elem.text.strip()
                            print(f"  Selenium XPath succeeded for {key_name}: {text}")
                    except Exception as e:
                        print(f"  Selenium XPath failed for {key_name}: {e}")
                except Exception as e:
                    print(f"  Selenium failed for {key_name}: {e}")

            # =========================================================
            # VALIDATION & SAVE
            # =========================================================
            if text is not None:
                clean_text = text.strip().lstrip('+$').rstrip('%').strip()
                m_num = re.search(r'([0-9]+\.[0-9]+)', clean_text)
                if m_num:
                    clean_text = m_num.group(1)

                is_positive_float = False
                try:
                    parsed_value = float(clean_text)
                    if parsed_value > 0:
                        is_positive_float = True
                except ValueError:
                    pass

                if is_positive_float:
                    existing_data[key_name] = {"date": today, "value": clean_text}
                    print(f"  Success: Extracted '{clean_text}' for {key_name}.")
                else:
                    print(f"  FATAL: Extracted value '{text}' for {key_name} is not a positive floating-point number. Preserving old data.")
            else:
                print(f"  FATAL: Failed to extract data for {key_name} after exhausting all fallback methods. Preserving old data.")

    finally:
        # Cleanup browser resources
        if pw_context:
            try:
                pw_context.close()
            except Exception:
                pass
        if pw_instance:
            try:
                pw_instance.stop()
            except Exception:
                pass
        if selenium_driver:
            try:
                selenium_driver.quit()
            except Exception:
                pass

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
