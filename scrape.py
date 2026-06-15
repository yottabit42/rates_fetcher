import sys
import re
import json
import time
from datetime import date
from curl_cffi import requests
import requests as std_requests
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

        filename = parts[0]
        url = parts[1]
        xpath = parts[2]

        print(f"Processing {filename} from {url}...")

        text = None
        for attempt in range(3):
            if attempt > 0:
                print(f"  Retry attempt {attempt + 1}/3 for {filename}...")
                time.sleep(5) # short pause before retry

            try:
                headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cache-Control": "max-age=0",
                }
                response = requests.get(url, headers=headers, impersonate="chrome", timeout=10)

                if response.status_code == 200:
                    tree = html.fromstring(response.text)

                    # Evaluate the exact xpath against the raw HTML
                    nodes = tree.xpath(xpath)
                    if nodes:
                        # lxml xpath can return a string directly if the xpath ends in text(),
                        # or it can return an Element.
                        if isinstance(nodes[0], str):
                            text = nodes[0]
                        else:
                            text = nodes[0].text_content()
                    else:
                        print(f"  XPath '{xpath}' not found in raw HTML payload for {filename}.")
                else:
                    print(f"  curl_cffi failed with status code: {response.status_code}")
            except Exception as ex:
                print(f"  curl_cffi attempt failed: {ex}")

            # Second fallback specific to Fidelity targets
            if text is None and 'fidelity.com' in url.lower():
                print(f"  Attempting Fidelity Legacy JSON API fallback for {filename}...")
                try:
                    fq_url = f"https://fastquote.fidelity.com/service/quote/json?productid=embeddedquotes&symbols={filename}"
                    fq_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                    fq_response = std_requests.get(fq_url, headers=fq_headers, timeout=10)
                    if fq_response.status_code == 200:
                        # Strip the leading '(' and trailing ')' from JSONP response
                        clean_json = fq_response.text.strip()[1:-1]
                        data = json.loads(clean_json)
                        if "QUOTES" in data and filename in data["QUOTES"]:
                            text = data["QUOTES"][filename].get("YIELD_7_DAY")
                            if not text:
                                print(f"  JSON API response did not contain YIELD_7_DAY for {filename}.")
                        else:
                            print(f"  JSON API response missing expected QUOTES payload for {filename}.")
                    else:
                        print(f"  Fidelity Legacy JSON API failed with status code: {fq_response.status_code}")
                except Exception as ex:
                    print(f"  Fidelity Legacy JSON API fallback failed: {ex}")

            # If text was successfully extracted, break out of the retry loop
            if text is not None:
                break

        if text is not None:
            text = text.strip().rstrip('%').strip()
            with open(f"{filename}.txt", "w") as out_f:
                out_f.write(f"{today}\n{text}\n")
            print(f"  Success: Extracted '{text}' and saved to {filename}.txt")
        else:
            print(f"  FATAL: Failed to extract data for {filename} after 3 attempts. Skipping file write to preserve old data.")

        print("  Sleeping for 10 seconds before next request to avoid bot detection...")
        time.sleep(10)

if __name__ == "__main__":
    main()
