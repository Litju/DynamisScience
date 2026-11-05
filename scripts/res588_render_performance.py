from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design" / "res588-ux" / "screens"
with sync_playwright() as p:
    browser = p.chromium.launch()
    for name, file, full in [("f-command", "command.html", False), ("f-atlas", "atlas.html", True)]:
        for w, h, label in [(1440, 900, "1440x900"), (1280, 800, "1280x800")]:
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            errors = []
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.goto(f"http://127.0.0.1:4173/docs/design/res588-ux/prototypes/f/{file}", wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(700)
            page.screenshot(path=str(OUT / f"{name}-{label}.png"), full_page=full)
            print(name, label, page.evaluate("({sw:document.documentElement.scrollWidth,iw:innerWidth})"), errors)
            page.close()
    browser.close()
