"""Cross-channel resolution, identity and quota behaviour without external calls."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch
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
        proxy._api_cache.clear()
        proxy._api_times.clear()

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


class SharedQuota(unittest.TestCase):
    def setUp(self):
        proxy._api_cache.clear()
        proxy._api_times.clear()
        proxy._api_blocked_until = 0
        proxy._unsupported.clear()

    def test_search_lyrics_and_urls_share_quota_and_cache(self):
        with patch.object(proxy, "API_LIMIT", 3), patch.object(proxy.urllib.request, "urlopen", side_effect=lambda *a, **k: response({})) as fetch:
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


if __name__ == "__main__":
    unittest.main()
