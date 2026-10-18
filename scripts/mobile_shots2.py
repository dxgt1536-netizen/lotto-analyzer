import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
BASE = "http://127.0.0.1:5000"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 375, "height": 812}, device_scale_factor=2)

    page.goto(BASE + "/", wait_until="networkidle")
    page.screenshot(path=str(OUT_DIR / "nav_closed.png"))

    page.click("#navToggle")
    page.wait_for_timeout(200)
    page.screenshot(path=str(OUT_DIR / "nav_open.png"))

    page.goto(BASE + "/tax-calculator", wait_until="networkidle")
    page.screenshot(path=str(OUT_DIR / "tax_top.png"))

    browser.close()
