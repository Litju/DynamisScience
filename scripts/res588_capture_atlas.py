from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design" / "res588-ux" / "screens"
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://127.0.0.1:4173/docs/design/res588-ux/prototypes/f/atlas.html", wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    h = page.evaluate("document.querySelector('.atlas').scrollHeight + 60")
    print("atlas height", h)
    page.set_viewport_size({"width": 1440, "height": max(900, int(h))})
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / "f-atlas-1440x900.png"), full_page=False)
    browser.close()
