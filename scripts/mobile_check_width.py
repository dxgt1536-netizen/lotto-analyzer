from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
PAGES = ["/", "/board", "/simulator", "/stats"]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 375, "height": 812})
    for path in PAGES:
        page.goto(BASE + path, wait_until="networkidle")
        scroll_width = page.evaluate("document.documentElement.scrollWidth")
        client_width = page.evaluate("document.documentElement.clientWidth")
        status = "OVERFLOW" if scroll_width > client_width else "OK"
        print(f"{path}: scrollWidth={scroll_width} clientWidth={client_width} -> {status}")
    browser.close()
