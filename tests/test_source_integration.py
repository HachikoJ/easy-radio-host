"""Verified admission and explicit request failures across the real API routes."""
import io
import json
import unittest
from unittest.mock import AsyncMock, patch

from backend import music_sources as sources
from test_frontend_contract import radio, request, verified


class SourceClient(unittest.TestCase):
    def test_multiple_artists_keep_title_identity_after_recovery(self):
        result = sources.identity({"title": "A、B - Song", "artist": "A / B"})
        self.assertEqual(result["title"], "Song")
        self.assertEqual(sources.artist_key(result["artist"]), {"a", "b"})

    def test_catalog_requires_exact_title_and_artist(self):
        catalog = [{"title": "周杰伦 - 晴天", "rel": "s/netease/1.mp3"},
                   {"title": "其他歌手 - 晴天", "rel": "s/netease/2.mp3"}]
        self.assertIsNone(sources.catalog_match(catalog, "晴"))
        self.assertIsNone(sources.catalog_match(catalog, "晴天"))
        self.assertEqual(sources.catalog_match(catalog, "晴天", "周杰倫"), catalog[0])
        self.assertIsNone(sources.catalog_match(catalog, "周杰伦 - 晴天", "其他歌手"))

    def test_available_track_never_uses_an_arbitrary_upstream_rel(self):
        payload = {"status": "available", "track": {"title": "童年", "artist": "罗大佑",
                   "source": "netease", "id": "109530", "lyric_id": "456", "rel": "https://evil.test/"}}
        with patch.object(sources.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as fetch:
            result = sources.resolve_song("http://127.0.0.1:8001/songs.txt", {"title": "童年", "artist": "罗大佑"})
        self.assertEqual(result["song"]["rel"], "s/netease/109530.mp3")
        self.assertEqual(result["song"]["lyric_id"], "456")
        self.assertEqual(fetch.call_args.args[0].full_url, "http://127.0.0.1:8001/resolve")

    def test_incomplete_or_malformed_response_is_not_a_missing_song(self):
        for payload in ({"status": "limited"}, {"status": "temporary"}, {}, {"status": "available", "track": {}}):
            with self.subTest(payload=payload), patch.object(sources.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
                result = sources.resolve_song("http://local/songs.txt", {"title": "童年"})
                self.assertIn(result["status"], {"limited", "temporary"})
                self.assertNotIn("song", result)


class SourceAPI(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for name, value in (("tts_to_mp3", AsyncMock(return_value=False)),
                            ("ensure_fallback_voice", AsyncMock(return_value=False))):
            patcher = patch.object(radio, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_recommendations_replace_unavailable_candidates_before_narration(self):
        catalog = [{"title": f"Artist {i} - Song {i}", "rel": f"s/netease/{i}.mp3"} for i in range(5)]
        async def check(song, exclude=()):
            return {"status": "unavailable"} if song == catalog[0] else await verified(song)
        selections = [(catalog[:4], {"count": 4}), ([catalog[4]], {"count": 1})]
        with patch.object(radio, "fetch_library", return_value=catalog), \
                patch.object(radio, "select_songs", side_effect=selections), \
                patch.object(radio, "verify_song", side_effect=check), \
                patch.object(radio, "llm_json_async", return_value={"introductions": ["Next"] * 4}) as narrator:
            status, body = await request("/api/show", {})
        result = json.loads(body)
        self.assertEqual(status, 200)
        titles = [item["title"] for item in result["items"] if item["kind"] == "song"]
        self.assertEqual(titles, [song["title"] for song in catalog[1:]])
        self.assertNotIn(catalog[0]["title"], narrator.call_args.args[0])
        self.assertTrue(result["meta"]["recommendation"]["availability_checked"])

    async def test_no_available_recommendations_are_not_queued(self):
        for reason, expected in (("unavailable", 422), ("limited", 429), ("temporary", 503)):
            with self.subTest(reason=reason), patch.object(radio, "fetch_library", return_value=[{"title": "Artist - Missing", "rel": "s/netease/1.mp3"}]), \
                    patch.object(radio, "verify_song", new=AsyncMock(return_value={"status": reason})), \
                    patch.object(radio, "llm_json_async") as llm:
                status, body = await request("/api/show", {})
                self.assertEqual(status, expected)
                self.assertNotIn("items", json.loads(body))
                llm.assert_not_called()

    async def test_requested_missing_song_has_notice_then_next_only_after_exhaustion(self):
        for reason in ("unavailable", "limited", "temporary"):
            with self.subTest(reason=reason), patch.object(radio, "fetch_library", return_value=[]), \
                    patch.object(radio, "llm_json_async", return_value={"reply": "马上为你播放", "actions": [{"type": "play_song", "title": "不存在", "artist": "指定歌手"}]}), \
                    patch.object(radio, "verify_song", new=AsyncMock(return_value={"status": reason})):
                status, body = await request("/api/intent", {"message": "听指定歌手的不存在"})
            result = json.loads(body)
            self.assertEqual(status, 200)
            self.assertEqual(result["items"], [])
            self.assertIn("不存在", result["notice"])
            self.assertEqual(result["availability"], reason)
            self.assertEqual(result["actions"], [{"type": "next"}])
            self.assertNotIn("马上为你播放", body.decode())

    async def test_song_outside_catalog_can_be_requested_when_llm_fails(self):
        matched = {"title": "罗大佑 - 童年", "artist": "罗大佑", "source": "netease", "id": "109530",
                   "lyric_id": "999", "rel": "s/netease/109530.mp3", "_verified": True}
        with patch.object(radio, "fetch_library", return_value=[]), \
                patch.object(radio, "llm_json_async", side_effect=TimeoutError()), \
                patch.object(radio, "verify_song", new=AsyncMock(return_value={"status": "available", "song": matched})) as resolve:
            status, body = await request("/api/intent", {"message": "请播放《罗大佑 - 童年》"})
        self.assertEqual(status, 200)
        item = next(row for row in json.loads(body)["items"] if row["kind"] == "song")
        self.assertTrue(item["requested"])
        self.assertEqual(item["lyric_id"], "999")
        self.assertTrue(item["url"].endswith("?stream=1"))
        resolve.assert_awaited_once()

    async def test_recovery_preserves_failed_identifiers_and_reports_quota(self):
        with patch.object(radio, "verify_song", new=AsyncMock(return_value={"status": "limited", "retry_after": 30})) as resolve:
            status, body = await request("/api/playback/resolve", {"title": "罗大佑 - 童年", "source": "joox", "id": "old", "exclude": [{"source": "joox", "id": "old"}]})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "limited")
        self.assertEqual(data["retry_after"], 30)
        self.assertEqual(resolve.call_args.args[1], [{"source": "joox", "id": "old"}])
        self.assertNotIn("item", data)


if __name__ == "__main__":
    unittest.main()
