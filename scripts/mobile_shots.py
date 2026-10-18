import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
BASE = "http://127.0.0.1:5000"
PAGES = {
    "index": "/",
    "stats": "/stats",
    "recommend": "/recommend",
    "fortune": "/fortune",
    "simulator": "/simulator",
    "tax": "/tax-calculator",
    "prizes": "/prizes",
    "prize_detail": "/prizes/1237",
    "other_games": "/other-games",
    "board": "/board",
}

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 375, "height": 812}, device_scale_factor=2)
    for name, path in PAGES.items():
        page.goto(BASE + path, wait_until="networkidle")
        page.screenshot(path=str(OUT_DIR / f"mobile_{name}.png"), full_page=True)
        print("captured", name)
    browser.close()
