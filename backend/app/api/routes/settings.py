from threading import Lock

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.core.errors import APIError
from app.schemas.common import Preferences, PreferencesPatch

router = APIRouter(prefix="/settings", tags=["settings"])
_lock = Lock()


def snapshot(request: Request):
    config = get_settings()
    return {"preferences": request.app.state.preferences.model_dump(), "persistence": "process_local",
            "capabilities": {"groq_configured": bool(config.groq_api_key),
                             "scraping_enabled": bool(config.allowed_hosts),
                             "speech_engine": "browser_web_speech"},
            "limits": {"max_upload_bytes": config.max_upload_bytes,
                       "max_document_pages": config.max_document_pages,
                       "max_document_chunks": config.max_document_chunks}}


@router.get("")
def get_preferences(request: Request):
    with _lock:
        return snapshot(request)


@router.patch("")
def patch_preferences(patch: PreferencesPatch, request: Request):
    updates = patch.model_dump(exclude_unset=True)
    if any(value is None for value in updates.values()):
        raise APIError(422, "invalid_preferences", "Preferences cannot be null.")
    with _lock:
        request.app.state.preferences = Preferences.model_validate({**request.app.state.preferences.model_dump(), **updates})
        return snapshot(request)
