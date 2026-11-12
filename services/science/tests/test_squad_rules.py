"""RES-647 researcher-configured flags and assumption-driven simulations."""

from __future__ import annotations

import pytest

from dynamis_science import importer, researchstore, squad
from test_importer import FIXTURE
from test_longitudinal_research import admit, service, study_file, value  # noqa: F401  (service is a fixture)


@pytest.fixture
def workspace(service, tmp_path):
    context = importer.build_context(FIXTURE)
    identity = service.create_workspace("Flags")["study"]["id"]
    service.attach_workspace_data(identity, admit(study_file(tmp_path, range(1, 7), "season.csv"), context))
    return identity


def mean(index, week):
    trials = [value(index, week, trial) for trial in range(1, 3 + index % 2)]
    return sum(trials) / len(trials)


DANGER = {"name": "Jump height dropping", "category": "In danger", "tone": "negative",
          "conditions": [{"metric_id": "MET-CMJ-HEIGHT", "measure": "change_from_previous_pct", "operator": "<", "value": -1}]}
GREAT = {"name": "Jump height rising", "category": "Doing great", "tone": "positive",
         "conditions": [{"metric_id": "MET-CMJ-HEIGHT", "measure": "change_from_baseline_pct", "operator": ">", "value": 4}]}


def test_user_rules_flag_athletes_with_evidence(workspace):
    with pytest.raises(researchstore.ResearchValidation, match="category"):
        squad.save_rules(workspace, [{**DANGER, "category": ""}])
    with pytest.raises(researchstore.ResearchValidation, match="not measured"):
        squad.save_rules(workspace, [{**DANGER, "conditions": [{**DANGER["conditions"][0], "metric_id": "MET-SLEEP"}]}])
    squad.save_rules(workspace, [DANGER, GREAT])
    board = squad.squad_board(workspace)
    athletes = {a["subject_id"]: a for group in board["groups"] for a in group["athletes"]}
    assert len(athletes) == 12
    # Independent recomputation of the "previous test" rule for every athlete.
    for index in range(1, 13):
        subject = f"P{index:02d}"
        weeks = [w for w in range(1, 7) if (subject, w) not in __import__("test_longitudinal_research").MISSING]
        values = [mean(index, w) for w in weeks]
        drop = len(values) > 1 and (values[-1] - values[-2]) / values[-2] * 100 < -1
        rise = len(values) > 1 and (values[-1] - values[0]) / values[0] * 100 > 4
        categories = {flag["category"] for flag in athletes[subject]["flags"]}
        assert ("In danger" in categories) == drop and ("Doing great" in categories) == rise, subject
    flagged = next(a for a in athletes.values() if a["flags"])
    evidence = flagged["flags"][0]["evidence"][0]
    assert evidence["met"] and evidence["metric"] == "Jump height (flight time)" and evidence["unit"] == "cm"
    assert {group["name"] for group in squad.squad_board(workspace, "trend")["groups"]} <= {"up", "down", "flat", "insufficient data"}
    missed = squad.evaluate(researchstore.get_entity(workspace)["dataset_snapshot_id"], [squad.validate_rule(
        {"name": "Missing data", "category": "Follow up", "conditions": [{"metric_id": "MET-CMJ-HEIGHT", "measure": "missed_tests", "operator": ">=", "value": 2}]},
        squad._metrics(researchstore.get_entity(workspace)["dataset_snapshot_id"]))])
    assert {s for s, hits in missed.items() if hits} == {"P03", "P11"}


def test_scenarios_preserve_definitions_without_forecasts_or_flag_crossings(workspace):
    squad.save_rules(workspace, [DANGER])
    before = researchstore.get_entity(workspace)
    board = squad.squad_board(workspace)
    scenario = {"name": "Detraining assumptions", "steps": 4, "outcome_metric_id": "MET-CMJ-HEIGHT",
                "outcome_trend_pct_per_step": {"best": 1, "expected": 0, "worst": -3}}
    result = squad.save_simulation(workspace, scenario)
    assert result["designation"] == "HYPOTHETICAL"
    assert result["qualification"]["status"] == "NOT_QUALIFIED" and result["numerical_result"] is None
    assert result["athletes"] == [] and result["flags_at_horizon"] == {}
    after = researchstore.get_entity(workspace)
    assert after["simulations"][0]["definition"] == scenario
    assert after["simulations"][0]["summary"] == {}
    assert after["dataset_snapshot_id"] == before["dataset_snapshot_id"]
    assert after["active_data_revision_id"] == before["active_data_revision_id"]
    assert squad.squad_board(workspace)["groups"] == board["groups"]
    assert not researchstore.list_runs(workspace) and not researchstore.list_evidence(workspace)
    assert all("would meet" not in e["detail"] for e in squad.events(workspace)["events"])
    with pytest.raises(researchstore.ResearchValidation, match="not measured"):
        squad.simulate(workspace, {**scenario, "drivers": [{"metric_id": "MET-LOAD", "change_pct_per_step": 10}]})
