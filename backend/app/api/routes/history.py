import csv
import io
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.database.models import Experiment, utcnow
from app.database.session import get_db
from app.schemas.common import ExperimentOut

router = APIRouter(prefix="/history", tags=["history"])
Status = Literal["running", "completed", "failed"]


def filtered(module: str | None, status: str | None):
    query = select(Experiment)
    if module:
        query = query.where(Experiment.module == module)
    if status:
        query = query.where(Experiment.status == status)
    return query


def encoded(row: Experiment) -> dict:
    return ExperimentOut.model_validate(row).model_dump(mode="json")


@router.get("")
def history(page: int = Query(1, ge=1, le=1000000), page_size: int = Query(20, ge=1, le=100),
            module: str | None = Query(None, max_length=40), status: Status | None = None,
            db: Session = Depends(get_db)):
    query = filtered(module, status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Experiment.started_at.desc(), Experiment.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [encoded(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(Experiment.status, func.count()).group_by(Experiment.status)).all())
    by_module = dict(db.execute(select(Experiment.module, func.count()).group_by(Experiment.module)).all())
    average = db.scalar(select(func.avg(Experiment.duration_ms)).where(Experiment.status == "completed"))
    recent = db.scalar(select(func.count()).select_from(Experiment).where(Experiment.started_at >= utcnow() - timedelta(days=7)))
    return {"total": sum(by_status.values()), "by_status": {s: by_status.get(s, 0) for s in ("running", "completed", "failed")},
            "by_module": by_module, "average_duration_ms": round(average, 2) if average is not None else None,
            "last_7_days": recent}


@router.get("/export")
def export(format: Literal["json", "csv"] = "json", module: str | None = Query(None, max_length=40),
           status: Status | None = None, db: Session = Depends(get_db)):
    rows = db.scalars(filtered(module, status).order_by(Experiment.started_at.desc(), Experiment.id.desc()).limit(5001)).all()
    truncated = len(rows) > 5000
    items = [encoded(row) for row in rows[:5000]]
    if format == "json":
        return {"items": items, "truncated": truncated, "limit": 5000}
    buffer = io.StringIO(newline="")
    fields = ["id", "module", "title", "status", "started_at", "completed_at", "duration_ms", "error"]
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in items:
        # Spreadsheet formula injection also applies to user-controlled titles/errors.
        writer.writerow({key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value for key, value in row.items()})
    return Response(buffer.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="workshop-history.csv"',
        "X-Export-Truncated": str(truncated).lower(),
    })


def get_experiment(db: Session, experiment_id: UUID) -> Experiment:
    experiment = db.get(Experiment, str(experiment_id))
    if experiment is None:
        raise APIError(404, "experiment_not_found", "Experiment was not found.")
    return experiment


@router.get("/{experiment_id}")
def detail(experiment_id: UUID, db: Session = Depends(get_db)):
    return encoded(get_experiment(db, experiment_id))


@router.delete("/{experiment_id}", status_code=204)
def delete(experiment_id: UUID, db: Session = Depends(get_db)):
    experiment = get_experiment(db, experiment_id)
    if experiment.status == "running":
        raise APIError(409, "experiment_running", "A running experiment cannot be deleted.")
    db.delete(experiment)
    db.commit()
    return Response(status_code=204)
