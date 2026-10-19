from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.database.session import get_db
from app.schemas.pricepilot import CompareRequest
from app.services.experiments import finish_experiment, start_experiment
from app.services.price_comparison_service import PriceComparisonService

router = APIRouter(prefix="/pricepilot", tags=["PricePilot"])


@router.post("/compare")
def compare(request: CompareRequest, db: Session = Depends(get_db)):
    experiment = start_experiment(db, "pricepilot", "Compare product prices", {"item_count": len(request.items)})
    try:
        result = PriceComparisonService().compare(request)
    except APIError as exc:
        finish_experiment(db, experiment, error=exc.message)
        raise
    except Exception:
        finish_experiment(db, experiment, error="Price comparison failed unexpectedly.")
        raise
    succeeded = sum(row["status"] == "completed" for row in result["results"])
    finish_experiment(db, experiment, {"item_count": len(request.items), "success_count": succeeded,
                                     "currencies": [group["currency"] for group in result["currency_groups"]]},
                      error="No product prices could be retrieved." if not succeeded else None)
    return {"experiment_id": experiment.id, **result}
