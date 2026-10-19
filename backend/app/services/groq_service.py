import json

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import APIError

BASE_URL = "https://api.groq.com/openai/v1"


class GroqService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        key = self.settings.groq_api_key
        if not key or not key.get_secret_value().strip():
            raise APIError(503, "provider_not_configured", "Configure a Groq API key on the backend to use this feature.")
        try:
            async with httpx.AsyncClient(timeout=self.settings.network_timeout, trust_env=False, follow_redirects=False) as client:
                # Stream and bound even error responses; never return provider bodies.
                async with client.stream(method, BASE_URL + path, headers={"Authorization": f"Bearer {key.get_secret_value()}"}, **kwargs) as response:
                    if response.status_code >= 300:
                        if response.status_code in (401, 403):
                            raise APIError(503, "provider_authentication", "Groq rejected the backend credentials or permissions.")
                        if response.status_code == 429:
                            raise APIError(429, "provider_rate_limit", "Groq rate limit reached; try again later.")
                        raise APIError(502, "provider_error", "Groq could not complete this request.")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 2 * 1024 * 1024:
                            raise APIError(502, "provider_response", "Groq returned an oversized response.")
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        raise ValueError
                    return data
        except APIError:
            raise
        except httpx.TimeoutException:
            raise APIError(504, "provider_timeout", "Groq request timed out.") from None
        except (httpx.HTTPError, ValueError, TypeError):
            raise APIError(502, "provider_unavailable", "Groq returned an invalid response or could not be reached.") from None

    async def list_models(self) -> list[dict]:
        data = await self._request("GET", "/models")
        models = data.get("data")
        if not isinstance(models, list):
            raise APIError(502, "provider_response", "Groq returned an invalid model listing.")
        return [{"id": m["id"], "owned_by": m.get("owned_by"), "active": m.get("active", True)}
                for m in models if isinstance(m, dict) and isinstance(m.get("id"), str)]

    async def _verify_model(self, model: str):
        if not any(m["id"] == model and m["active"] for m in await self.list_models()):
            raise APIError(422, "model_unavailable", "The requested model is not available in the Groq model listing.")

    async def chat(self, messages: list[dict], model: str | None = None, temperature: float = 0.3) -> str:
        model = model or self.settings.groq_model
        await self._verify_model(model)
        data = await self._request("POST", "/chat/completions", json={
            "model": model, "messages": messages, "temperature": temperature, "max_tokens": 2048,
        })
        try:
            text = data["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError
            return text
        except (KeyError, IndexError, TypeError, ValueError):
            raise APIError(502, "provider_response", "Groq returned no usable completion.") from None

    async def transcribe(self, content: bytes, filename: str, content_type: str, language: str | None = None) -> dict:
        model = self.settings.groq_transcription_model
        await self._verify_model(model)
        fields = {"model": model, "response_format": "verbose_json"}
        if language:
            fields["language"] = language
        result = await self._request("POST", "/audio/transcriptions", data=fields,
                                     files={"file": (filename, content, content_type)})
        if not isinstance(result.get("text"), str):
            raise APIError(502, "provider_response", "Groq returned no usable transcription.")
        return {"text": result["text"], "language": result.get("language"), "duration": result.get("duration"), "model": model}
