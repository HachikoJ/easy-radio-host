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
        proxy._recording_cache.clear()
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
                    self.assertFalse(proxy._lyric_cache)

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
                self.assertEqual(error.exception.detail, {
                    "status": "temporary", "message": "lyrics temporarily unavailable",
                })
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
        with patch.object(proxy.time, "monotonic", return_value=100 + proxy.LYRIC_CACHE_TTL + 1), \
                patch.object(proxy.urllib.request, "urlopen", side_effect=lambda *args, **kw: upstream({"lyric": "new line"})) as fetch:
            self.assertEqual(proxy.lyrics("netease", "1")["lyric"], "new line")
            self.assertEqual(fetch.call_count, 1)
            with patch.object(proxy._quota, "limit", 1000):
                for number in range(2, proxy.LYRIC_CACHE_SIZE + 2):
                    proxy.lyrics("netease", str(number))
            self.assertEqual(len(proxy._lyric_cache), proxy.LYRIC_CACHE_SIZE)
            self.assertNotIn(("source", "netease", "1"), proxy._lyric_cache)

    def test_empty_primary_falls_back_to_strict_cross_source_match(self):
        calls = []

        def api(kind, source, deadline, **params):
            calls.append((kind, source, params))
            if kind == "lyric":
                if source == "kuwo" and params["id"] == "lyrics-2":
                    return {"lyric": "[00:01.00]南方姑娘", "tlyric": ""}
                return {"lyric": "", "tlyric": ""}
            if source == "kuwo":
                return [{"name": "南方姑娘", "artist": "赵雷", "id": "play-2",
                         "lyric_id": "lyrics-2"}]
            return []

        with patch.object(proxy, "_api_data", side_effect=api):
            result = proxy.lyrics("netease", "play-1", "南方姑娘", "赵雷")
        self.assertEqual(result, {
            "lyric": "[00:01.00]南方姑娘", "translation": "", "source": "kuwo",
        })
        self.assertIn(("search", "kuwo", {"name": "南方姑娘 赵雷", "count": 30, "pages": 1}), calls)
        self.assertIn(("lyric", "kuwo", {"id": "lyrics-2"}), calls)

    def test_unsupported_primary_lyrics_can_fall_back(self):
        def api(kind, source, deadline, **params):
            if kind == "lyric" and source == "spotify":
                return None
            if kind == "search" and source == "netease":
                return [{"name": "晴天", "artist": "周杰伦", "id": "186016"}]
            if kind == "lyric" and source == "netease":
                return {"lyric": "[00:01.00]故事的小黄花", "tlyric": ""}
            return []

        with patch.object(proxy, "_api_data", side_effect=api):
            result = proxy.lyrics("spotify", "track-id", "晴天", "周杰伦")
        self.assertEqual(result["source"], "netease")
        self.assertIn("故事的小黄花", result["lyric"])

    def test_cached_resolver_candidate_is_tried_before_search(self):
        proxy._recording_cache[("kuwo", "play-2")] = (
            proxy.time.monotonic() + 60,
            {"name": "南方姑娘", "artist": "赵雷", "lyric_id": "lyrics-2"},
        )
        calls = []

        def api(kind, source, deadline, **params):
            calls.append((kind, source, params))
            if source == "kuwo":
                return {"lyric": "[00:01.00]南方姑娘", "tlyric": ""}
            return {"lyric": "", "tlyric": ""}

        with patch.object(proxy, "_api_data", side_effect=api):
            result = proxy.lyrics("netease", "play-1", "南方姑娘", "赵雷")
        self.assertEqual(result["source"], "kuwo")
        self.assertEqual(calls, [
            ("lyric", "netease", {"id": "play-1"}),
            ("lyric", "kuwo", {"id": "lyrics-2"}),
        ])

    def test_translation_only_response_remains_usable(self):
        with patch.object(proxy, "_api_data", return_value={
                "lyric": "", "tlyric": "[00:01.00]Translated line",
        }):
            result = proxy.lyrics("netease", "translated")
        self.assertEqual(result, {
            "lyric": "[00:01.00]Translated line", "translation": "", "source": "netease",
        })

    def test_wrong_artist_or_version_is_never_used(self):
        lyric_candidates = []

        def api(kind, source, deadline, **params):
            if kind == "lyric":
                lyric_candidates.append((source, params["id"]))
                return {"lyric": "", "tlyric": ""}
            if source == "kuwo":
                return [
                    {"name": "童年", "artist": "其他歌手", "id": "wrong-artist"},
                    {"name": "童年 (Live)", "artist": "罗大佑", "id": "wrong-version"},
                ]
            return []

        with patch.object(proxy, "_api_data", side_effect=api):
            result = proxy.lyrics("netease", "missing", "童年", "罗大佑")
        self.assertEqual(result["lyric"], "")
        self.assertEqual(lyric_candidates, [("netease", "missing")])

    def test_limited_fallback_stops_immediately_with_retry_after(self):
        calls = []

        def api(kind, source, deadline, **params):
            calls.append((kind, source))
            if kind == "lyric":
                return {"lyric": "", "tlyric": ""}
            raise proxy.ResolveFailure("limited", 137)

        with patch.object(proxy, "_api_data", side_effect=api):
            with self.assertRaises(HTTPException) as error:
                proxy.lyrics("netease", "missing", "童年", "罗大佑")
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.detail, {"status": "limited", "retry_after": 137})
        self.assertEqual(error.exception.headers["Retry-After"], "137")
        self.assertEqual(calls, [("lyric", "netease"), ("search", "kuwo")])

    def test_negative_cache_requires_complete_cross_source_search(self):
        calls = []

        def api(kind, source, deadline, **params):
            calls.append((kind, source))
            return {"lyric": "", "tlyric": ""} if kind == "lyric" else []

        with patch.object(proxy, "_api_data", side_effect=api):
            first = proxy.lyrics("netease", "missing", "童年", "罗大佑")
            count = len(calls)
            second = proxy.lyrics("netease", "missing", "童年", "罗大佑")
        self.assertEqual(first, second)
        self.assertEqual(len(calls), count)
        self.assertIn(("request", "netease", "missing", "童年", "罗大佑"), proxy._lyric_cache)

    def test_temporary_search_failure_is_not_negative_cached(self):
        calls = []

        def api(kind, source, deadline, **params):
            calls.append((kind, source))
            if kind == "lyric":
                return {"lyric": "", "tlyric": ""}
            if source == "kuwo":
                raise proxy.ResolveFailure("temporary")
            return []

        with patch.object(proxy, "_api_data", side_effect=api):
            self.assertEqual(proxy.lyrics("netease", "missing", "童年", "罗大佑")["lyric"], "")
            first_count = len(calls)
            self.assertEqual(proxy.lyrics("netease", "missing", "童年", "罗大佑")["lyric"], "")
        self.assertGreater(len(calls), first_count)
        self.assertNotIn(("request", "netease", "missing", "童年", "罗大佑"), proxy._lyric_cache)

    def test_full_search_page_is_not_treated_as_exhaustive(self):
        def api(kind, source, deadline, **params):
            if kind == "lyric":
                return {"lyric": "", "tlyric": ""}
            return [{"name": f"Other {number}", "artist": "Other", "id": str(number)}
                    for number in range(30)]

        with patch.object(proxy, "_api_data", side_effect=api):
            proxy.lyrics("netease", "missing", "童年", "罗大佑")
        self.assertNotIn(("request", "netease", "missing", "童年", "罗大佑"), proxy._lyric_cache)


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

    async def test_query_identity_enables_cross_source_route_fallback(self):
        proxy._lyric_cache.clear()
        proxy._recording_cache.clear()
        calls = []

        def api(kind, source, deadline, **params):
            calls.append((kind, source, params))
            if kind == "lyric" and source == "kuwo":
                return {"lyric": "[00:01.00]南方姑娘", "tlyric": ""}
            if kind == "lyric":
                return {"lyric": "", "tlyric": ""}
            if source == "kuwo":
                return [{"name": "南方姑娘", "artist": "赵雷", "id": "lyrics-2"}]
            return []

        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        query = urllib.parse.urlencode({"title": "南方姑娘", "artist": "赵雷"}).encode()
        with patch.object(proxy, "_api_data", side_effect=api):
            await proxy.app({
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": "GET", "scheme": "http", "path": "/lyrics/netease/missing.json",
                "raw_path": b"/lyrics/netease/missing.json", "query_string": query, "root_path": "",
                "server": ("testserver", 80), "client": ("127.0.0.1", 1234), "headers": [],
            }, receive, send)
        status = next(message["status"] for message in messages if message["type"] == "http.response.start")
        body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["source"], "kuwo")
        self.assertIn(("search", "kuwo", {"name": "南方姑娘 赵雷", "count": 30, "pages": 1}), calls)


if __name__ == "__main__":
    unittest.main()
