from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design" / "res588-ux" / "compare"
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1720, "height": 1200})
    page.goto("http://127.0.0.1:4173/docs/design/res588-ux/compare/performance-os.html", wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUT / "performance-os-1440.png"), full_page=True)
    page.screenshot(path=str(OUT / "performance-os-viewport.png"), full_page=False)
    browser.close()
print("performance-os gallery captured")
