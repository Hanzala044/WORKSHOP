import asyncio
import json
from types import SimpleNamespace

import pytest

from app.core.middleware import RequestSafetyMiddleware


def scope(extra_headers=None):
    return {"type": "http", "method": "POST", "path": "/", "scheme": "http", "headers": [(b"host", b"localhost"), *(extra_headers or [])]}


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [[], [(b"content-length", b"1")]])
async def test_chunked_body_limit_does_not_trust_content_length(headers):
    received = []
    chunks = iter([{"type": "http.request", "body": b"123", "more_body": True},
                   {"type": "http.request", "body": b"45", "more_body": False}])
    async def receive():
        return next(chunks)
    async def send(message):
        received.append(message)
    async def forbidden_app(*args):
        pytest.fail("Oversized body reached application")
    config = SimpleNamespace(max_request_bytes=4, network_timeout=1, trusted_hosts=["localhost"], cors_origins=[])
    await RequestSafetyMiddleware(forbidden_app, config)(scope(headers), receive, send)
    assert received[0]["status"] == 413
    assert json.loads(received[1]["body"])["error"]["code"] == "request_too_large"


@pytest.mark.asyncio
async def test_body_read_timeout():
    received = []
    async def receive():
        await asyncio.sleep(1)
    async def send(message):
        received.append(message)
    async def forbidden_app(*args):
        pytest.fail("Incomplete body reached application")
    config = SimpleNamespace(max_request_bytes=4, network_timeout=0.001, trusted_hosts=["localhost"], cors_origins=[])
    await RequestSafetyMiddleware(forbidden_app, config)(scope(), receive, send)
    assert received[0]["status"] == 408


@pytest.mark.asyncio
async def test_chunked_request_replayed_once():
    received = []
    chunks = iter([{"type": "http.request", "body": b"12", "more_body": True},
                   {"type": "http.request", "body": b"34", "more_body": False}])
    async def receive():
        return next(chunks)
    async def send(message):
        received.append(message)
    async def app(scope, receive, send):
        assert (await receive())["body"] == b"1234"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    config = SimpleNamespace(max_request_bytes=4, network_timeout=1, trusted_hosts=["localhost"], cors_origins=[])
    await RequestSafetyMiddleware(app, config)(scope(), receive, send)
    assert received[0]["status"] == 200
    assert dict(received[0]["headers"])[b"x-request-id"]
