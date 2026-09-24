"""Computed provenance graph.

The lineage graph is derived from the stored artefacts, not asserted. Every node
carries the metadata needed to inspect it, and every edge is created because a
stored artefact actually references the source it is derived from.
"""

from __future__ import annotations

from typing import Any


def _node(node_id: str, kind: str, label: str, metadata: str, **extra: Any) -> dict[str, Any]:
    return {"id": node_id, "kind": kind, "label": label, "metadata": metadata, **extra}


def _edge(source: str, target: str, relation: str, label: str) -> dict[str, Any]:
    return {"id": f"LE-{source}->{target}", "source": source, "target": target, "relation": relation, "label": label}


def build_lineage_graph(
    *,
    artifact_id: str,
    snapshot: dict[str, Any],
    study: dict[str, Any],
    registry: dict[str, Any],
    runs: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    figures: list[dict[str, Any]],
    report: dict[str, Any],
    model_spec: dict[str, Any],
    model_run: dict[str, Any],
    trial_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    snapshot_id = snapshot.get("id", "DS-SYNTH-001")
    study_id = study.get("study", {}).get("id", "STUDY-001")
    specs = {spec["id"]: spec for spec in study.get("analysis_specs", [])}
    cohort = study.get("cohort", {})
    protocol_ids = {protocol["id"]: protocol for protocol in study.get("protocols", [])}
    metric_defs = {metric["id"]: metric for metric in registry.get("metrics", [])}

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    def add(node: dict[str, Any]) -> None:
        nodes.setdefault(node["id"], node)

    def link(source: str, target: str, relation: str, label: str) -> None:
        edge = _edge(source, target, relation, label)
        edges.setdefault(edge["id"], edge)

    add(_node(
        "GEN-001",
        "generator",
        "Deterministic synthetic generator",
        f"{snapshot.get('generator_version', 'dynamis-synthetic@1.0.0')} · seed {snapshot.get('seed')}",
        detail={
            "generator_version": snapshot.get("generator_version"),
            "schema_version": snapshot.get("schema_version"),
            "seed": snapshot.get("seed"),
            "generated_at": snapshot.get("generated_at"),
            "source": snapshot.get("provenance", {}).get("generator"),
        },
    ))
    add(_node(
        snapshot_id,
        "snapshot",
        snapshot_id,
        "immutable analytical snapshot",
        detail={
            "label": snapshot.get("label"),
            "row_counts": snapshot.get("row_counts"),
            "checksums": snapshot.get("checksums"),
            "generated_at": snapshot.get("generated_at"),
        },
    ))
    link("GEN-001", snapshot_id, "generated", "deterministic generation")

    for protocol_id, protocol in protocol_ids.items():
        add(_node(
            protocol_id,
            "protocol",
            protocol.get("name", protocol_id),
            f"{protocol.get('frequency', '')} · {protocol.get('status', '')}",
            detail=protocol,
        ))
        link("GEN-001", protocol_id, "implements", "measurement contract")

    for metric_id, metric in metric_defs.items():
        add(_node(
            metric_id,
            "metric",
            f"{metric.get('name', metric_id)}",
            f"{metric.get('algorithm', '')}@{metric.get('version', '')}",
            detail=metric,
        ))
        link(protocol_id := metric.get("protocol_id", "PROT-CMJ"), metric_id, "defines", "metric contract")
        link(metric_id, snapshot_id, "included_in", "materialised in snapshot")

    add(_node(
        cohort.get("id", "COHORT-001"),
        "cohort",
        cohort.get("name", "Frozen cohort"),
        f"{cohort.get('status', 'FROZEN')} · {len(cohort.get('subject_ids', []))} athletes",
        detail=cohort,
    ))
    link(snapshot_id, cohort.get("id", "COHORT-001"), "filtered_into", "frozen eligibility rule")

    for spec_id, spec in specs.items():
        add(_node(
            spec_id,
            "spec",
            spec.get("name", spec_id),
            f"{spec.get('method_id', '')} · {spec.get('status', '')}",
            detail=spec,
        ))
        link(cohort.get("id", "COHORT-001"), spec_id, "scopes", "cohort and metric selection")

    for run in runs:
        spec_id = run.get("analysis_spec_id", "")
        add(_node(
            run.get("id", "RUN-0001"),
            "run",
            run.get("id", "RUN-0001"),
            f"{run.get('method_id', '')} · {run.get('status', '')}",
            detail={
                "analysis_spec_id": spec_id,
                "method_id": run.get("method_id"),
                "snapshot_id": run.get("snapshot_id"),
                "cohort_id": run.get("cohort_id"),
                "status": run.get("status"),
                "created_at": run.get("created_at"),
                "duration_ms": run.get("duration_ms"),
                "seed": run.get("seed"),
                "software_versions": run.get("software_versions"),
                "reproducibility_key": run.get("reproducibility_key"),
                "output_artifact_ids": run.get("output_artifact_ids"),
            },
        ))
        if spec_id in nodes:
            link(spec_id, run["id"], "executed_as", "immutable execution")
        link(cohort.get("id", "COHORT-001"), run["id"], "input_to", "cohort selection")
        link(run.get("snapshot_id", snapshot_id), run["id"], "read_by", "snapshot-bound execution")

    for item in evidence:
        run_id = item.get("analysis_run_id", "")
        add(_node(
            item.get("id", "EVID-0001"),
            "evidence",
            item.get("title", "Evidence artifact"),
            f"{item.get('kind', '')} · {item.get('quality', '')}",
            detail={
                "kind": item.get("kind"),
                "metric_id": item.get("metric_id"),
                "analysis_run_id": run_id,
                "value": item.get("value"),
                "unit": item.get("unit"),
                "estimate": item.get("estimate"),
                "uncertainty": item.get("uncertainty"),
                "uncertainty_label": item.get("uncertainty_label"),
                "effect_size": item.get("effect_size"),
                "population": item.get("population"),
                "sample_size": item.get("sample_size"),
                "protocol_id": item.get("protocol_id"),
                "dataset_snapshot_id": item.get("dataset_snapshot_id"),
                "quality": item.get("quality"),
                "provenance": item.get("provenance"),
                "interpretation": item.get("interpretation"),
            },
        ))
        if run_id in nodes:
            link(run_id, item["id"], "produces", "computed result")
        if item.get("metric_id") in nodes:
            link(item["metric_id"], item["id"], "measured_by", "metric contract")
        if item.get("protocol_id") in nodes:
            link(item["protocol_id"], item["id"], "constrained_by", "measurement protocol")
        link(item.get("dataset_snapshot_id", snapshot_id), item["id"], "supports", "input snapshot")

    for figure in figures:
        add(_node(
            figure.get("id", "FIG-0001"),
            "figure",
            figure.get("title", "Figure artifact"),
            f"{figure.get('kind', '')} · computed",
            detail=figure,
        ))
        for evidence_id in figure.get("evidence_ids", []):
            if evidence_id in nodes:
                link(evidence_id, figure["id"], "visualised_as", "computed figure")
        link(figure.get("analysis_run_id", "RUN-0001"), figure["id"], "renders", "run output")

    add(_node(
        report.get("id", "REPORT-001"),
        "report",
        report.get("title", "Interim report"),
        report.get("status", "DRAFT"),
        detail=report,
    ))
    for evidence_id in report.get("evidence_ids", []):
        if evidence_id in nodes:
            link(evidence_id, report["id"], "cited_by", "report citation")
    for figure_id in report.get("figure_ids", []):
        if figure_id in nodes:
            link(figure_id, report["id"], "embedded_in", "report figure")
    link(study_id, report["id"], "reported_in", "study report")

    add(_node(
        model_spec.get("id", "MODEL-FITNESS-FATIGUE"),
        "model",
        model_spec.get("name", "Training response model"),
        f"{model_spec.get('kind', '')} · {model_spec.get('status', '')}",
        detail=model_spec,
    ))
    link(snapshot_id, model_spec.get("id", "MODEL-FITNESS-FATIGUE"), "trains_on", "snapshot input")
    add(_node(
        model_run.get("id", "MODEL-RUN-0001"),
        "model_run",
        model_run.get("id", "MODEL-RUN-0001"),
        model_run.get("diagnostics", {}).get("fit_status", "PROTOTYPE_FIT"),
        detail={
            "model_spec_id": model_run.get("model_spec_id"),
            "parameters": model_run.get("parameters"),
            "diagnostics": model_run.get("diagnostics"),
            "created_at": model_run.get("created_at"),
        },
    ))
    link(model_spec.get("id", "MODEL-FITNESS-FATIGUE"), model_run.get("id", "MODEL-RUN-0001"), "fitted_as", "local fit")

    add(_node(
        "TRIAL-INDEX",
        "trial",
        "Trial registry",
        f"{snapshot.get('row_counts', {}).get('cmj_trials', 0)} CMJ trials",
        detail={"source": "cmj_trials.parquet", "trace_source": "force_traces.parquet", "sample_rate_hz": 1000},
    ))
    link(snapshot_id, "TRIAL-INDEX", "contains", "trial summaries")
    link("GEN-001", "TRIAL-INDEX", "simulates", "synthetic measurements")

    add(_node(
        study_id,
        "study",
        study.get("study", {}).get("title", study_id),
        study.get("study", {}).get("state", "ACTIVE"),
        detail=study.get("study", {}),
    ))
    link("GEN-001", study_id, "supports", "study design")
    link(study_id, cohort.get("id", "COHORT-001"), "defines", "study cohort")

    plan = study.get("plan", {})
    if plan:
        add(_node(
            plan.get("id", "PLAN-001"),
            "plan",
            "Frozen analysis plan",
            plan.get("status", "FROZEN"),
            detail=plan,
        ))
        link(study_id, plan.get("id", "PLAN-001"), "governed_by", "pre-specified plan")
        for spec_id in specs:
            link(plan.get("id", "PLAN-001"), spec_id, "authorises", "planned analysis")

    question = study.get("question", {})
    if question:
        add(_node(
            question.get("id", "RQ-001"),
            "question",
            "Research question",
            question.get("estimand", ""),
            detail=question,
        ))
        link(question.get("id", "RQ-001"), study_id, "investigated_by", "study objective")
        for hypothesis in study.get("hypotheses", []):
            add(_node(
                hypothesis["id"],
                "hypothesis",
                hypothesis.get("statement", hypothesis["id"]),
                f"{hypothesis.get('status', '')} · {hypothesis.get('direction', '')}",
                detail=hypothesis,
            ))
            link(question.get("id", "RQ-001"), hypothesis["id"], "tested_as", "registered hypothesis")

    # Materialise the focused measurement so a trial or match can be inspected
    # directly instead of only through the aggregate trial index.
    focused_trial = next((row for row in (trial_rows or []) if str(row.get("trial_id")) == artifact_id), None)
    if focused_trial is not None:
        add(_node(
            artifact_id,
            "trial",
            artifact_id,
            f"{focused_trial.get('quality_state', '')} · week {focused_trial.get('week')}",
            detail={
                "subject_id": focused_trial.get("subject_id"),
                "display_id": focused_trial.get("display_id"),
                "session_id": focused_trial.get("session_id"),
                "week": focused_trial.get("week"),
                "trial_number": focused_trial.get("trial_number"),
                "quality_state": focused_trial.get("quality_state"),
                "exclusion_reason": focused_trial.get("exclusion_reason"),
                "body_mass_kg": focused_trial.get("body_mass_kg"),
                "intervention_arm": focused_trial.get("intervention_arm"),
                "phase_boundaries": focused_trial.get("phase_boundaries"),
                "trace_path": focused_trial.get("trace_path"),
                "metrics": {
                    key: focused_trial.get(key)
                    for key in (
                        "jump_height_cm",
                        "concentric_impulse_n_s_kg",
                        "eccentric_braking_impulse_n_s_kg",
                        "eccentric_braking_duration_s",
                        "countermovement_depth_cm",
                        "peak_force_n",
                        "peak_power_w_kg",
                        "rsi_mod",
                    )
                },
            },
        ))
        link("GEN-001", artifact_id, "simulated", "synthetic force trace")
        link(artifact_id, "TRIAL-INDEX", "indexed_in", "trial registry")
        link(artifact_id, snapshot_id, "stored_in", "immutable snapshot")
        for metric_id in metric_defs:
            link(metric_id, artifact_id, "extracted_from", "phase-aware extraction")

    if artifact_id == "MATCH-SYNTH-001":
        add(_node(
            artifact_id,
            "match",
            "Synthetic match segment",
            f"{snapshot.get('row_counts', {}).get('match_tracking', 0)} tracking rows · 10 Hz",
            detail={
                "tracking_source": "match_tracking.parquet",
                "pose_source": "match_pose.parquet",
                "events_source": "match_events.parquet",
                "pose_athletes": snapshot.get("pose_athletes"),
                "frame_count": snapshot.get("row_counts", {}).get("match_tracking"),
                "sample_rate_hz": snapshot.get("sample_rates", {}).get("match_tracking_hz"),
            },
        ))
        link("GEN-001", artifact_id, "simulated", "bounded match segment")
        link(artifact_id, snapshot_id, "stored_in", "immutable snapshot")
        link(artifact_id, "PROT-MATCH", "constrained_by", "match protocol")

    if artifact_id not in nodes:
        nodes[artifact_id] = _node(artifact_id, "unknown", artifact_id, "not found in local artefact store")

    focus = nodes[artifact_id]
    return {
        "artifact_id": artifact_id,
        "focus": focus,
        "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
        "edges": sorted(edges.values(), key=lambda item: item["id"]),
    }
