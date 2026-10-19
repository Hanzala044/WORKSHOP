from datetime import timezone

from sqlalchemy.orm import Session

from app.database.models import Experiment, utcnow


def start_experiment(db: Session, module: str, title: str, input_summary: dict | None = None) -> Experiment:
    experiment = Experiment(module=module, title=title[:200], input_summary=input_summary or {})
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return experiment


def finish_experiment(db: Session, experiment: Experiment, output_metadata: dict | None = None, error: str | None = None) -> Experiment:
    experiment.completed_at = utcnow()
    started = experiment.started_at
    if started.tzinfo is None:  # SQLite stores UTC datetimes without their offset.
        started = started.replace(tzinfo=timezone.utc)
    experiment.duration_ms = max(0, int((experiment.completed_at - started).total_seconds() * 1000))
    experiment.status = "failed" if error else "completed"
    experiment.error = error[:1000] if error else None
    experiment.output_metadata = output_metadata or {}
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return experiment
