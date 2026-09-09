"""Cancellation must release upstream work, not just hide its UI result."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from backend import music_sources
from test_frontend_contract import radio, request


class PlaybackLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_resolution_closes_proxy_connection(self):
        connected, closed = asyncio.Event(), asyncio.Event()

        async def proxy(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            connected.set()
            await reader.read()
            closed.set()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(proxy, "127.0.0.1", 0)
        async with server:
            port = server.sockets[0].getsockname()[1]
            task = asyncio.create_task(music_sources.resolve_song_async(
                f"http://127.0.0.1:{port}/songs.txt", {"title": "Song"}))
            await asyncio.wait_for(connected.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(closed.wait(), 2)

    async def test_browser_disconnect_cancels_resolution_handler(self):
        started, cancelled = asyncio.Event(), asyncio.Event()
        body_sent = False

        async def resolve(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": b'{"title":"Song"}', "more_body": False}
            if started.is_set():
                return {"type": "http.disconnect"}
            await asyncio.Event().wait()

        messages = []

        async def send(message):
            messages.append(message)

        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": "POST", "scheme": "http", "path": "/api/playback/resolve",
                 "raw_path": b"/api/playback/resolve", "query_string": b"", "root_path": "",
                 "server": ("test", 80), "client": ("127.0.0.1", 1000),
                 "headers": [(b"content-type", b"application/json")]}
        with patch.object(radio, "verify_song", side_effect=resolve):
            await asyncio.wait_for(radio.app(scope, receive, send), 2)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(messages[0]["status"], 499)

    async def test_recommendation_cancel_collects_child_searches(self):
        started, cancelled = asyncio.Event(), []

        async def resolve(song):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(song["rel"])

        candidates = [{"rel": str(i), "title": str(i)} for i in range(4)]
        with patch.object(radio, "verify_song", side_effect=resolve):
            task = asyncio.create_task(radio.verify_recommendations(candidates, candidates, {}, [], {}))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertCountEqual(cancelled, [song["rel"] for song in candidates])

    async def test_reason_audio_never_triggers_per_error_synthesis(self):
        with patch.object(radio, "tts_to_mp3", new=AsyncMock()) as synth:
            for reason in radio.ANNOUNCEMENT_LINES:
                status, _ = await request(f"/api/playback/announcement/{reason}.mp3")
                self.assertEqual(status, 503)
            status, _ = await request("/api/playback/announcement/unknown.mp3")
            self.assertEqual(status, 404)
            synth.assert_not_awaited()

    async def test_cooldown_manifest_only_exposes_ready_versioned_audio(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(radio, "VOICE_DIR", Path(directory)):
            radio._cooldown_path("mood1").write_bytes(b"ID3ready")
            with patch.object(radio, "tts_to_mp3", new=AsyncMock()) as synth:
                status, body = await request("/api/playback/cooldown/content.json")
                missing, _ = await request(f"/api/playback/cooldown/{radio.COOLDOWN_CONTENT_VERSION}/mood2.mp3")
                unknown, _ = await request(f"/api/playback/cooldown/{radio.COOLDOWN_CONTENT_VERSION}/unknown.mp3")
            manifest = json.loads(body)
            self.assertEqual(status, 200)
            self.assertEqual(manifest["version"], radio.COOLDOWN_CONTENT_VERSION)
            self.assertEqual([item["id"] for item in manifest["items"]], ["mood1"])
            self.assertIn(radio.COOLDOWN_CONTENT_VERSION, manifest["items"][0]["url"])
            self.assertEqual(missing, 503)
            self.assertEqual(unknown, 404)
            synth.assert_not_awaited()

    def test_cooldown_revision_changes_with_voice_or_text(self):
        changed_voice = dict(radio.MINIMAX_VOICE_SETTING, voice_id="another-voice")
        changed_lines = tuple([dict(radio.COOLDOWN_LINES[0], text="更新后的内容"), *radio.COOLDOWN_LINES[1:]])
        self.assertNotEqual(radio.COOLDOWN_CONTENT_VERSION,
                            radio._cooldown_revision(voice_setting=changed_voice))
        self.assertNotEqual(radio.COOLDOWN_CONTENT_VERSION,
                            radio._cooldown_revision(lines=changed_lines))

    def test_song_item_preserves_canonical_lyric_title(self):
        song = {"title": "周杰伦 - 晴天", "artist": "周杰伦", "rel": "s/netease/1.mp3"}
        with patch.object(radio, "identity", return_value={"title": "晴天", "artist": "周杰伦"}):
            item = radio.song_item(song)
        self.assertEqual(item["lyric_title"], "晴天")

    async def test_show_error_preserves_actual_cooldown(self):
        with patch.object(radio, "fetch_library", return_value=[{"title": "Song", "rel": "1"}]), \
                patch.object(radio, "verify_song", new=AsyncMock(return_value={"status": "limited"})), \
                patch.object(radio, "playback_availability", new=AsyncMock(return_value={"status": "limited", "retry_after": 640})):
            status, body = await request("/api/show", {})
        detail = json.loads(body)["detail"]
        self.assertEqual(status, 429)
        self.assertEqual(detail["status"], "limited")
        self.assertEqual(detail["retry_after"], 640)


if __name__ == "__main__":
    unittest.main()
