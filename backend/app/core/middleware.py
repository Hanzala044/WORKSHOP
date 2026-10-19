import asyncio
import time
from urllib.parse import urlsplit
from uuid import uuid4

from starlette.responses import JSONResponse


class RequestSafetyMiddleware:
    """Bound chunked requests too, block cross-origin writes, and assign request IDs."""

    def __init__(self, app, settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        headers = {key.lower(): value for key, value in scope.get("headers", [])}

        async def safe_send(message):
            if message["type"] == "http.response.start":
                additions = {
                    b"x-request-id": request_id.encode(), b"x-content-type-options": b"nosniff",
                    b"cache-control": b"no-store", b"referrer-policy": b"no-referrer",
                }
                message["headers"] = [(key, value) for key, value in message.get("headers", []) if key.lower() not in additions]
                message["headers"].extend(additions.items())
            await send(message)

        async def reject(status, code, text):
            response = JSONResponse({"error": {"code": code, "message": text}, "request_id": request_id}, status_code=status)
            await response(scope, receive, safe_send)

        host = headers.get(b"host", b"").decode("latin-1")
        try:
            parsed_host = urlsplit("http://" + host)
            valid_host = (
                bool(host) and not any(c.isspace() for c in host)
                and parsed_host.hostname in {h.strip("[]").lower() for h in self.settings.trusted_hosts}
                and parsed_host.username is None and parsed_host.password is None
                and not parsed_host.path and not parsed_host.query and not parsed_host.fragment
                and (parsed_host.port is None or 1 <= parsed_host.port <= 65535)
                and sum(key.lower() == b"host" for key, _ in scope.get("headers", [])) == 1
            )
        except ValueError:
            valid_host = False
        if not valid_host:
            await reject(400, "host_denied", "Request Host header is not allowed.")
            return
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = headers.get(b"origin", b"").decode("latin-1")
            host = headers.get(b"host", b"").decode("latin-1")
            same_origin = f"{scope.get('scheme', 'http')}://{host}"
            if origin and origin not in {*self.settings.cors_origins, same_origin}:
                await reject(403, "origin_denied", "Request origin is not allowed.")
                return
            fetch_site = headers.get(b"sec-fetch-site", b"")
            if fetch_site == b"cross-site" and not origin:
                await reject(403, "origin_denied", "Cross-site writes require an allowed origin.")
                return
        length = headers.get(b"content-length")
        if length:
            try:
                size = int(length)
                if size < 0:
                    raise ValueError
            except ValueError:
                await reject(400, "invalid_content_length", "Content-Length is invalid.")
                return
            if size > self.settings.max_request_bytes:
                await reject(413, "request_too_large", "Request exceeds the configured body limit.")
                return
        body = bytearray()
        deadline = time.monotonic() + self.settings.network_timeout
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=max(0, deadline - time.monotonic()))
            except TimeoutError:
                await reject(408, "request_timeout", "Request body was not received in time.")
                return
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.settings.max_request_bytes:
                await reject(413, "request_too_large", "Request exceeds the configured body limit.")
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, safe_send)
