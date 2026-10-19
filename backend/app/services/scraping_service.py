"""Permission-gated, DNS-pinned public-web fetching; no proxy or cookie support."""
import http.client
import ipaddress
import re
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import BoundedSemaphore
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from app.core.config import Settings, get_settings
from app.core.errors import APIError

USER_AGENT = "WorkshopPricePilot/1.0"
_DNS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pricepilot-dns")
_DNS_SLOTS = BoundedSemaphore(4)


class ScrapingService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._robots: dict[str, RobotFileParser] = {}

    def validate_url(self, url: str) -> tuple:
        try:
            if not isinstance(url, str) or len(url) > 4096 or re.search(r"[\s\\\x00-\x1f\x7f]", url):
                raise ValueError
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
                raise ValueError
            host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if port != (443 if parsed.scheme == "https" else 80) or "%" in host:
                raise ValueError
        except (ValueError, UnicodeError):
            raise APIError(422, "invalid_url", "Use a public HTTP(S) URL without credentials on its standard port.") from None
        if host not in self.settings.allowed_hosts:
            raise APIError(403, "host_not_allowed", "Website hostname is not in the backend scrape allowlist.")
        if not _DNS_SLOTS.acquire(blocking=False):
            raise APIError(503, "dns_busy", "DNS resolver is busy; try again later.")
        try:
            future = _DNS_POOL.submit(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM)
        except Exception:
            _DNS_SLOTS.release()
            raise
        future.add_done_callback(lambda _: _DNS_SLOTS.release())
        try:
            answers = future.result(timeout=self.settings.network_timeout)
        except (OSError, TimeoutError):
            future.cancel()
            raise APIError(502, "dns_failed", "Website DNS resolution failed or timed out.") from None
        if not answers:
            raise APIError(422, "unsafe_address", "Website has no public addresses.")
        for answer in answers:
            address = ipaddress.ip_address(answer[4][0])
            mapped = getattr(address, "ipv4_mapped", None)
            if not address.is_global or address.is_multicast or address.is_reserved or (mapped and not mapped.is_global):
                raise APIError(403, "unsafe_address", "Every resolved website address must be a public internet address.")
        return parsed, host, port, str(answers[0][4][0])

    def _request(self, url: str, limit: int) -> tuple[int, dict, bytes]:
        parsed, host, port, address = self.validate_url(url)
        if parsed.scheme == "https":
            connection = http.client.HTTPSConnection(host, port, timeout=self.settings.network_timeout, context=ssl.create_default_context())
        else:
            connection = http.client.HTTPConnection(host, port, timeout=self.settings.network_timeout)
        # HTTPS retains hostname verification/SNI while the socket uses only the vetted IP.
        connection._create_connection = lambda _addr, timeout, source_address=None: socket.create_connection((address, port), timeout, source_address)
        deadline = time.monotonic() + self.settings.network_timeout
        try:
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.request("GET", target, headers={
                "Host": host, "User-Agent": USER_AGENT, "Accept-Encoding": "identity",
                "Accept": "text/html,application/xhtml+xml,text/plain",
            })
            response = connection.getresponse()
            headers = {key.lower(): value for key, value in response.getheaders()}
            if 300 <= response.status < 400:
                return response.status, headers, b""
            if headers.get("content-encoding", "identity").lower() != "identity":
                raise APIError(502, "unsupported_encoding", "Website must return an uncompressed response.")
            length = headers.get("content-length")
            if length and (not length.isdigit() or int(length) > limit):
                raise APIError(502, "website_too_large", "Website response exceeds the size limit.")
            body = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise APIError(504, "website_timeout", "Website response timed out.")
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(65536, limit + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > limit:
                    raise APIError(502, "website_too_large", "Website response exceeds the size limit.")
            return response.status, headers, bytes(body)
        except APIError:
            raise
        except (OSError, http.client.HTTPException, UnicodeError, ValueError):
            raise APIError(502, "website_failed", "Website request failed or timed out.") from None
        finally:
            connection.close()

    @staticmethod
    def _redirect(url: str, headers: dict) -> str:
        location = headers.get("location")
        if not location:
            raise APIError(502, "invalid_redirect", "Website redirect has no destination.")
        try:
            next_url = urljoin(url, location)
            next_scheme = urlsplit(next_url).scheme
        except ValueError:
            raise APIError(502, "invalid_redirect", "Website redirect destination is invalid.") from None
        if urlsplit(url).scheme == "https" and next_scheme != "https":
            raise APIError(403, "unsafe_redirect", "HTTPS downgrade redirects are not permitted.")
        return next_url

    def _check_robots(self, url: str):
        parsed = urlsplit(url)
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        if origin not in self._robots:
            robots_url = origin + "/robots.txt"
            for hop in range(4):
                status, headers, body = self._request(robots_url, 256 * 1024)
                if status in {301, 302, 303, 307, 308} and hop < 3:
                    robots_url = self._redirect(robots_url, headers)
                    continue
                # Fail closed even for a missing robots file: explicit automation policy required.
                if status != 200:
                    raise APIError(403, "robots_unavailable", "A readable robots.txt automation policy is required.")
                parser = RobotFileParser()
                parser.set_url(origin + "/robots.txt")
                parser.parse(body.decode("utf-8", errors="replace").splitlines())
                self._robots[origin] = parser
                break
            else:
                raise APIError(403, "robots_unavailable", "Robots policy could not be loaded safely.")
        parser = self._robots[origin]
        if not parser.can_fetch(USER_AGENT, url):
            raise APIError(403, "robots_denied", "Website robots policy disallows this URL.")
        # Do not violate crawl-delay/request-rate directives by guessing a safe cadence.
        delay = parser.crawl_delay(USER_AGENT)
        rate = parser.request_rate(USER_AGENT)
        if (delay and delay > 0) or rate:
            raise APIError(403, "robots_rate_policy", "This website requires crawl scheduling which this local tool does not implement.")

    def fetch_html(self, url: str, permission_confirmed: bool = False) -> bytes:
        if not permission_confirmed:
            raise APIError(403, "permission_required", "Confirm you have permission to scrape the requested websites.")
        for hop in range(5):
            self.validate_url(url)
            self._check_robots(url)
            status, headers, body = self._request(url, self.settings.max_html_bytes)
            if status in {301, 302, 303, 307, 308} and hop < 4:
                url = self._redirect(url, headers)
                continue
            if status != 200:
                raise APIError(502, "website_status", "Website did not return a successful product page.")
            content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise APIError(502, "website_content_type", "Product URL must return HTML.")
            return body
        raise APIError(502, "redirect_limit", "Website exceeded the redirect limit.")
