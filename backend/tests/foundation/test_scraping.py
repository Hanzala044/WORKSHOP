import socket

import pytest

from app.core.config import Settings
from app.core.errors import APIError
from app.services.scraping_service import ScrapingService


def dns_answers(*addresses):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]


@pytest.fixture
def scraper(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: dns_answers("8.8.8.8"))
    return ScrapingService(Settings(_env_file=None, allowed_hosts=["shop.example", "cdn.example"]))


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.1.1", "::1", "::ffff:127.0.0.1", "224.0.0.1", "0.0.0.0"])
def test_private_addresses_blocked(scraper, monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: dns_answers(address))
    with pytest.raises(APIError) as exc:
        scraper.validate_url("https://shop.example/item")
    assert exc.value.code == "unsafe_address"


def test_mixed_dns_answers_blocked(scraper, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: dns_answers("8.8.8.8", "10.0.0.1"))
    with pytest.raises(APIError):
        scraper.validate_url("https://shop.example/item")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@shop.example", "https://shop.example:8443", "http://shop.example:443", "https://evil.example", "https://shop.example\\@evil.example", "https://shop.example/\n"])
def test_bad_urls_and_unlisted_hosts(scraper, url):
    with pytest.raises(APIError):
        scraper.validate_url(url)


def test_permission_required_before_network(scraper, monkeypatch):
    monkeypatch.setattr(scraper, "validate_url", lambda *args: pytest.fail("Network attempted without permission"))
    with pytest.raises(APIError) as exc:
        scraper.fetch_html("https://shop.example/item")
    assert exc.value.code == "permission_required"


def test_robots_denial_and_missing_policy(scraper, monkeypatch):
    monkeypatch.setattr(scraper, "_request", lambda *args: (200, {}, b"User-agent: *\nDisallow: /private"))
    with pytest.raises(APIError) as exc:
        scraper.fetch_html("https://shop.example/private", True)
    assert exc.value.code == "robots_denied"
    scraper._robots.clear()
    monkeypatch.setattr(scraper, "_request", lambda *args: (404, {}, b""))
    with pytest.raises(APIError) as exc:
        scraper.fetch_html("https://shop.example/item", True)
    assert exc.value.code == "robots_unavailable"


def test_redirect_checks_destination_policy(scraper, monkeypatch):
    requested = []
    def request(url, limit):
        requested.append(url)
        if url == "https://shop.example/robots.txt":
            return 200, {}, b"User-agent: *\nAllow: /"
        if url == "https://shop.example/item":
            return 302, {"location": "https://cdn.example/private"}, b""
        if url == "https://cdn.example/robots.txt":
            return 200, {}, b"User-agent: *\nDisallow: /"
        pytest.fail("Requested denied destination")
    monkeypatch.setattr(scraper, "_request", request)
    with pytest.raises(APIError) as exc:
        scraper.fetch_html("https://shop.example/item", True)
    assert exc.value.code == "robots_denied"
    assert "https://cdn.example/private" not in requested


def test_redirect_cannot_escape_allowlist(scraper, monkeypatch):
    def request(url, limit):
        if url.endswith("robots.txt"):
            return 200, {}, b"User-agent: *\nAllow: /"
        return 302, {"location": "https://evil.example/"}, b""
    monkeypatch.setattr(scraper, "_request", request)
    with pytest.raises(APIError) as exc:
        scraper.fetch_html("https://shop.example/item", True)
    assert exc.value.code == "host_not_allowed"


def test_pinned_connection_uses_original_tls_hostname(scraper, monkeypatch):
    from app.services import scraping_service as service
    calls = {}
    class Response:
        status = 200
        def getheaders(self):
            return [("Content-Type", "text/html"), ("Content-Length", "13")]
        def read1(self, limit):
            if calls.get("read"):
                return b""
            calls["read"] = True
            return b"<h1>Test</h1>"
    class Connection:
        sock = None
        def __init__(self, host, port, **kwargs):
            calls["host"] = host
        def request(self, method, target, headers):
            calls["target"] = target
            self._create_connection(("unchecked", 443), 20)
        def getresponse(self):
            return Response()
        def close(self):
            calls["closed"] = True
    monkeypatch.setattr(service.http.client, "HTTPSConnection", Connection)
    monkeypatch.setattr(socket, "create_connection", lambda address, *args: calls.update(pinned=address))
    scraper._request("https://shop.example/path?q=1", 100)
    assert calls["host"] == "shop.example"
    assert calls["pinned"] == ("8.8.8.8", 443)
    assert calls["target"] == "/path?q=1"
    assert calls["closed"] is True


def test_size_and_content_encoding_bounds(scraper, monkeypatch):
    from app.services import scraping_service as service
    class Response:
        status = 200
        def getheaders(self):
            return [("Content-Length", "99999999")]
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(service.http.client, "HTTPSConnection", Connection)
    with pytest.raises(APIError) as exc:
        scraper._request("https://shop.example/item", 1024)
    assert exc.value.code == "website_too_large"
