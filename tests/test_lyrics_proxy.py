"""Verify lyric transport, input boundaries, and bounded transient caching."""
import importlib.util
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lyrics_proxy", ROOT / "musiclib" / "proxy_server.py")
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


def upstream(data, status=200):
    response = io.BytesIO(data if isinstance(data, bytes) else json.dumps(data).encode())
    response.status = status
    return response


class LyricsProxy(unittest.TestCase):
    def setUp(self):
        proxy._lyric_cache.clear()
        proxy._api_cache.clear()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        quota = patch.object(proxy, "_quota", proxy.RollingQuota(Path(directory.name) / "quota.sqlite3"))
        quota.start()
        self.addCleanup(quota.stop)

    def test_joox_identifier_and_translation_are_preserved(self):
        sid = "bLnv0PqDX_qAlIqapc+Okw=="
        with patch.object(proxy.urllib.request, "urlopen", return_value=upstream({
            "lyric": "[00:01.00]Original test line", "tlyric": "[00:01.00]Test translation",
        })) as fetch:
            result = proxy.lyrics("joox", sid)
        request = fetch.call_args.args[0]
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query), {
            "types": ["lyric"], "source": ["joox"], "id": [sid],
        })
        self.assertIn("%2B", request.full_url)
        self.assertIn("%3D%3D", request.full_url)
        self.assertEqual(result, {"lyric": "[00:01.00]Original test line",
                                  "translation": "[00:01.00]Test translation", "source": "joox"})
        self.assertEqual(fetch.call_args.kwargs["timeout"], 5)

    def test_empty_lyrics_are_a_success(self):
        for data in ({"lyric": "", "tlyric": ""}, {}, {"lyric": None, "tlyric": None}):
            with self.subTest(data=data):
                proxy._lyric_cache.clear()
                proxy._api_cache.clear()
                with patch.object(proxy.urllib.request, "urlopen", return_value=upstream(data)):
                    self.assertEqual(proxy.lyrics("netease", "missing"), {
                        "lyric": "", "translation": "", "source": "netease",
                    })

    def test_invalid_identifiers_never_reach_upstream(self):
        for source, sid in (("evil", "1"), ("netease&types=url", "1"), ("netease", ""),
                            ("netease", "a" * 201), ("netease", "1&types=url"),
                            ("joox", "test\nheader"), ("joox", "https://example.com")):
            with self.subTest(source=source, sid=sid), patch.object(proxy.urllib.request, "urlopen") as fetch:
                with self.assertRaises(HTTPException) as error:
                    proxy.lyrics(source, sid)
                self.assertEqual(error.exception.status_code, 400)
                fetch.assert_not_called()

    def test_upstream_failures_are_generic_and_not_cached(self):
        cases = [
            urllib.error.HTTPError("private-url", 403, "private-error", {}, io.BytesIO(b"private-body")),
            urllib.error.URLError("private-server"), TimeoutError("private-host"),
        ]
        for failure in cases:
            with self.subTest(failure=type(failure).__name__), \
                    patch.object(proxy.urllib.request, "urlopen", side_effect=failure):
                with self.assertRaises(HTTPException) as error:
                    proxy.lyrics("netease", "1")
                self.assertEqual(error.exception.status_code, 502)
                self.assertEqual(error.exception.detail, "lyrics temporarily unavailable")
                self.assertFalse(proxy._lyric_cache)

    def test_invalid_or_oversized_responses_are_rejected(self):
        for body in (b"not-json", [], {"lyric": ["line"]}, {"tlyric": {"text": "line"}},
                     {"error": "private failure"}, {"lyric": 0}, {"tlyric": False},
                     b"x" * (proxy.LYRIC_MAX_BYTES + 1)):
            with self.subTest(body_type=type(body).__name__), \
                    patch.object(proxy.urllib.request, "urlopen", return_value=upstream(body)):
                with self.assertRaises(HTTPException) as error:
                    proxy.lyrics("netease", "1")
                self.assertEqual(error.exception.status_code, 502)
                self.assertFalse(proxy._lyric_cache)

    def test_response_read_is_bounded(self):
        response = upstream({"lyric": ""})
        with patch.object(response, "read", wraps=response.read) as read, \
                patch.object(proxy.urllib.request, "urlopen", return_value=response):
            proxy.lyrics("netease", "1")
        read.assert_called_once_with(proxy.LYRIC_MAX_BYTES + 1)

    def test_cache_expires_and_is_bounded(self):
        with patch.object(proxy.time, "monotonic", return_value=100), \
                patch.object(proxy.urllib.request, "urlopen", side_effect=lambda *args, **kw: upstream({"lyric": "line"})) as fetch:
            proxy.lyrics("netease", "1")
            proxy.lyrics("netease", "1")
            self.assertEqual(fetch.call_count, 1)
        with patch.object(proxy.time, "monotonic", return_value=401), \
                patch.object(proxy.urllib.request, "urlopen", side_effect=lambda *args, **kw: upstream({"lyric": "new line"})) as fetch:
            self.assertEqual(proxy.lyrics("netease", "1")["lyric"], "new line")
            self.assertEqual(fetch.call_count, 1)
            with patch.object(proxy._quota, "limit", 1000):
                for number in range(2, proxy.LYRIC_CACHE_SIZE + 2):
                    proxy.lyrics("netease", str(number))
            self.assertEqual(len(proxy._lyric_cache), proxy.LYRIC_CACHE_SIZE)
            self.assertNotIn(("netease", "1"), proxy._lyric_cache)


class LyricsRoute(unittest.IsolatedAsyncioTestCase):
    async def test_encoded_identifier_survives_the_asgi_route(self):
        proxy._lyric_cache.clear()
        proxy._api_cache.clear()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        quota = patch.object(proxy, "_quota", proxy.RollingQuota(Path(directory.name) / "quota.sqlite3"))
        quota.start()
        self.addCleanup(quota.stop)
        sid = "bLnv0PqDX_qAlIqapc+Okw=="
        raw_path = "/lyrics/joox/" + urllib.parse.quote(sid, safe="") + ".json"
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        with patch.object(proxy.urllib.request, "urlopen", return_value=upstream({"lyric": ""})) as fetch:
            await proxy.app({
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": "GET", "scheme": "http", "path": urllib.parse.unquote(raw_path),
                "raw_path": raw_path.encode(), "query_string": b"", "root_path": "",
                "server": ("testserver", 80), "client": ("127.0.0.1", 1234), "headers": [],
            }, receive, send)
        status = next(message["status"] for message in messages if message["type"] == "http.response.start")
        body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"lyric": "", "translation": "", "source": "joox"})
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(fetch.call_args.args[0].full_url).query)["id"], [sid])


if __name__ == "__main__":
    unittest.main()
