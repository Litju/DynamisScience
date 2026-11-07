"""Read the generated scientific definition catalogue without HTTP transport."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .generate import ARTIFACT_DIR


def _read(name: str, default: Any) -> Any:
    path = ARTIFACT_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def get_scientific_library() -> dict[str, Any]:
    registry = _read("registry.json", {})
    study = _read("study.json", {})
    runs = _read("analysis_runs.json", [])
    specs = study.get("analysis_specs", [])
    metric_usage: dict[str, list[str]] = {}
    for spec in specs:
        metric_usage.setdefault(spec["outcome_metric_id"], []).append(spec["id"])
    method_runs: dict[str, list[str]] = {}
    for run in runs:
        spec = (run.get("execution") or {}).get("analysis_spec") or {}
        metric_id = spec.get("outcome_metric_id")
        if metric_id:
            metric_usage.setdefault(metric_id, []).append(run["id"])
        method_runs.setdefault(run["method_id"], []).append(run["id"])
    return {
        **registry,
        "metrics": [
            {
                **metric,
                "usages": sorted(set(metric_usage.get(metric["id"], []))),
            }
            for metric in registry.get("metrics", [])
        ],
        "methods": [
            {
                **method,
                "runs": method_runs.get(method["id"], []),
                "specs": [
                    spec["id"]
                    for spec in specs
                    if spec["method_id"] == method["id"]
                ],
            }
            for method in registry.get("methods", [])
        ],
        "model_spec": _read("model_spec.json", {}),
    }
