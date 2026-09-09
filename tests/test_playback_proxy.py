"""Exercise expired CDN URLs, same-recording bitrate fallback, and bounded reads."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.parse

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("playback_proxy", ROOT / "musiclib" / "proxy_server.py")
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


def upstream(body, status=200):
    response = io.BytesIO(body)
    response.status = status
    return response


def api_result(url):
    return 200, json.dumps({"url": url}).encode()


class PlaybackProxy(unittest.TestCase):
    def setUp(self):
        proxy._play_cache.clear()
        proxy._api_cache.clear()
        proxy._api_times.clear()
        proxy._api_blocked_until = 0

    def test_broken_high_bitrates_fall_back_on_the_same_recording(self):
        sid = "bLnv0PqDX_qAlIqapc+Okw=="
        urls = [f"https://hk.stream.music.joox.com/{br}.mp3" for br in (320, 192, 128)]
        with patch.object(proxy, "http_get", side_effect=[api_result(url) for url in urls]) as api, \
                patch.object(proxy, "_media_available", side_effect=[False, False, True]) as probe:
            self.assertEqual(proxy._resolve_play_url("joox", sid), urls[2])
        self.assertEqual(probe.call_count, 3)
        queries = [urllib.parse.parse_qs(urllib.parse.urlsplit(call.args[0]).query)
                   for call in api.call_args_list]
        self.assertEqual([query["br"] for query in queries], [["320"], ["192"], ["128"]])
        self.assertTrue(all(query["id"] == [sid] and query["source"] == ["joox"] for query in queries))
        self.assertIn("%2B", api.call_args.args[0])

    def test_identical_failed_cdn_url_is_probed_only_once(self):
        with patch.object(proxy, "http_get", return_value=api_result("https://hk.stream.music.joox.com/gone")) as api, \
                patch.object(proxy, "_media_available", return_value=False) as probe:
            self.assertIsNone(proxy._resolve_play_url("joox", "one"))
        self.assertEqual(api.call_count, 3)
        probe.assert_called_once()
        self.assertFalse(proxy._play_cache)

    def test_success_cache_and_explicit_refresh(self):
        url = "https://hk.stream.music.joox.com/audio.mp3"
        with patch.object(proxy, "http_get", return_value=api_result(url)) as api, \
                patch.object(proxy, "_media_available", return_value=True), \
                patch.object(proxy.time, "monotonic", return_value=100):
            proxy._resolve_play_url("joox", "one")
            proxy._resolve_play_url("joox", "one")
            self.assertEqual(api.call_count, 1)
            proxy._resolve_play_url("joox", "one", refresh=True)
            self.assertEqual(api.call_count, 2)
        with patch.object(proxy, "http_get", return_value=(503, b"")) as api, \
                patch.object(proxy.time, "monotonic", return_value=146):
            self.assertIsNone(proxy._resolve_play_url("joox", "one"))
            self.assertEqual(api.call_count, 3)
        self.assertFalse(proxy._play_cache)

    def test_success_cache_is_bounded(self):
        with patch.object(proxy, "http_get", return_value=api_result("https://hk.stream.music.joox.com/a")), \
                patch.object(proxy, "_media_available", return_value=True):
            for index in range(proxy.PLAY_CACHE_SIZE + 1):
                proxy._resolve_play_url("joox", str(index))
        self.assertEqual(len(proxy._play_cache), proxy.PLAY_CACHE_SIZE)
        self.assertNotIn(("joox", "0"), proxy._play_cache)

    def test_exhausted_budget_stops_further_requests(self):
        with patch.object(proxy.time, "monotonic", side_effect=[0, 1, 2, 3, 21]), \
                patch.object(proxy, "http_get", return_value=(503, b"")) as api:
            self.assertIsNone(proxy._resolve_play_url("joox", "one"))
        api.assert_called_once()
        self.assertLessEqual(api.call_args.kwargs["timeout"], proxy.PLAY_TIMEOUT)

    def test_invalid_api_urls_are_never_probed(self):
        urls = [None, 123, "file:///etc/passwd", "http://127.0.0.1/a", "https://joox.com.evil.test/a",
                "https://user:secret@joox.com/a", "https://joox.com:8001/a", "https://joox.com:bad/a"]
        for url in urls:
            with self.subTest(url=url), patch.object(proxy, "http_get", return_value=api_result(url)), \
                    patch.object(proxy, "_media_available") as probe:
                self.assertIsNone(proxy._resolve_play_url("joox", "one"))
                probe.assert_not_called()

    def test_probe_requires_audio_header_and_reads_only_a_small_range(self):
        for body, valid in [(b"ID3" + b"\0" * 600, True), (b"\xff\xfb\x90\0", True),
                            (b"\0\0\0\x20ftypM4A ", True), (b"<Error>Not found</Error>", False),
                            (b"", False)]:
            response = upstream(body, status=206)
            opener = Mock()
            opener.open.return_value = response
            with self.subTest(valid=valid, header=body[:4]), \
                    patch.object(proxy.urllib.request, "build_opener", return_value=opener), \
                    patch.object(response, "read", wraps=response.read) as read:
                self.assertEqual(proxy._media_available("https://hk.stream.music.joox.com/a", 4), valid)
                read.assert_called_once_with(proxy.PLAY_PROBE_BYTES)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_header("Range"), "bytes=0-511")
            self.assertEqual(opener.open.call_args.kwargs["timeout"], 4)

    def test_cdn_404_is_a_failed_probe_without_reading_error_body(self):
        body = io.BytesIO(b"private upstream error")
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError("signed-url", 404, "missing", {}, body)
        with patch.object(proxy.urllib.request, "build_opener", return_value=opener):
            self.assertFalse(proxy._media_available("https://hk.stream.music.joox.com/a", 1))
        self.assertTrue(body.closed)

    def test_redirects_cannot_probe_unrelated_hosts(self):
        handler = proxy._MediaRedirectHandler()
        request = urllib.request.Request("https://hk.stream.music.joox.com/a")
        for target in ("http://127.0.0.1/", "https://unrelated.test/a"):
            with self.subTest(target=target), self.assertRaises(urllib.error.URLError):
                handler.redirect_request(request, None, 302, "Found", {}, target)

    def test_api_response_is_bounded(self):
        response = upstream(b"x" * (proxy.PLAY_MAX_BYTES + 1))
        with patch.object(proxy.urllib.request, "urlopen", return_value=response), \
                patch.object(response, "read", wraps=response.read) as read:
            self.assertEqual(proxy.http_get("https://api.test/"), (502, b""))
            read.assert_called_once_with(proxy.PLAY_MAX_BYTES + 1)

    def test_invalid_play_identifiers_never_reach_upstream(self):
        for source, sid in [("other", "1"), ("joox", "1&types=search"), ("joox", "%252F"),
                            ("joox", "a" * 201)]:
            with self.subTest(source=source, sid=sid), patch.object(proxy, "_resolve_play_url") as resolve:
                with self.assertRaises(HTTPException) as error:
                    proxy.play(source, sid)
                self.assertEqual(error.exception.status_code, 400)
                resolve.assert_not_called()

    def test_unavailable_is_generic_and_not_cacheable(self):
        with patch.object(proxy, "_resolve_play_url", return_value=None):
            result = proxy.play("joox", "one")
        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.headers["cache-control"], "no-store")
        self.assertEqual(result.body, b"audio temporarily unavailable")


class PlaybackRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_stream_forwards_single_range_and_closes_upstream(self):
        response = upstream(b"ID3" + b"x" * 600, 206)
        response.headers = {"Content-Type": "audio/mpeg", "Content-Length": "603", "Content-Range": "bytes 0-602/5000"}
        opener = Mock()
        opener.open.return_value = response
        with patch.object(proxy.urllib.request, "build_opener", return_value=opener):
            result = proxy._stream_audio("https://music.126.net/a", "bytes=0-602")
        self.assertEqual(opener.open.call_args.args[0].get_header("Range"), "bytes=0-602")
        self.assertEqual(result.status_code, 206)
        self.assertEqual(result.headers["content-range"], "bytes 0-602/5000")
        body = b"".join([block async for block in result.body_iterator])
        self.assertTrue(body.startswith(b"ID3"))
        self.assertTrue(response.closed)

    async def test_stream_disconnect_cleanup_and_range_validation(self):
        response = upstream(b"ID3", 206)
        response.headers = {"Content-Type": "audio/mpeg"}
        opener = Mock()
        opener.open.return_value = response
        with patch.object(proxy.urllib.request, "build_opener", return_value=opener):
            result = proxy._stream_audio("https://music.126.net/a", "bytes=0-")
        await result.background()
        self.assertTrue(response.closed)
        for value in ("bytes=0-1,5-6", "items=0-1", "bytes=-", "bytes=1-2\r\nInjected: 1"):
            with self.subTest(value=value), self.assertRaises(HTTPException) as error:
                proxy._stream_audio("https://music.126.net/a", value)
            self.assertEqual(error.exception.status_code, 416)

    async def test_stream_rejects_html_and_disallowed_urls(self):
        response = upstream(b"not audio", 200)
        response.headers = {"Content-Type": "text/html"}
        opener = Mock()
        opener.open.return_value = response
        with patch.object(proxy.urllib.request, "build_opener", return_value=opener), self.assertRaises(HTTPException):
            proxy._stream_audio("https://music.126.net/a", None)
        self.assertTrue(response.closed)
        with patch.object(proxy.urllib.request, "build_opener") as opener, self.assertRaises(HTTPException):
            proxy._stream_audio("http://127.0.0.1/private", None)
        opener.assert_not_called()

    async def test_original_double_encoded_and_legacy_routes_preserve_id_and_refresh(self):
        sid = "bLnv0PqDX_qAlIqapc+Okw=="
        for route_source, source, identifier in [("joox", "joox", sid), ("id", "netease", "123")]:
            for encodings in (1, 2):
                encoded = identifier
                for _ in range(encodings):
                    encoded = urllib.parse.quote(encoded, safe="")
                raw_path = f"/s/{route_source}/{encoded}.mp3"
                messages = []

                async def receive():
                    return {"type": "http.request", "body": b"", "more_body": False}

                async def send(message):
                    messages.append(message)

                with self.subTest(source=route_source, encodings=encodings), \
                        patch.object(proxy, "_resolve_play_url", return_value="https://hk.stream.music.joox.com/a") as resolve:
                    await proxy.app({
                        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                        "method": "GET", "scheme": "http", "path": urllib.parse.unquote(raw_path),
                        "raw_path": raw_path.encode(), "query_string": b"refresh=1", "root_path": "",
                        "server": ("testserver", 80), "client": ("127.0.0.1", 1234), "headers": [],
                    }, receive, send)
                    resolve.assert_called_once_with(source, identifier, refresh=True)
                    response = next(message for message in messages if message["type"] == "http.response.start")
                    self.assertEqual(response["status"], 307)
                    self.assertIn((b"cache-control", b"no-store"), response["headers"])


if __name__ == "__main__":
    unittest.main()
