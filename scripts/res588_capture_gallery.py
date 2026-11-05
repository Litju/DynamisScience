from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design" / "res588-ux" / "compare"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 2300, "height": 1200}, device_scale_factor=1)
    page.goto("http://127.0.0.1:4173/docs/design/res588-ux/compare/index.html", wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(700)
    for section in ["directions", "compact", "current-vs-a"]:
        el = page.locator(f"#{section}")
        el.screenshot(path=str(OUT / f"{section}.png"))
        print(section, el.bounding_box())
    page.screenshot(path=str(OUT / "gallery-full.png"), full_page=True)
    browser.close()
