from pathlib import PurePosixPath

from app.core.errors import APIError
from app.schemas.voicemind import SpeechRequest

AUDIO_TYPES = {
    ".wav": {"audio/wav", "audio/x-wav", "audio/wave"},
    ".mp3": {"audio/mpeg", "audio/mp3"},
    ".flac": {"audio/flac", "audio/x-flac"},
    ".ogg": {"audio/ogg", "application/ogg"},
    ".webm": {"audio/webm", "video/webm"},
    ".m4a": {"audio/mp4", "audio/m4a", "audio/x-m4a"},
    ".mp4": {"audio/mp4", "video/mp4"},
}


def validate_audio(content: bytes, filename: str | None, content_type: str | None, limit: int) -> tuple[str, str]:
    if not content:
        raise APIError(422, "empty_audio", "Upload a nonempty audio file.")
    if len(content) > limit:
        raise APIError(413, "upload_too_large", "Audio exceeds the configured upload limit.")
    # Never send user-controlled path components to the provider.
    suffix = PurePosixPath((filename or "").replace("\\", "/")).suffix.lower()
    mime = (content_type or "").split(";", 1)[0].lower().strip()
    if suffix not in AUDIO_TYPES or mime not in AUDIO_TYPES[suffix]:
        raise APIError(415, "audio_format", "Use WAV, MP3, FLAC, OGG, WebM, M4A or MP4 with a matching audio content type.")
    valid = {
        ".wav": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE",
        ".mp3": content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 255 and content[1] & 224 == 224),
        ".flac": content.startswith(b"fLaC"),
        ".ogg": content.startswith(b"OggS"),
        ".webm": content.startswith(b"\x1aE\xdf\xa3"),
        ".m4a": len(content) >= 12 and content[4:8] == b"ftyp",
        ".mp4": len(content) >= 12 and content[4:8] == b"ftyp",
    }[suffix]
    if not valid:
        raise APIError(415, "audio_signature", "Audio header does not match its declared format.")
    return "recording" + suffix, mime


def browser_speech(request: SpeechRequest) -> dict:
    return {
        "engine": "browser_web_speech", "audio_generated": False,
        "requires_browser_support": True, "requires_user_gesture": True,
        "privacy_notice": "Your browser or OS may use a remote speech service; check its privacy settings.",
        **request.model_dump(),
    }
