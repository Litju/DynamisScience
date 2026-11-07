"""Temporary FastAPI adapter for the Performance OS Python domain functions.

The native application imports :mod:`performance` directly. This adapter is
kept only while the legacy web runtime is being retired in RES-604 G4.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from . import performance, researchstore

router = APIRouter(prefix="/performance", tags=["performance"])


def _call(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except researchstore.ResearchNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except researchstore.ResearchConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except researchstore.ResearchValidation as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except performance.PerformanceInputError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/context")
def context() -> dict[str, Any]:
    return _call(performance.context)


@router.get("/today")
def today() -> dict[str, Any]:
    return _call(performance.today)


@router.get("/athletes")
def athletes() -> list[dict[str, Any]]:
    return _call(performance.athletes)


@router.get("/squad-weeks")
def squad_weeks() -> dict[str, Any]:
    return _call(performance.squad_weeks)


@router.get("/athletes/{athlete_id}")
def athlete_detail(athlete_id: str) -> dict[str, Any]:
    return _call(lambda: performance.athlete_detail(athlete_id))


@router.get("/load")
def load_overview() -> dict[str, Any]:
    return _call(performance.load_overview)


@router.post("/sessions")
def log_session(payload: performance.SessionLog) -> dict[str, Any]:
    return _call(lambda: performance.log_session(payload))


@router.post("/athletes/{athlete_id}/notes")
def add_athlete_note(
    athlete_id: str, payload: performance.AthleteNote
) -> dict[str, Any]:
    return _call(lambda: performance.add_athlete_note(athlete_id, payload))


@router.get("/plan")
def get_plan() -> dict[str, Any]:
    return _call(performance.get_plan)


@router.put("/plan")
def update_plan(payload: performance.PlanUpdate) -> dict[str, Any]:
    return _call(lambda: performance.update_plan(payload))


@router.post("/plan/publish")
def publish_plan() -> dict[str, Any]:
    return _call(performance.publish_plan)


@router.get("/tests")
def tests() -> dict[str, Any]:
    return _call(performance.tests)


@router.post("/tests/reliability")
def run_reliability() -> dict[str, Any]:
    return _call(performance.run_reliability)


@router.get("/movement")
def movement() -> dict[str, Any]:
    return _call(performance.movement)


@router.get("/units")
def units() -> dict[str, Any]:
    return _call(performance.units)


@router.get("/research")
def research_link() -> dict[str, Any]:
    return _call(performance.research_link)


@router.get("/reports")
def list_reports(audience: str | None = Query(default=None)) -> list[dict[str, Any]]:
    return _call(lambda: performance.list_reports(audience))


@router.post("/reports")
def create_report(payload: performance.ReportRequest) -> dict[str, Any]:
    return _call(lambda: performance.create_report(payload))


@router.post("/reports/{report_id}/freeze")
def freeze_report(report_id: str) -> dict[str, Any]:
    return _call(lambda: performance.freeze_report(report_id))


@router.get("/reports/{report_id}")
def get_report(report_id: str) -> dict[str, Any]:
    return _call(lambda: performance.get_report(report_id))


@router.get("/reports/{report_id}/export", response_class=HTMLResponse)
def export_report(report_id: str) -> HTMLResponse:
    return HTMLResponse(_call(lambda: performance.export_report(report_id)))
