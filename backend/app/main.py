import importlib
import importlib.util
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware

from app.api.routes import health, history, pricepilot, settings, voicemind
from app.core.config import get_settings
from app.core.errors import APIError
from app.core.middleware import RequestSafetyMiddleware
from app.database.session import init_db
from app.schemas.common import Preferences

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    config = get_settings()
    application = FastAPI(title="Workshop API", version="1.0.0", lifespan=lifespan, middleware=[
        Middleware(RequestSafetyMiddleware, settings=config),
        Middleware(CORSMiddleware, allow_origins=config.cors_origins, allow_credentials=False,
                   allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                   allow_headers=["Content-Type"], expose_headers=["X-Request-ID", "X-Export-Truncated"]),

    ])
    application.state.preferences = Preferences()

    def error_response(request: Request, status: int, code: str, message: str):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}, "request_id": request_id},
                            headers={"X-Request-ID": request_id, "Cache-Control": "no-store",
                                                                 "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})

    @application.exception_handler(APIError)
    async def api_error(request: Request, exc: APIError):
        return error_response(request, exc.status_code, exc.code, exc.message)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(request, 422, "validation_error", "Request validation failed. Check field types, values and size limits.")

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        message = {404: "Endpoint was not found.", 405: "Method is not allowed.", 413: "Request is too large."}.get(exc.status_code, "Request could not be processed.")
        return error_response(request, exc.status_code, "http_error", message)

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        # Log a correlation ID and type, not potentially sensitive exception/provider bodies.
        logger.error("Request %s failed (%s)", getattr(request.state, "request_id", "unknown"), type(exc).__name__)
        return error_response(request, 500, "internal_error", "An unexpected backend error occurred.")

    for router in (health.router, history.router, settings.router, pricepilot.router, voicemind.router):
        application.include_router(router, prefix="/api/v1")
    missing = []
    for name in ("documents", "rag", "handvision"):
        module_name = f"app.api.routes.{name}"
        if importlib.util.find_spec(module_name) is None:
            missing.append(name)
            continue
        module = importlib.import_module(module_name)
        application.include_router(module.router, prefix="/api/v1")
    application.state.unavailable_modules = missing
    if missing:
        logger.warning("Optional feature routers not installed: %s", ", ".join(missing))
    return application


app = create_app()
