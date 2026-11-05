from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3001"
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    bad = []
    page.on("response", lambda r: bad.append((r.status, r.url)) if r.status >= 400 else None)
    page.goto(BASE + "/research", wait_until="networkidle")
    page.wait_for_timeout(1000)
    page.goto(BASE + "/research/studies/STUDY-U-EE7514BB", wait_until="networkidle")
    page.wait_for_timeout(1000)
    print("BAD", bad)
    browser.close()
