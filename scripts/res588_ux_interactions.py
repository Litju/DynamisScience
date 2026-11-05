"""Supplementary measurements for the RES-588 UX audit."""
from __future__ import annotations

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3001"
OUT = Path(__file__).resolve().parents[1] / "docs" / "design" / "res588-ux" / "audit" / "production"

payload: dict = {}

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # Click path: Research -> project -> study.
    page.goto(BASE + "/research", wait_until="networkidle")
    page.locator('a[href="/research/projects/PRJ-FB8A479E"]').click()
    page.wait_for_load_state("networkidle")
    project_url = page.url
    page.locator('a[href="/research/studies/STUDY-U-EE7514BB"]').first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".bench")
    study_url = page.url

    blocks = page.evaluate("""
    () => Array.from(document.querySelectorAll('.block')).map((el, i) => {
      const r = el.getBoundingClientRect();
      const head = el.querySelector('.block-type');
      return {index: i + 1, type: head ? head.textContent.trim() : '', top: Math.round(r.top + window.scrollY), h: Math.round(r.height)};
    })
    """)
    page_h = page.evaluate("document.documentElement.scrollHeight")
    viewport_h = page.evaluate("window.innerHeight")

    # Measure scroll needed to bring the analysis result into view.
    analysis = page.locator('.block', has_text="Analysis").first
    analysis.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    scroll_y = page.evaluate("document.querySelector('.bench').scrollTop")
    bench_scroll_height = page.evaluate("document.querySelector('.bench').scrollHeight")
    bench_client_height = page.evaluate("document.querySelector('.bench').clientHeight")
    chart_boxes = page.evaluate("""
    () => Array.from(document.querySelectorAll('canvas')).map((c) => {
      const r = c.getBoundingClientRect();
      return {w: Math.round(r.width), h: Math.round(r.height), document_top: Math.round(r.top + document.querySelector('.bench').scrollTop)};
    })
    """)

    # Read the first 12 focus stops in the study workspace.
    page.goto(BASE + "/research/studies/STUDY-U-EE7514BB", wait_until="networkidle")
    page.wait_for_selector(".bench")
    page.locator("body").click(position={"x": 5, "y": 5})
    stops = []
    for _ in range(14):
        page.keyboard.press("Tab")
        stops.append(page.evaluate("""
        () => {
          const el = document.activeElement;
          return {tag: el.tagName, text: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 70),
                  cls: String(el.className).slice(0, 50)};
        }
        """))

    # Duplication of navigational labels.
    labels = page.evaluate("""
    () => {
      const wanted = ['Study setup','Research question','Hypotheses','Single arm','Occasions','DS-REAL-MENDELEY-2C44490E08AD','Cohort'];
      const out = {};
      for (const w of wanted) {
        out[w] = (document.body.innerText.match(new RegExp(w.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'), 'g')) || []).length;
      }
      return out;
    }
    """)
    page.keyboard.press("Control+K")
    page.wait_for_timeout(250)
    palette = page.locator('[role="dialog"], .palette, .cmdk').first
    palette_visible = palette.count() > 0 and palette.is_visible()
    palette_text = palette.inner_text()[:500] if palette_visible else None
    page.keyboard.press("Escape")

    payload = {
        "click_path": {"project_url": project_url, "study_url": study_url, "clicks_from_research_home": 2},
        "study_document": {
            "page_scroll_height": page_h,
            "viewport_height": viewport_h,
            "scroll_screens": round(page_h / viewport_h, 2),
            "blocks": blocks,
            "analysis_scroll_y": scroll_y,
            "bench_scroll_height": bench_scroll_height,
            "bench_client_height": bench_client_height,
            "bench_scroll_screens": round(bench_scroll_height / bench_client_height, 2),
            "chart_boxes": chart_boxes,
        },
        "focus_stops": stops,
        "label_occurrences": labels,
        "palette": {"visible": palette_visible, "text": palette_text},
    }
    browser.close()

(OUT / "interaction-audit.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps(payload, indent=2)[:5000])
