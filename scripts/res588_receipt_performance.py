import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design" / "res588-ux" / "screens"
receipt = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    for page_name, file in [("command", "command.html"), ("atlas", "atlas.html")]:
        for w, h, label in [(1440, 900, "1440x900"), (1280, 800, "1280x800")]:
            page = browser.new_page(viewport={"width": w, "height": h})
            errors = []
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.goto(f"http://127.0.0.1:4173/docs/design/res588-ux/prototypes/f/{file}", wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(500)
            m = page.evaluate("""
            () => ({
              viewport: {w: innerWidth, h: innerHeight},
              scroll: {w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight},
              main: {h: document.querySelector('.main')?.scrollHeight, c: document.querySelector('.main')?.clientHeight},
              atlas: {h: document.querySelector('.atlas')?.scrollHeight, c: document.querySelector('.atlas')?.clientHeight}
            })
            """)
            receipt.append({"page": page_name, "viewport": label, "metrics": m, "console": errors})
            page.close()
    browser.close()
(OUT / "render-receipt-f.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
