from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design" / "res588-ux" / "screens"
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto("http://127.0.0.1:4173/docs/design/res588-ux/prototypes/d/analyze.html", wait_until="networkidle")
    page.click("#notes-toggle")
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / "d-analyze-1280x800-notes.png"))
    drawer = page.evaluate("() => { const m = document.getElementById('evidence-margin'); const r = m.getBoundingClientRect(); return {display: getComputedStyle(m).display, w: Math.round(r.width), visible: r.width > 0}; }")
    print("drawer", drawer, "errors", errors)
    browser.close()
