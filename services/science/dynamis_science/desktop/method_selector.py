"""Shared native scientific catalogue presentation for cohort and individual selectors."""
from __future__ import annotations

import html
import json


def method_html(method: dict) -> str:
    esc = lambda value: html.escape(str(value))
    def paragraph(label, value):
        return f"<p><b>{esc(label)}:</b> {esc(value)}</p>"
    def items(label, values):
        return f"<p><b>{esc(label)}</b></p><ul>" + "".join(f"<li>{esc(v)}</li>" for v in values) + "</ul>"
    return (
        paragraph(method["name"], f"{method['method_id']} v{method['version']} · {method['method_class']}")
        + paragraph("Eligibility", method["status"])
        + (items("Cannot run", method["issues"]) if method["issues"] else paragraph("Population", method.get("population", {})))
        + paragraph("Estimand", method["estimand"])
        + paragraph("Designs", ", ".join(method["supported_designs"]) or "No general execution contract")
        + paragraph("Data requirements", method["required_shape"])
        + paragraph("Units", method["units"])
        + paragraph("Timebase", method["timebase"])
        + paragraph("Missingness", method["missingness"])
        + paragraph("Uncertainty", method["uncertainty"])
        + items("Assumptions", method["assumptions"])
        + items("Diagnostics", method["diagnostics"])
        + items("Outputs", method["output_schema"])
        + paragraph("Qualification evidence", method["qualification"].get("basis", ""))
        + items("Evidence references", method["evidence_references"])
        + items("Limitations", method["limitations"])
        + paragraph("Implementation", method["implementation"])
        + paragraph("Catalogue version", method["catalogue_version"])
    )


def binding_html(run: dict) -> str:
    binding = run.get("execution", {}).get("method_binding")
    if not binding:
        return "<p>Historical run: scientific contract/source binding was not captured.</p>"
    return "<h4>Captured scientific execution contract</h4><pre>" + html.escape(json.dumps(binding, indent=2, default=str)) + "</pre>"


def run_html(run: dict, *, include_details: bool = True) -> str:
    """Readable recorded output; no statistic or uncertainty is recomputed in the UI."""
    esc = lambda value: html.escape(str(value))
    result = run.get("result", {})
    binding = run.get("execution", {}).get("method_binding", {})
    spec = binding.get("method_spec", {})
    body = (f"<h3>{esc(spec.get('name', run['method_id']))}</h3>"
            f"<p>{esc(run['method_id'])} v{esc(run['method_version'])} · {esc(spec.get('method_class', 'Historical'))}</p>"
            f"<p>{esc(spec.get('estimand', ''))}</p><p><b>Uncertainty:</b> {esc(spec.get('uncertainty', 'See recorded result'))}</p>"
            f"<p>Run {esc(run['id'])} · data revision {esc(run.get('data_revision_id', run.get('snapshot_id')))} · digest {esc(run.get('result_digest'))}</p>")
    if result.get("points") and result.get("axis"):
        axis = result["axis"]
        body += f"<table cellpadding='4'><tr><th>{esc(axis)}</th><th>Athletes</th><th>Mean</th><th>SD</th><th>95% CI low</th><th>95% CI high</th></tr>"
        for point in result["points"]:
            body += "<tr>" + "".join(f"<td>{esc(point.get(key) if point.get(key) is not None else '—')}</td>"
                                      for key in (axis, "n", "mean", "sd", "ci_low", "ci_high")) + "</tr>"
        body += f"</table><p>Units: {esc(binding.get('outcome', {}).get('unit', 'as recorded'))}. Repeated trials are averaged within athlete.</p>"
    body += "<p><b>Limitations</b></p><ul>" + "".join(f"<li>{esc(v)}</li>" for v in result.get("limitations", [])) + "</ul>"
    if include_details:
        body += "<h4>Recorded result and diagnostics</h4><pre>" + esc(json.dumps({"result": result, "diagnostics": run.get("diagnostics")}, indent=2, default=str)) + "</pre>"
        body += binding_html(run)
    return body
