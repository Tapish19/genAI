"""Screenshot unmodified evaluation records in a headless local browser."""
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

def main():
    with sync_playwright() as playwright:
        try:
            browser=playwright.chromium.launch(headless=True)
        except Exception:
            # Reuse an installed Chrome binary with a fresh, private headless profile.
            browser=playwright.chromium.launch(headless=True,channel='chrome')
        try:
            print('Headless browser: '+browser.version,flush=True)
            if '--check' in sys.argv: return
            page=browser.new_page(viewport={'width':1260,'height':1000},device_scale_factor=1)
            page.goto((ROOT/'artifacts/evidence.html').as_uri())
            page.screenshot(path=str(ROOT/'artifacts/evidence-full.png'),full_page=True)
            for section in ['query','idempotency','judge','position','adversarial']:
                page.locator('#'+section).screenshot(path=str(ROOT/'artifacts'/f'{section}.png'))
            print('Captured five screenshots of actual audit and evaluation records.',flush=True)
        finally:
            browser.close()

if __name__=='__main__': main()
