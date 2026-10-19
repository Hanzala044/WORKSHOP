import httpx
import pytest

from app.core.config import Settings
from app.core.errors import APIError
from app.services.groq_service import GroqService


@pytest.fixture
def provider():
    return GroqService(Settings(_env_file=None, groq_api_key="private-test-key"))


def mock_http(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


@pytest.mark.asyncio
async def test_chat_verifies_real_model_endpoint(provider, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        assert request.url.host == "api.groq.com"
        assert request.headers["authorization"] == "Bearer private-test-key"
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": provider.settings.groq_model, "active": True}]})
        assert b'"messages"' in request.content
        return httpx.Response(200, json={"choices": [{"message": {"content": "A real mocked completion"}}]})
    mock_http(monkeypatch, handler)
    assert await provider.chat([{"role": "user", "content": "Hi"}]) == "A real mocked completion"
    assert calls == ["/openai/v1/models", "/openai/v1/chat/completions"]


@pytest.mark.asyncio
async def test_missing_or_inactive_model_not_sent(provider, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"data": [{"id": "disabled", "active": False}]})
    mock_http(monkeypatch, handler)
    with pytest.raises(APIError) as exc:
        await provider.chat([{"role": "user", "content": "Hi"}], model="disabled")
    assert exc.value.code == "model_unavailable"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_real_multipart_transcription(provider, monkeypatch):
    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": provider.settings.groq_transcription_model}]})
        assert request.url.path.endswith("/audio/transcriptions")
        assert request.headers["content-type"].startswith("multipart/form-data;")
        assert b'filename="recording.wav"' in request.content
        assert b"RIFF0000WAVE" in request.content
        assert b"verbose_json" in request.content
        return httpx.Response(200, json={"text": "transcribed", "language": "english", "duration": 1.0})
    mock_http(monkeypatch, handler)
    result = await provider.transcribe(b"RIFF0000WAVE", "recording.wav", "audio/wav", "en")
    assert result["text"] == "transcribed"


@pytest.mark.parametrize("status,code", [(401, "provider_authentication"), (403, "provider_authentication"), (429, "provider_rate_limit"), (500, "provider_error"), (302, "provider_error")])
@pytest.mark.asyncio
async def test_provider_errors_never_expose_body(provider, monkeypatch, status, code):
    mock_http(monkeypatch, lambda request: httpx.Response(status, text="PRIVATE key and provider details"))
    with pytest.raises(APIError) as exc:
        await provider.list_models()
    assert exc.value.code == code
    assert "PRIVATE" not in exc.value.message
    assert "private-test-key" not in exc.value.message


@pytest.mark.asyncio
async def test_timeout_and_bad_json(provider, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("PRIVATE traceback", request=request)
    mock_http(monkeypatch, handler)
    with pytest.raises(APIError) as exc:
        await provider.list_models()
    assert exc.value.code == "provider_timeout"


@pytest.mark.asyncio
async def test_missing_key_does_not_network(monkeypatch):
    provider = GroqService(Settings(_env_file=None, groq_api_key=None))
    mock_http(monkeypatch, lambda request: pytest.fail("Provider called without key"))
    with pytest.raises(APIError) as exc:
        await provider.list_models()
    assert exc.value.code == "provider_not_configured"


@pytest.mark.asyncio
async def test_invalid_json_response(provider, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=b"not-json"))
    with pytest.raises(APIError):
        await provider.list_models()


@pytest.mark.asyncio
async def test_oversized_response_is_bounded(provider, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1)))
    with pytest.raises(APIError) as exc:
        await provider.list_models()
    assert exc.value.code == "provider_response"
