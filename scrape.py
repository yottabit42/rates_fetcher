import sys
import re
from datetime import date
from playwright.sync_api import sync_playwright

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

    with sync_playwright() as p:
        # Chromium requires --no-sandbox to run as root inside a Docker container
        browser = p.chromium.launch(args=["--no-sandbox"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
        page = context.new_page()

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

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # Removing trailing text() or text()[n] so wait_for_selector works
                wait_xpath = re.sub(r'/text\(\)(\[\d+\])?$', '', xpath)
                page.wait_for_selector(f"xpath={wait_xpath}", timeout=30000)

                js_code = f"""
                () => {{
                    let result = document.evaluate(`{xpath}`, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    return result.singleNodeValue ? result.singleNodeValue.nodeValue || result.singleNodeValue.textContent : null;
                }}
                """
                text = page.evaluate(js_code)

                if text is not None:
                    text = text.strip().rstrip('%').strip()
                else:
                    text = "N/A"

                with open(f"{filename}.txt", "w") as out_f:
                    out_f.write(f"{today}\n{text}\n")

                print(f"  Success: Extracted '{text}' and saved to {filename}.txt")
            except Exception as e:
                print(f"  Error processing {filename}: {e}")

        browser.close()

if __name__ == "__main__":
    main()
