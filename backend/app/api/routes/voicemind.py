import re

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError
from app.database.session import get_db
from app.schemas.voicemind import ChatRequest, SpeechRequest
from app.services.experiments import finish_experiment, start_experiment
from app.services.groq_service import GroqService
from app.services.speech_service import browser_speech, validate_audio

router = APIRouter(prefix="/voicemind", tags=["VoiceMind"])


def get_groq() -> GroqService:
    return GroqService()


@router.get("/models")
async def models(provider: GroqService = Depends(get_groq)):
    return {"models": await provider.list_models(), "default_model": get_settings().groq_model}


@router.post("/chat")
async def chat(request: ChatRequest, db: Session = Depends(get_db), provider: GroqService = Depends(get_groq)):
    experiment = start_experiment(db, "voicemind", "VoiceMind conversation", {"message_count": len(request.messages)})
    try:
        text = await provider.chat([m.model_dump() for m in request.messages], request.model, request.temperature)
        finish_experiment(db, experiment, {"response_characters": len(text), "model": request.model or get_settings().groq_model})
        return {"experiment_id": experiment.id, "text": text, "model": request.model or get_settings().groq_model}
    except APIError as exc:
        finish_experiment(db, experiment, error=exc.message)
        raise
    except Exception:
        finish_experiment(db, experiment, error="Conversation failed unexpectedly.")
        raise


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), language: str | None = Form(default=None),
                     db: Session = Depends(get_db), provider: GroqService = Depends(get_groq)):
    try:
        if language is not None and not re.fullmatch(r"[a-z]{2}", language):
            raise APIError(422, "invalid_language", "Use a two-letter ISO language code.")
        limit = get_settings().max_upload_bytes
        content = await file.read(limit + 1)
        filename, mime = validate_audio(content, file.filename, file.content_type, limit)
    finally:
        await file.close()
    experiment = start_experiment(db, "voicemind", "Transcribe audio", {"size_bytes": len(content), "format": mime})
    try:
        result = await provider.transcribe(content, filename, mime, language)
        finish_experiment(db, experiment, {"transcript_characters": len(result["text"]), "model": result["model"]})
        return {"experiment_id": experiment.id, **result}
    except APIError as exc:
        finish_experiment(db, experiment, error=exc.message)
        raise
    except Exception:
        finish_experiment(db, experiment, error="Transcription failed unexpectedly.")
        raise


@router.post("/speech")
def speech(request: SpeechRequest, db: Session = Depends(get_db)):
    experiment = start_experiment(db, "voicemind", "Browser speech descriptor", {"text_characters": len(request.text)})
    result = browser_speech(request)
    finish_experiment(db, experiment, {"engine": result["engine"], "audio_generated": False})
    return {"experiment_id": experiment.id, **result}
