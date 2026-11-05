"""RES-588 Step A production UX audit.

Read-only: navigates the running production build, captures screenshots at the
required desktop viewports and measures layout/interaction facts. It does not
create, update, freeze, run or delete any research object.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3001"
OUT = Path(__file__).resolve().parents[1] / "docs" / "design" / "res588-ux" / "audit" / "production"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("research-home", "/research"),
    ("project-cmj", "/research/projects/PRJ-FB8A479E"),
    ("study-mendeley", "/research/studies/STUDY-U-EE7514BB"),
    ("study-mendeley-setup", "/research/studies/STUDY-U-EE7514BB?mode=setup"),
    ("study-mendeley-report", "/research/studies/STUDY-U-EE7514BB?mode=report"),
    ("monitoring-program", "/research/studies/PROG-U-7B9AB9FE"),
    ("study-movesmart", "/research/studies/STUDY-U-AE0D7A3C"),
    ("data", "/data"),
    ("dataset-detail", "/data/DS-REAL-MENDELEY-2C44490E08AD"),
    ("library", "/library"),
    ("admission", "/data/admission"),
]

VIEWPORTS = [(1440, 900), (1280, 800), (1024, 800)]

MEASURE_JS = """
() => {
  const rect = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
  };
  const all = (sel) => Array.from(document.querySelectorAll(sel));
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const canvases = all('canvas').filter(visible).map((c) => {
    const r = c.getBoundingClientRect();
    return {w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top)};
  });
  const charts = all('[data-zr-dom-id], .echarts-for-react, .chart, .chart-frame').filter(visible).map((el) => {
    const r = el.getBoundingClientRect();
    return {tag: el.tagName, cls: el.className && String(el.className).slice(0,80), w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top)};
  });
  const overflow = all('*').filter((el) => visible(el) && el.scrollWidth > el.clientWidth + 2).slice(0, 12).map((el) => ({
    tag: el.tagName, cls: String(el.className).slice(0, 90), sw: el.scrollWidth, cw: el.clientWidth,
  }));
  const buttons = all('button, a[href]').filter(visible);
  const blocks = all('.block').filter(visible);
  const headings = all('h1,h2,h3,h4').filter(visible).slice(0, 25).map((el) => ({
    tag: el.tagName, text: el.textContent.trim().slice(0, 100), top: Math.round(el.getBoundingClientRect().top),
  }));
  return {
    viewport: {w: innerWidth, h: innerHeight},
    doc: {scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth,
          scrollH: document.documentElement.scrollHeight, clientH: document.documentElement.clientHeight},
    regions: {
      globalBar: rect('.gbar'), page: rect('.page'), pageInner: rect('.page-inner'),
      studyBar: rect('.sbar'), contextBar: rect('.ctx'), studyBody: rect('.study-body'),
      tree: rect('.pane-tree'), bench: rect('.pane-bench'), inspector: rect('.pane-insp'),
      benchInner: rect('.bench-inner'), firstBlock: rect('.block'), report: rect('.report'),
    },
    counts: {
      visibleButtonsLinks: buttons.length, blocks: blocks.length,
      collapsedBlocks: all('.block.is-collapsed').length,
      tables: all('table').filter(visible).length,
      inputs: all('input,select,textarea').filter(visible).length,
      canvases: canvases.length,
    },
    canvases, charts,
    headings,
    overflow,
  };
}
"""

results = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    for width, height in VIEWPORTS:
        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        page = context.new_page()
        console_errors: list[str] = []
        page_errors: list[str] = []
        failed: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on("requestfailed", lambda req: failed.append(f"{req.method} {req.url} :: {req.failure}"))
        for slug, path in PAGES:
            url = BASE + path
            response = page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(600)
            shot_path = OUT / f"{slug}-{width}x{height}.png"
            page.screenshot(path=str(shot_path), full_page=False)
            metrics = page.evaluate(MEASURE_JS)
            metrics.update({"slug": slug, "path": path, "status": response.status if response else None})
            results.append(metrics)
            if width == 1440 and slug in ("study-mendeley", "monitoring-program"):
                page.screenshot(path=str(OUT / f"{slug}-{width}x{height}-full.png"), full_page=True)
        # Keyboard check on the study page.
        page.goto(BASE + "/research/studies/STUDY-U-EE7514BB", wait_until="networkidle")
        page.keyboard.press("Control+K")
        page.wait_for_timeout(300)
        palette_open = page.locator('[role="dialog"], .palette, .cmdk').count() > 0
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        palette_closed = page.locator('[role="dialog"], .palette, .cmdk').count() == 0
        errors_payload = {"width": width, "console": console_errors, "page": page_errors, "failed": failed,
                          "palette_open": palette_open, "palette_closed": palette_closed}
        (OUT / f"runtime-{width}x{height}.json").write_text(json.dumps(errors_payload, indent=2), encoding="utf-8")
        context.close()
    browser.close()

(OUT / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"captured {len(results)} page/viewport combinations")
for item in results:
    if item["viewport"]["w"] == 1440:
        print(item["slug"], item["status"], "blocks", item["counts"]["blocks"],
              "canvas", item["counts"]["canvases"], "buttons", item["counts"]["visibleButtonsLinks"],
              "docH", item["doc"]["scrollH"], "overflowX", item["doc"]["scrollW"] > item["doc"]["clientW"])
