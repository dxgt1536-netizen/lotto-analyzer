import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
BASE = "http://127.0.0.1:5000"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 375, "height": 700}, device_scale_factor=2)
    page.goto(BASE + "/stats", wait_until="networkidle")
    page.locator(".card").first.screenshot(path=str(OUT_DIR / "stats_chart1.png"))
    browser.close()
