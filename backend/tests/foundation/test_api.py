from sqlalchemy import select

from app.core.errors import APIError
from app.database.models import Experiment
from app.services.experiments import finish_experiment, start_experiment


def test_health_has_real_diagnostics(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["checks"]["database"]["status"] == "ok"
    assert response.json()["checks"]["storage"]["status"] == "ok"
    assert response.json()["dependencies"]["sqlalchemy"]["status"] == "installed"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_safe_validation_and_settings(client):
    response = client.patch("/api/v1/settings", json={"groq_api_key": "sensitive-test-secret"})
    assert response.status_code == 422
    assert "sensitive-test-secret" not in response.text
    response = client.patch("/api/v1/settings", json={"speech_rate": 1.5, "theme": "dark"})
    assert response.status_code == 200
    assert client.get("/api/v1/settings").json()["preferences"]["theme"] == "dark"
    assert client.patch("/api/v1/settings", json={"theme": None}).status_code == 422
    assert client.patch("/api/v1/settings", json={"speech_rate": 99}).status_code == 422
    assert "groq_api_key" not in client.get("/api/v1/settings").text


def test_host_origin_and_body_protection(client):
    denied = client.get("/api/v1/health", headers={"Host": "evil.example"})
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == "host_denied"
    assert client.get("/api/v1/health", headers={"Host": "[::1]:8000"}).status_code == 200
    assert client.post("/api/v1/voicemind/speech", headers={"Origin": "https://evil.example"}, json={"text": "hello"}).status_code == 403
    assert client.post("/api/v1/voicemind/speech", content=b"a" * 4097).status_code == 413
    assert client.post("/api/v1/voicemind/speech", content=b"a", headers={"Content-Length": "invalid"}).status_code == 400
    response = client.options("/api/v1/settings", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PATCH"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in response.headers


def test_history_stats_exports_and_deletion(client, db):
    first = start_experiment(db, "pricepilot", "=DANGEROUS", {"item_count": 1})
    finish_experiment(db, first, {"success_count": 1})
    failed = start_experiment(db, "voicemind", "Audio")
    finish_experiment(db, failed, error="Safe failure.")
    running = start_experiment(db, "voicemind", "Running")
    assert first.duration_ms >= 0
    response = client.get("/api/v1/history", params={"page_size": 1})
    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert len(response.json()["items"]) == 1
    assert client.get("/api/v1/history", params={"module": "pricepilot"}).json()["total"] == 1
    stats = client.get("/api/v1/history/stats").json()
    assert stats["by_status"] == {"running": 1, "completed": 1, "failed": 1}
    assert stats["last_7_days"] == 3
    detail = client.get(f"/api/v1/history/{first.id}").json()
    assert detail["started_at"].endswith("Z")
    assert detail["output_metadata"] == {"success_count": 1}
    csv = client.get("/api/v1/history/export?format=csv")
    assert csv.status_code == 200
    assert "'=DANGEROUS" in csv.text
    assert "attachment" in csv.headers["content-disposition"]
    assert len(client.get("/api/v1/history/export").json()["items"]) == 3
    assert client.delete(f"/api/v1/history/{running.id}").status_code == 409
    assert client.delete(f"/api/v1/history/{first.id}").status_code == 204
    assert client.get(f"/api/v1/history/{first.id}").status_code == 404
    assert client.get("/api/v1/history/not-a-uuid").status_code == 422


def test_browser_speech_explicitly_not_audio(client, db):
    response = client.post("/api/v1/voicemind/speech", json={"text": "Speak me"})
    assert response.status_code == 200
    result = response.json()
    assert result["engine"] == "browser_web_speech"
    assert result["audio_generated"] is False
    assert result["requires_user_gesture"] is True
    row = db.get(Experiment, result["experiment_id"])
    assert row.status == "completed"
    assert "Speak me" not in str(row.input_summary) + str(row.output_metadata)


def test_chat_and_transcription_with_provider_override(client, db):
    from app.api.routes.voicemind import get_groq

    class Provider:
        async def chat(self, messages, model, temperature):
            assert messages[-1]["content"] == "private prompt"
            return "Provider response"

        async def transcribe(self, content, filename, mime, language):
            assert filename == "recording.wav"
            assert language == "en"
            return {"text": "private transcript", "language": "english", "duration": 1, "model": "whisper-test"}

    client.app.dependency_overrides[get_groq] = Provider
    response = client.post("/api/v1/voicemind/chat", json={"messages": [{"role": "user", "content": "private prompt"}]})
    assert response.status_code == 200
    assert response.json()["text"] == "Provider response"
    audio = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 100
    response = client.post("/api/v1/voicemind/transcribe", files={"file": ("../../evil.wav", audio, "audio/wav")}, data={"language": "en"})
    assert response.status_code == 200
    assert response.json()["text"] == "private transcript"
    rows = list(db.scalars(select(Experiment)))
    assert len(rows) == 2
    assert all(row.status == "completed" for row in rows)
    assert "private" not in str([(row.input_summary, row.output_metadata) for row in rows])


def test_bad_audio_rejected_before_provider(client):
    assert client.post("/api/v1/voicemind/transcribe", files={"file": ("a.wav", b"garbage", "audio/wav")}).status_code == 415
    assert client.post("/api/v1/voicemind/transcribe", files={"file": ("a.wav", b"", "audio/wav")}).status_code == 422
    assert client.post("/api/v1/voicemind/transcribe", files={"file": ("a.wav", b"x" * 1025, "audio/wav")}).status_code == 413
    assert client.post("/api/v1/voicemind/transcribe", files={"file": ("a.wav", b"RIFF0000WAVE", "text/plain")}).status_code == 415


def test_safe_provider_failure_is_recorded(client, db):
    from app.api.routes.voicemind import get_groq

    class Provider:
        async def chat(self, *args):
            raise APIError(429, "provider_rate_limit", "Try again later.")

    client.app.dependency_overrides[get_groq] = Provider
    response = client.post("/api/v1/voicemind/chat", json={"messages": [{"role": "user", "content": "secret prompt"}]})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "provider_rate_limit"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    experiment = db.scalar(select(Experiment))
    assert experiment.status == "failed"
    assert experiment.error == "Try again later."


def test_price_permission_and_mocked_scraping(client, db, monkeypatch):
    from app.services.scraping_service import ScrapingService
    monkeypatch.setattr(ScrapingService, "fetch_html", lambda *args, **kwargs: b"<h1>Example</h1><b>$9.99</b>")
    body = {"items": [{"url": "https://shop.example/item", "price_selector": "b", "currency": "USD"}]}
    assert client.post("/api/v1/pricepilot/compare", json=body).status_code == 403
    response = client.post("/api/v1/pricepilot/compare", json={**body, "permission_confirmed": True})
    assert response.status_code == 200
    assert response.json()["currency_groups"][0]["lowest_price"] == "9.99"
    assert response.json()["product_identity_verified"] is False


def test_health_reports_real_failures_without_paths(client, monkeypatch):
    import app.api.routes.health as health
    config = health.get_settings()
    monkeypatch.setattr(health, "get_settings", lambda: config.model_copy(update={"data_dir": config.data_dir / "missing-private-directory"}))
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["checks"]["storage"]["status"] == "error"
    assert "missing-private-directory" not in response.text


def test_health_provider_probe_checks_configured_models(client, monkeypatch):
    import app.api.routes.health as health
    from pydantic import SecretStr
    config = health.get_settings().model_copy(update={"groq_api_key": SecretStr("health-private-key")})
    monkeypatch.setattr(health, "get_settings", lambda: config)
    async def listing(self):
        return [{"id": config.groq_model, "active": True}]
    monkeypatch.setattr(health.GroqService, "list_models", listing)
    response = client.get("/api/v1/health?check_provider=true")
    assert response.status_code == 503
    assert response.json()["checks"]["groq"]["chat_model_available"] is True
    assert response.json()["checks"]["groq"]["transcription_model_available"] is False
    assert "health-private-key" not in response.text


def test_unexpected_failure_is_sanitized_and_recorded(client, db):
    from app.api.routes.voicemind import get_groq
    class Provider:
        async def chat(self, *args):
            raise RuntimeError("DO-NOT-EXPOSE-provider-secret")
    client.app.dependency_overrides[get_groq] = Provider
    response = client.post("/api/v1/voicemind/chat", json={"messages": [{"role": "user", "content": "hello"}]})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "DO-NOT-EXPOSE" not in response.text
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert db.scalar(select(Experiment)).status == "failed"
