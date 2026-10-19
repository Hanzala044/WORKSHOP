import importlib.metadata
import tempfile

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError
from app.database.session import get_db
from app.services.groq_service import GroqService

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request, check_provider: bool = False, db: Session = Depends(get_db)):
    config = get_settings()
    checks = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception:
        db.rollback()
        checks["database"] = {"status": "error", "message": "Database is unavailable."}
    try:
        with tempfile.TemporaryFile(dir=config.data_dir) as probe:
            probe.write(b"health")
            probe.flush()
        checks["storage"] = {"status": "ok"}
    except OSError:
        checks["storage"] = {"status": "error", "message": "Data storage is not writable."}
    checks["groq"] = {"status": "configured_not_checked" if config.groq_api_key else "not_configured"}
    if check_provider and config.groq_api_key:
        try:
            available = await GroqService().list_models()
            ids = {m["id"] for m in available if m["active"]}
            checks["groq"] = {"status": "ok" if config.groq_model in ids and config.groq_transcription_model in ids else "error",
                              "chat_model_available": config.groq_model in ids,
                              "transcription_model_available": config.groq_transcription_model in ids}
        except APIError as exc:
            checks["groq"] = {"status": "error", "code": exc.code, "message": exc.message}
    dependencies = {}
    for package in ("fastapi", "sqlalchemy", "httpx", "python-multipart", "beautifulsoup4"):
        try:
            dependencies[package] = {"status": "installed", "version": importlib.metadata.version(package)}
        except importlib.metadata.PackageNotFoundError:
            dependencies[package] = {"status": "missing"}
    degraded = any(check["status"] == "error" for check in checks.values()) or any(d["status"] == "missing" for d in dependencies.values())
    return JSONResponse(status_code=503 if degraded else 200, content={
        "status": "degraded" if degraded else "ok", "checks": checks, "dependencies": dependencies,
        "scraping": {"enabled": bool(config.allowed_hosts), "requires_permission": True, "requires_robots_policy": True},
        "feature_routers": {name: "not_installed" if name in request.app.state.unavailable_modules else "installed"
                            for name in ("documents", "rag", "handvision")},
    })
