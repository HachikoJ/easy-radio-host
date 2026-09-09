"""Cross-channel resolution, identity and quota behaviour without external calls."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
import importlib.util
import io
import json
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
import urllib.error
import urllib.parse

from musiclib.matching import artist_match, recording_match, SOURCES

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("music_resolver", ROOT / "musiclib" / "proxy_server.py")
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


def response(data, status=200):
    result = io.BytesIO(json.dumps(data).encode())
    result.status = status
    result.headers = {"Content-Type": "audio/mpeg"}
    return result


class RecordingIdentity(unittest.TestCase):
    def test_traditional_artist_and_string_artist(self):
        self.assertTrue(recording_match("晴天", "周杰伦", {"name": "晴天", "artist": "周杰倫"}))
        self.assertFalse(artist_match("周杰伦", ["周杰伦翻唱合集"]))
        self.assertFalse(artist_match("林俊杰", "林俊杰 / 其他歌手"))

    def test_title_is_exact_and_version_does_not_change(self):
        self.assertFalse(recording_match("童年", "罗大佑", {"name": "童年 (Live)", "artist": ["罗大佑"]}))
        self.assertFalse(recording_match("童年", "罗大佑", {"name": "童年的回忆", "artist": ["罗大佑"]}))
        self.assertFalse(recording_match("童年", "罗大佑", {"name": "童年", "artist": ["罗大佑"], "note": "现场版"}))
        self.assertTrue(recording_match("童年 (现场版)", "罗大佑", {"name": "童年 (Live)", "artist": ["罗大佑"]}))
        self.assertFalse(recording_match("Song", "Artist", {"name": "Song (Another Song)", "artist": ["Artist"]}))

    def test_unspecified_artist_still_excludes_covers(self):
        self.assertFalse(recording_match("晴天", "", {"name": "晴天 (Cover 周杰伦)", "artist": ["Someone"]}))
        self.assertFalse(recording_match("晴天", "", {"name": "晴天", "artist": []}))


class ResolveTracks(unittest.TestCase):
    def setUp(self):
        proxy._play_cache.clear()
        proxy._recording_cache.clear()
        proxy._api_cache.clear()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        quota = patch.object(proxy, "_quota", proxy.RollingQuota(Path(directory.name) / "quota.sqlite3"))
        quota.start()
        self.addCleanup(quota.stop)

    def test_failed_candidate_continues_across_channels_with_real_probe(self):
        probes = []
        def api(url, **kwargs):
            args = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            source, kind = args["source"][0], args["types"][0]
            if kind == "search":
                return 200, json.dumps([{"name": "童年", "artist": "罗大佑", "id": source,
                                          "lyric_id": "lyrics-" + source}]).encode()
            return 200, json.dumps({"url": "https://music.126.net/" + source}).encode()
        def probe(url, timeout):
            probes.append(url)
            return url.endswith("kuwo")
        with patch.object(proxy, "http_get", side_effect=api), patch.object(proxy, "_media_available", side_effect=probe):
            result = proxy.resolve(proxy.ResolveRequest(title="童年", artist="罗大佑"))
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["track"]["source"], "kuwo")
        self.assertEqual(result["track"]["lyric_id"], "lyrics-kuwo")
        self.assertEqual(result["searched"], ["netease", "kuwo"])
        self.assertIn(("kuwo", "kuwo"), proxy._play_cache)
        self.assertEqual(len(probes), 2)
        self.assertNotIn("url", result["track"])

    def test_unavailable_only_after_all_sources_and_queries_exhausted(self):
        with patch.object(proxy, "_api_data", return_value=[]) as fetch:
            result = proxy.resolve(proxy.ResolveRequest(title="Missing", artist="Artist"))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(set(result["searched"]), set(SOURCES))
        self.assertTrue(any(call.kwargs["name"] == "Missing" for call in fetch.call_args_list))

    def test_quota_and_network_failure_are_not_absence(self):
        for state in ("limited", "temporary"):
            with self.subTest(state=state), patch.object(proxy, "_api_data", side_effect=proxy.ResolveFailure(state, 42)) as fetch:
                result = proxy.resolve(proxy.ResolveRequest(title="Missing", artist="Artist"))
            self.assertEqual(result["status"], state)
            if state == "limited":
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(result["retry_after"], 42)

    def test_old_playlist_live_id_is_not_used_for_studio_request(self):
        row = {"title": "童年", "artist": "罗大佑", "source": "joox", "sid": "old", "note": "现场版"}
        with patch.object(proxy, "load_playlist", return_value=[row]), \
                patch.object(proxy, "_api_data", return_value=[]), patch.object(proxy, "_resolve_play_url") as play:
            result = proxy.resolve(proxy.ResolveRequest(title="童年", artist="罗大佑", source="joox", id="old"))
        self.assertEqual(result["status"], "unavailable")
        play.assert_not_called()

    def test_old_playlist_actual_artist_mismatch_and_unknown_identity_require_search(self):
        for note in ("一生所愛 - 盧冠廷,莫文蔚", "", "曾可播放", "別的歌 - 盧冠廷"):
            row = {"title": "一生所爱", "artist": "卢冠廷", "source": "joox", "sid": "old", "note": note}
            with self.subTest(note=note), patch.object(proxy, "load_playlist", return_value=[row]), \
                    patch.object(proxy, "_api_data", return_value=[]) as search, patch.object(proxy, "_resolve_play_url") as play:
                result = proxy.resolve(proxy.ResolveRequest(title="一生所爱", artist="卢冠廷", source="joox", id="old"))
            self.assertEqual(result["status"], "unavailable")
            self.assertTrue(search.called)
            play.assert_not_called()

    def test_old_playlist_matching_actual_identity_can_use_fast_probe(self):
        row = {"title": "浮夸", "artist": "陈奕迅", "source": "joox", "sid": "old", "note": "浮誇 - 陳奕迅"}
        with patch.object(proxy, "load_playlist", return_value=[row]), patch.object(proxy, "_api_data") as search, \
                patch.object(proxy, "_resolve_play_url", return_value="audio"):
            result = proxy.resolve(proxy.ResolveRequest(title="浮夸", artist="陈奕迅", source="joox", id="old"))
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["track"]["title"], "浮誇")
        self.assertEqual(result["track"]["artist"], "陳奕迅")
        search.assert_not_called()

    def test_excluded_recording_is_not_retried(self):
        with patch.object(proxy, "_api_data", return_value=[{"name": "Song", "artist": "Artist", "id": "one"}]), \
                patch.object(proxy, "_resolve_play_url", return_value="https://music.126.net/a") as play:
            result = proxy.resolve(proxy.ResolveRequest(title="Song", artist="Artist", exclude=[{"source": "netease", "id": "one"}]))
        self.assertEqual(result["track"]["source"], "kuwo")
        play.assert_called_once()

    def test_second_page_is_searched_when_first_page_full(self):
        fillers = [{"name": "Other", "artist": "Artist", "id": str(n)} for n in range(30)]
        def data(kind, source, deadline, **kwargs):
            if source != "netease":
                return []
            if kwargs["pages"] == 1:
                return fillers
            return [{"name": "Song", "artist": "Artist", "id": "match"}]
        with patch.object(proxy, "_api_data", side_effect=data), patch.object(proxy, "_resolve_play_url", return_value="audio"):
            result = proxy.resolve(proxy.ResolveRequest(title="Song", artist="Artist"))
        self.assertEqual(result["track"]["id"], "match")

    def test_temporary_candidate_failure_does_not_hide_next_same_source_candidate(self):
        rows = [{"name": "Song", "artist": "Artist", "id": "timed-out"},
                {"name": "Song", "artist": "Artist", "id": "playable"}]
        with patch.object(proxy, "_api_data", return_value=rows), \
                patch.object(proxy, "_resolve_play_url", side_effect=[proxy.ResolveFailure("temporary"), "audio"]):
            result = proxy.resolve(proxy.ResolveRequest(title="Song", artist="Artist"))
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["track"]["id"], "playable")
        self.assertEqual(result["searched"], ["netease"])

    def test_verified_identity_and_cdn_url_remain_usable_while_api_is_limited(self):
        row = {"name": "Song", "artist": "Artist", "id": "known"}
        with patch.object(proxy, "_api_data", return_value=[row]), \
                patch.object(proxy, "_resolve_play_url", return_value="audio"):
            first = proxy.resolve(proxy.ResolveRequest(title="Song", artist="Artist"))
        self.assertEqual(first["status"], "available")
        proxy._quota.inspect(cooldown=300)
        url = "https://music.126.net/known"
        proxy._play_cache[("netease", "known")] = (0, url, proxy.time.monotonic() + 300)
        with patch.object(proxy, "_media_available", return_value=True) as probe, \
                patch.object(proxy.urllib.request, "urlopen") as api:
            second = proxy.resolve(proxy.ResolveRequest(title="Song", artist="Artist"))
        self.assertEqual(second["track"]["id"], "known")
        probe.assert_called_once()
        api.assert_not_called()


class SharedQuota(unittest.TestCase):
    def setUp(self):
        proxy._api_cache.clear()
        proxy._emergency_cooldown_until = 0
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        quota = patch.object(proxy, "_quota", proxy.RollingQuota(Path(directory.name) / "quota.sqlite3"))
        quota.start()
        self.addCleanup(quota.stop)
        proxy._unsupported.clear()

    def test_search_lyrics_and_urls_share_quota_and_cache(self):
        with patch.object(proxy._quota, "limit", 3), patch.object(proxy.urllib.request, "urlopen", side_effect=lambda *a, **k: response({})) as fetch:
            for kind in ("search", "lyric", "url"):
                url = proxy.API + "?types=" + kind + "&source=netease"
                self.assertEqual(proxy.http_get(url)[0], 200)
                self.assertEqual(proxy.http_get(url)[0], 200)
            self.assertEqual(proxy.http_get(proxy.API + "?types=search&source=kuwo")[0], 429)
        self.assertEqual(fetch.call_count, 3)

    def test_429_is_not_retried_and_blocks_other_sources(self):
        error = urllib.error.HTTPError("url", 429, "limit", {"Retry-After": "30"}, io.BytesIO())
        with patch.object(proxy.urllib.request, "urlopen", side_effect=error) as fetch:
            self.assertEqual(proxy.http_get(proxy.API + "?source=netease", tries=3)[0], 429)
            self.assertEqual(proxy.http_get(proxy.API + "?source=kuwo")[0], 429)
        self.assertEqual(fetch.call_count, 1)

    def test_exact_45_per_rolling_300_seconds_persists_across_instances(self):
        with patch("musiclib.quota.time.time", return_value=1000), \
                patch.object(proxy.urllib.request, "urlopen", side_effect=lambda *a, **k: response({})) as fetch:
            for index in range(45):
                self.assertEqual(proxy.http_get(proxy.API + "?types=search&id=" + str(index))[0], 200)
            self.assertEqual(proxy.http_get(proxy.API + "?types=url&id=46")[0], 429)
            self.assertEqual(fetch.call_count, 45)
            self.assertEqual(proxy.availability(), {"status": "limited", "remaining": 0, "retry_after": 300})
            restarted = proxy.RollingQuota(proxy._quota.path)
            self.assertEqual(restarted.inspect()["status"], "limited")
        with patch("musiclib.quota.time.time", return_value=1299):
            self.assertEqual(restarted.inspect()["retry_after"], 1)
        with patch("musiclib.quota.time.time", return_value=1300):
            self.assertEqual(restarted.inspect(), {"status": "ready", "remaining": 45, "retry_after": 0})

    def test_long_retry_after_is_persisted_without_truncation(self):
        error = urllib.error.HTTPError("url", 429, "limit", {"Retry-After": "900"}, io.BytesIO())
        with patch("musiclib.quota.time.time", return_value=1000), \
                patch.object(proxy.urllib.request, "urlopen", side_effect=error):
            self.assertEqual(proxy.http_get(proxy.API + "?source=netease")[0], 429)
            self.assertEqual(proxy._retry_after(), 900)
        with patch("musiclib.quota.time.time", return_value=1301):
            restarted = proxy.RollingQuota(proxy._quota.path)
            self.assertEqual(restarted.inspect()["retry_after"], 599)
        with patch.object(proxy.time, "time", return_value=0):
            self.assertEqual(proxy._upstream_retry("Thu, 01 Jan 1970 00:15:00 GMT"), 900)

    def test_rolling_window_frees_only_expired_requests(self):
        with patch("musiclib.quota.time.time", return_value=1000):
            for _ in range(10):
                proxy._quota.inspect(reserve=True)
        with patch("musiclib.quota.time.time", return_value=1100):
            for _ in range(35):
                proxy._quota.inspect(reserve=True)
        with patch("musiclib.quota.time.time", return_value=1300):
            self.assertEqual(proxy._quota.inspect()["remaining"], 10)
        with patch("musiclib.quota.time.time", return_value=1200):
            self.assertEqual(proxy._quota.inspect()["remaining"], 10)

    def test_storage_failure_never_issues_an_uncounted_request(self):
        with patch.object(proxy._quota, "inspect", side_effect=proxy.sqlite3.OperationalError("locked")), \
                patch.object(proxy.urllib.request, "urlopen") as fetch:
            self.assertEqual(proxy.http_get(proxy.API + "?types=search")[0], 429)
        fetch.assert_not_called()

    def test_failed_cooldown_write_still_blocks_requests_after_storage_recovers(self):
        with patch.object(proxy._quota, "inspect", side_effect=proxy.sqlite3.OperationalError("locked")):
            proxy._quota_state(cooldown=900)
        with patch.object(proxy.urllib.request, "urlopen") as fetch:
            self.assertEqual(proxy.http_get(proxy.API + "?types=search")[0], 429)
        fetch.assert_not_called()

    def test_concurrent_independent_process_budgets_never_grant_over_45(self):
        def reserve(_):
            return proxy.RollingQuota(proxy._quota.path).inspect(reserve=True)["status"]
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(reserve, range(60)))
        self.assertEqual(results.count("ready"), 45)
        self.assertEqual(results.count("limited"), 15)

    def test_cancelled_resolution_does_not_issue_the_next_api_request(self):
        cancelled = Event()
        def fetch(*args, **kwargs):
            cancelled.set()
            return 200, b"[]"
        token = proxy._request_cancel.set(cancelled)
        try:
            with patch.object(proxy, "http_get", side_effect=fetch) as request:
                result = proxy.resolve(proxy.ResolveRequest(title="Missing"))
            self.assertEqual(result["status"], "cancelled")
            self.assertEqual(request.call_count, 1)
        finally:
            proxy._request_cancel.reset(token)

    def test_cancelled_waiter_does_not_cancel_shared_owner(self):
        entered, release, cancelled = Event(), Event(), Event()
        def upstream(*args, **kwargs):
            entered.set()
            release.wait(2)
            return response([])
        def waiter():
            token = proxy._request_cancel.set(cancelled)
            try:
                return proxy.http_get(proxy.API + "?types=search&source=netease")
            finally:
                proxy._request_cancel.reset(token)
        with patch.object(proxy.urllib.request, "urlopen", side_effect=upstream) as fetch, ThreadPoolExecutor(2) as pool:
            owner = pool.submit(proxy.http_get, proxy.API + "?types=search&source=netease")
            self.assertTrue(entered.wait(1))
            pending = pool.submit(waiter)
            cancelled.set()
            with self.assertRaises(proxy.ResolveFailure) as failure:
                pending.result(timeout=1)
            self.assertEqual(failure.exception.status, "cancelled")
            release.set()
            self.assertEqual(owner.result()[0], 200)
        self.assertEqual(fetch.call_count, 1)

    def test_unsupported_channel_cools_down(self):
        raw = io.BytesIO(b"Value of source is not supported")
        raw.status = 200
        with patch.object(proxy.urllib.request, "urlopen", return_value=raw) as fetch:
            self.assertEqual(proxy.http_get(proxy.API + "?types=search&source=tencent")[0], 400)
            self.assertEqual(proxy.http_get(proxy.API + "?types=url&source=tencent")[0], 400)
        self.assertEqual(fetch.call_count, 1)

    def test_simultaneous_identical_searches_share_one_request(self):
        entered, release = Event(), Event()
        def upstream(*args, **kwargs):
            entered.set()
            release.wait(2)
            return response([])
        with patch.object(proxy.urllib.request, "urlopen", side_effect=upstream) as fetch, ThreadPoolExecutor(2) as pool:
            first = pool.submit(proxy.http_get, proxy.API + "?types=search&source=netease")
            self.assertTrue(entered.wait(1))
            second = pool.submit(proxy.http_get, proxy.API + "?types=search&source=netease")
            release.set()
            self.assertEqual(first.result(), second.result())
        self.assertEqual(fetch.call_count, 1)


class CancelledRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_disconnected_request_cancels_worker_before_next_search(self):
        entered, release, finished = Event(), Event(), Event()
        def upstream(*args, **kwargs):
            entered.set()
            release.wait(2)
            return 200, b"[]"
        def work():
            try:
                return proxy.resolve(proxy.ResolveRequest(title="Missing"))
            finally:
                finished.set()
        request = Mock(is_disconnected=AsyncMock(return_value=True))
        with patch.object(proxy, "http_get", side_effect=upstream) as fetch:
            task = asyncio.create_task(proxy._run_for_request(request, work))
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            response = await task
            self.assertEqual(response.status_code, 499)
            release.set()
            self.assertTrue(await asyncio.to_thread(finished.wait, 1))
            self.assertEqual(fetch.call_count, 1)

    async def test_disconnect_closes_late_stream_connection(self):
        entered, release = Event(), Event()
        audio = io.BytesIO(b"ID3audio")
        audio.status = 200
        audio.headers = {"Content-Type": "audio/mpeg"}
        def open_audio(*args, **kwargs):
            entered.set()
            release.wait(2)
            return audio
        opener = Mock(open=Mock(side_effect=open_audio))
        request = Mock(is_disconnected=AsyncMock(return_value=True))
        with patch.object(proxy.urllib.request, "build_opener", return_value=opener):
            task = asyncio.create_task(proxy._run_for_request(
                request, lambda: proxy._stream_audio("https://music.126.net/a", None)))
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            self.assertEqual((await task).status_code, 499)
            release.set()
            for _ in range(100):
                if audio.closed:
                    break
                await asyncio.sleep(0.01)
        self.assertTrue(audio.closed)


if __name__ == "__main__":
    unittest.main()
