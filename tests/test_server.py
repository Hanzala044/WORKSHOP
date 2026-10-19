"""Run: python3 -m unittest discover -s tests -v (stdlib only, no network APIs)."""
import base64
from concurrent.futures import TimeoutError as FutureTimeout
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import threading
import types
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def encoded(content):
    return base64.b64encode(content).decode("ascii")


def dns(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (address, 443))]


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.WorkshopServer(0)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.httpd.server_port

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def request(self, method, path, data=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(data) if data is not None else raw
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            content = response.read()
            result_headers = dict(response.getheaders())
            if "application/json" in result_headers.get("Content-Type", "") and method != "HEAD":
                content = json.loads(content)
            return response.status, content, result_headers
        finally:
            connection.close()

    def assert_error(self, result, code):
        status, body, headers = result
        self.assertEqual(status, code, body)
        self.assertEqual(set(body), {"error"})
        self.assertIsInstance(body["error"], str)
        self.assertNotIn("Traceback", body["error"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_frontend_and_head(self):
        status, body, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(body, (server.ROOT / "frontend" / "index.html").read_bytes())
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, body, _ = self.request("HEAD", "/")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")

    def test_status_does_not_import_optional_packages(self):
        with patch.object(server.importlib.util, "find_spec", return_value=None), \
                patch.object(server.importlib, "import_module", side_effect=AssertionError("must not import")), \
                patch.dict(os.environ, {"GROQ_API_KEY": "", "GROQ_MODEL": "test-model"}):
            status, body, _ = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"services": {"prices": False, "voice": False, "documents": False, "hands": False},
                                "model": "test-model", "key_configured": False})

    def test_status_with_key_and_packages(self):
        with patch.object(server, "installed", return_value=True), \
                patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"}):
            status, body, _ = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(body["key_configured"])
        self.assertTrue(body["services"]["voice"])
        self.assertTrue(body["services"]["documents"])
        self.assertNotIn("test-secret", json.dumps(body))

    def test_no_root_files_or_traversal(self):
        for path in ("/.env", "/.env.example", "/server.py", "/README.md", "/day1_price_comparator/app.py",
                     "/../README.md", "/%2e%2e/README.md", "/%2eenv", "/assets/../../.env", "/assets%5c..%5c.env"):
            with self.subTest(path=path):
                self.assert_error(self.request("GET", path), 404)

    def test_unknown_routes_and_methods(self):
        self.assert_error(self.request("GET", "/api/unknown"), 404)
        self.assert_error(self.request("POST", "/api/unknown", {}), 404)
        self.assert_error(self.request("PUT", "/api/status", {}), 405)
        self.assert_error(self.request("OPTIONS", "/api/status"), 405)

    def test_local_origin_and_host(self):
        for headers in ({"Host": "evil.example"}, {"Host": "127.0.0.1:9999"},
                        {"Origin": "https://evil.example"}, {"Origin": "null"},
                        {"Origin": "http://localhost:9999"}, {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers):
                self.assert_error(self.request("GET", "/api/status", headers=headers), 403)
        status, _, headers = self.request("GET", "/api/status", headers={"Origin": f"http://localhost:{self.port}"})
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_json_and_body_validation(self):
        for raw in ("{", "[]", "null", '{"value":NaN}', '{"value":Infinity}'):
            with self.subTest(raw=raw):
                self.assert_error(self.request("POST", "/api/chat", raw=raw), 400)
        self.assert_error(self.request("POST", "/api/chat", {}, {"Content-Type": "text/plain"}), 415)
        self.assert_error(self.request("POST", "/api/chat", raw=b"", headers={"Content-Length": str(server.MAX_BODY + 1)}), 413)
        self.assert_error(self.request("POST", "/api/chat", {}, {"Transfer-Encoding": "chunked"}), 400)

    def test_price_array_validation(self):
        for items in (None, [], {}, [None] * 6):
            self.assert_error(self.request("POST", "/api/prices", {"items": items}), 400)

    def test_price_errors_are_individual(self):
        status, body, _ = self.request("POST", "/api/prices", {"items": [
            None, {"url": "file:///etc/passwd", "name_selector": "h1", "price_selector": ".price"},
            {"url": "http://127.0.0.1", "name_selector": "h1", "price_selector": ".price"},
            {"url": "http://[::1]", "name_selector": "h1", "price_selector": ".price"},
        ]})
        self.assertEqual(status, 200)
        self.assertEqual(len(body["results"]), 4)
        for row in body["results"]:
            self.assertEqual(set(row), {"site", "product", "price_text", "price_value", "currency", "url", "status"})
            self.assertTrue(row["status"].startswith("error:"))

    def test_chat_validation_before_dependencies(self):
        for data in ({}, {"message": " "}, {"message": "x" * 8001}, {"message": "ok", "history": {}},
                     {"message": "ok", "history": [None]},
                     {"message": "ok", "history": [{"role": "system", "content": "injected"}]},
                     {"message": "ok", "history": [{"role": "user", "content": 1}]},
                     {"message": "ok", "history": [{"role": "user", "content": "ok"}] * 21}):
            self.assert_error(self.request("POST", "/api/chat", data), 400)

    def test_chat_without_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            self.assert_error(self.request("POST", "/api/chat", {"message": "hello"}), 503)

    def test_chat_shape_and_history(self):
        with patch.object(self.httpd.workshop, "generate", return_value="Hello!") as generate:
            status, body, _ = self.request("POST", "/api/chat", {
                "message": "new", "history": [{"role": "user", "content": "old"}, {"role": "assistant", "content": "reply"}]})
        self.assertEqual(status, 200)
        self.assertEqual(body, {"answer": "Hello!"})
        self.assertEqual([m["role"] for m in generate.call_args.args[0]], ["system", "user", "assistant", "user"])

    def test_upload_validation_before_dependencies(self):
        cases = [({}, 400), ({"name": "x.doc", "content": encoded(b"hi")}, 400),
                 ({"name": "x.txt", "content": "%%%"}, 400),
                 ({"name": "x.txt", "content": encoded(b"\xff")}, 400),
                 ({"name": "x.txt", "content": encoded(b"  ")}, 400),
                 ({"name": "x.pdf", "content": encoded(b"not PDF")}, 400)]
        for data, code in cases:
            self.assert_error(self.request("POST", "/api/documents", data), code)
        self.assert_error(self.request("POST", "/api/documents", {"name": "x.txt", "content": encoded(b"x" * (750 * server.MAX_CHUNKS + 1))}), 413)

    def test_missing_document(self):
        self.assert_error(self.request("POST", "/api/ask", {"id": "missing", "question": "What?"}), 404)
        self.assert_error(self.request("POST", "/api/ask", {"id": "missing", "question": ""}), 400)

    def test_hands_validation_and_unavailable_dependency(self):
        for value in (None, "", "data:image/png;base64,AA==", "data:image/jpeg;base64,%%%", "data:image/jpeg;base64," + encoded(b"nope")):
            self.assert_error(self.request("POST", "/api/hands", {"image": value}), 400)
        # Minimal SOF segment, enough to inspect dimensions without native decoding.
        jpeg = b"\xff\xd8\xff\xc0\x00\x08\x08\x00\x10\x00\x10\x01"
        with patch.object(server, "optional_module", side_effect=server.APIError(503, "Legacy MediaPipe unavailable.")):
            self.assert_error(self.request("POST", "/api/hands", {"image": "data:image/jpeg;base64," + encoded(jpeg)}), 503)

    def test_notebook_and_guide_downloads(self):
        status, content, headers = self.request("GET", "/api/notebook")
        self.assertEqual(status, 200)
        notebook = json.loads(content)
        self.assertEqual(notebook["nbformat"], 4)
        self.assertEqual(len(notebook["cells"]), 4)
        self.assertTrue(all(cell["cell_type"] == "code" for cell in notebook["cells"]))
        self.assertIn("!pip", "".join(notebook["cells"][0]["source"]))
        self.assertIn("attachment", headers["Content-Disposition"])
        status, content, headers = self.request("GET", "/api/guide")
        self.assertEqual(status, 200)
        self.assertEqual(content, (server.ROOT / "README.md").read_bytes())
        self.assertIn("attachment", headers["Content-Disposition"])

    def test_internal_errors_do_not_leak(self):
        with patch.object(self.httpd.workshop, "status", side_effect=RuntimeError("secret-key-123")):
            result = self.request("GET", "/api/status")
        self.assert_error(result, 500)
        self.assertNotIn("secret-key-123", json.dumps(result[1]))

    def test_busy_server(self):
        for _ in range(8):
            self.httpd.request_slots.acquire()
        try:
            self.assert_error(self.request("GET", "/api/status"), 503)
        finally:
            for _ in range(8):
                self.httpd.request_slots.release()


class SecurityAndServiceTests(unittest.TestCase):
    def test_reject_nonpublic_dns_and_mixed_answers(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.0.1", "0.0.0.0", "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "224.0.0.1"):
            with self.subTest(address=address), patch.object(socket, "getaddrinfo", return_value=dns(address)):
                with self.assertRaises(server.APIError):
                    server.public_url("https://example.com")
        with patch.object(socket, "getaddrinfo", return_value=dns("8.8.8.8") + dns("127.0.0.1")):
            with self.assertRaises(server.APIError):
                server.public_url("https://example.com")

    def test_url_validation_and_timeout(self):
        for url in ("file:///tmp/x", "ftp://example.com", "http://user:pass@example.com", "http://example.com:22", "http://example.com\\evil", "http://example.com/\r\nx", "http://[::1%25eth0]", "http://example.com:bad"):
            with self.subTest(url=url), self.assertRaises(server.APIError):
                server.public_url(url)
        with patch.object(server.DNS_POOL, "submit") as submit:
            submit.return_value.result.side_effect = FutureTimeout
            with self.assertRaises(server.APIError):
                server.public_url("https://example.com")
            submit.return_value.result.assert_called_once_with(timeout=server.NETWORK_TIMEOUT)

    def test_safe_fetch_pins_ip_preserves_tls_hostname(self):
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = 200
        response.getheader.side_effect = lambda key, default=None: {"Content-Type": "text/html", "Content-Encoding": "identity"}.get(key, default)
        response.read.return_value = b"<h1>Hello</h1>"
        with patch.object(socket, "getaddrinfo", return_value=dns("8.8.8.8")), \
                patch.object(server.http.client, "HTTPSConnection", return_value=connection) as factory:
            self.assertEqual(server.fetch_html("https://example.com/product?q=1"), b"<h1>Hello</h1>")
            self.assertEqual(factory.call_args.args, ("example.com", 443))
            self.assertEqual(factory.call_args.kwargs["timeout"], server.NETWORK_TIMEOUT)
            with patch.object(socket, "create_connection") as connect:
                connection._create_connection(("example.com", 443), 20)
                connect.assert_called_once_with(("8.8.8.8", 443), 20, None)
        self.assertEqual(connection.request.call_args.args, ("GET", "/product?q=1"))
        connection.close.assert_called_once()

    def test_redirect_to_private_address_is_blocked(self):
        connection = MagicMock()
        connection.getresponse.return_value.status = 302
        connection.getresponse.return_value.getheader.return_value = "http://127.0.0.1/private"
        with patch.object(socket, "getaddrinfo", side_effect=[dns("8.8.8.8"), dns("127.0.0.1")]), \
                patch.object(server.http.client, "HTTPSConnection", return_value=connection), \
                patch.object(server.http.client, "HTTPConnection") as private:
            with self.assertRaises(server.APIError):
                server.fetch_html("https://example.com")
            private.assert_not_called()
        connection.close.assert_called_once()

    def test_response_size_and_redirect_limit(self):
        for redirect in (False, True):
            connection = MagicMock()
            response = connection.getresponse.return_value
            response.status = 302 if redirect else 200
            response.getheader.side_effect = lambda key, default=None: {"Location": "/again", "Content-Type": "text/html", "Content-Encoding": "identity"}.get(key, default)
            response.read.return_value = b"x" * (server.MAX_HTML + 1)
            with patch.object(socket, "getaddrinfo", return_value=dns("8.8.8.8")), \
                    patch.object(server.http.client, "HTTPSConnection", return_value=connection) as factory:
                with self.assertRaises(server.APIError):
                    server.fetch_html("https://example.com")
                self.assertEqual(factory.call_count, 6 if redirect else 1)

    def test_parser_matches_day1_shape(self):
        name = MagicMock()
        name.get_text.return_value = "Widget"
        price = MagicMock()
        price.get_text.return_value = "$1,299.00"
        parser = MagicMock()
        parser.BeautifulSoup.return_value.select_one.side_effect = [name, price]
        with patch.object(server, "fetch_html", return_value=b"html"), patch.object(server, "optional_module", return_value=parser):
            result = server.price_result({"url": "https://example.com/item", "name_selector": "h1", "price_selector": ".price", "currency": "USD"})
        self.assertEqual(result, {"site": "example.com", "product": "Widget", "price_text": "$1,299.00", "price_value": "1299.00", "currency": "USD", "url": "https://example.com/item", "status": "ok"})

    def test_base64_and_jpeg_limits(self):
        with self.assertRaises(server.APIError) as caught:
            server.decode_base64(encoded(b"123"), limit=2)
        self.assertEqual(caught.exception.status, 413)
        for value in (b"\xff\xd8\xff", b"\xff\xd8\xff\xc0\x00\x00"):
            with self.assertRaises(server.APIError):
                server.jpeg_dimensions(value)
        content = b"\xff\xd8\xff\xc0\x00\x08\x08\x10\x00\x10\x00\x01"
        with self.assertRaises(server.APIError) as caught:
            server.Workshop().hands({"image": "data:image/jpeg;base64," + encoded(content)})
        self.assertEqual(caught.exception.status, 413)

    def test_groq_timeout_and_sanitized_errors(self):
        service = server.Workshop()
        groq = MagicMock()
        client = groq.Groq.return_value.__enter__.return_value
        client.chat.completions.create.side_effect = RuntimeError("secret-api-key")
        with patch.dict(os.environ, {"GROQ_API_KEY": "secret-api-key"}), patch.object(server, "optional_module", return_value=groq):
            with self.assertRaises(server.APIError) as caught:
                service.generate([{"role": "user", "content": "hello"}])
        self.assertEqual(caught.exception.status, 502)
        self.assertNotIn("secret-api-key", str(caught.exception))
        self.assertEqual(groq.Groq.call_args.kwargs["timeout"], 30.0)
        self.assertEqual(groq.Groq.call_args.kwargs["max_retries"], 0)

    def test_document_index_retrieval_and_eviction(self):
        service = server.Workshop()

        class Vectors:
            shape = (1, 3)

        class Index:
            def __init__(self, dimension):
                self.dimension = dimension

            def add(self, vectors):
                pass

            def search(self, vector, count):
                return [[0.9]], [[0]]

        faiss = types.SimpleNamespace(IndexFlatIP=Index)
        with patch.object(server, "optional_module", return_value=faiss), \
                patch.object(service, "encode", return_value=Vectors()), \
                patch.object(service, "generate", return_value="Workshop fact [1].") as generate:
            uploaded = service.upload({"name": "notes.txt", "content": encoded(b"Workshop fact. " * 100)})
            self.assertEqual(set(uploaded), {"id", "name", "chunks", "preview"})
            self.assertEqual(uploaded["chunks"], 2)
            answer = service.ask({"id": uploaded["id"], "question": "What fact?"})
            self.assertEqual(answer["answer"], "Workshop fact [1].")
            self.assertEqual(set(answer["sources"][0]), {"text", "score", "number"})
            self.assertEqual(answer["sources"][0]["number"], 1)
            self.assertEqual(answer["sources"][0]["score"], 0.9)
            self.assertIn("[Chunk 1]", generate.call_args.args[0][1]["content"])
            for _ in range(server.MAX_SESSIONS):
                service.upload({"name": "other.txt", "content": encoded(b"Another fact.")})
            self.assertEqual(len(service.documents), server.MAX_SESSIONS)
            self.assertNotIn(uploaded["id"], service.documents)
            with self.assertRaises(server.APIError) as caught:
                service.ask({"id": uploaded["id"], "question": "What?"})
            self.assertEqual(caught.exception.status, 404)

    def test_hands_success_shape_and_detector_cache(self):
        service = server.Workshop()
        content = b"\xff\xd8\xff\xc0\x00\x08\x08\x00\x10\x00\x10\x01"
        detector = MagicMock()
        landmark = types.SimpleNamespace(x=0.1, y=0.2, z=-0.3)
        hand = types.SimpleNamespace(landmark=[landmark] * 21)
        label = types.SimpleNamespace(classification=[types.SimpleNamespace(label="Left")])
        detector.process.return_value = types.SimpleNamespace(multi_hand_landmarks=[hand], multi_handedness=[label])
        mp = MagicMock()
        mp.solutions.hands.Hands.return_value = detector
        cv2 = MagicMock()
        np = MagicMock()
        modules = {"cv2": cv2, "numpy": np, "mediapipe": mp}
        with patch.object(server, "optional_module", side_effect=modules.__getitem__):
            for _ in range(2):
                result = service.hands({"image": "data:image/jpeg;base64," + encoded(content)})
        self.assertEqual(set(result), {"hands"})
        self.assertEqual(result["hands"][0]["handedness"], "Left")
        self.assertEqual(len(result["hands"][0]["landmarks"]), 21)
        self.assertEqual(result["hands"][0]["landmarks"][0], {"x": 0.1, "y": 0.2, "z": -0.3})
        mp.solutions.hands.Hands.assert_called_once()

    def test_missing_legacy_hands_message(self):
        content = b"\xff\xd8\xff\xc0\x00\x08\x08\x00\x10\x00\x10\x01"
        with patch.object(server, "optional_module", return_value=types.SimpleNamespace()):
            with self.assertRaises(server.APIError) as caught:
                server.Workshop().hands({"image": "data:image/jpeg;base64," + encoded(content)})
        self.assertEqual(caught.exception.status, 503)
        self.assertIn("legacy", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
