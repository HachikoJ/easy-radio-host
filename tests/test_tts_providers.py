"""Qwen TTS response parsing and provider failover."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("radio_tts", ROOT / "backend" / "app.py")
radio = importlib.util.module_from_spec(spec)
with patch.dict(os.environ, {"DATA_DIR": tempfile.mkdtemp(prefix="tingjian-tts-")}):
    spec.loader.exec_module(radio)


class QwenSynthesis(unittest.IsolatedAsyncioTestCase):
    async def test_inline_base64_audio_is_normalized_and_written(self):
        response = {"output": {"audio": {"data": base64.b64encode(b"WAV").decode()}}}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(radio, "post_provider", new=AsyncMock(return_value=json.dumps(response).encode())) as post, \
                patch.object(radio, "_download_audio", new=AsyncMock()) as download, \
                patch.object(radio, "normalize_speech", return_value=b"MP3") as normalize:
            target = Path(directory) / "voice.mp3"
            ok = await radio.qwen_synth("欢迎收听", target)
            self.assertTrue(ok)
            self.assertEqual(target.read_bytes(), b"MP3")
            request = post.await_args.args[0]
        download.assert_not_awaited()
        normalize.assert_called_once_with(b"WAV")
        body = json.loads(request.data.decode())
        self.assertTrue(request.full_url.endswith(
            "/services/aigc/multimodal-generation/generation"))
        self.assertEqual(body["model"], "qwen3-tts-instruct-flash")
        self.assertEqual(body["input"]["voice"], "Cherry")
        self.assertEqual(body["input"]["language_type"], "Chinese")
        self.assertIn("Authorization", request.headers)

    async def test_audio_url_is_downloaded_without_provider_auth(self):
        response = {"output": {"audio": {"url": "https://example.test/audio.wav"}}}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(radio, "post_provider", new=AsyncMock(return_value=json.dumps(response).encode())), \
                patch.object(radio, "_download_audio", new=AsyncMock(return_value=b"WAV")) as download, \
                patch.object(radio, "normalize_speech", return_value=b"MP3"):
            target = Path(directory) / "voice.mp3"
            ok = await radio.qwen_synth("欢迎收听", target)
            self.assertTrue(ok)
            self.assertEqual(target.read_bytes(), b"MP3")
        download.assert_awaited_once_with("https://example.test/audio.wav")


class TTSRouting(unittest.IsolatedAsyncioTestCase):
    async def test_qwen_failure_falls_back_to_minimax(self):
        with patch.object(radio, "DASHSCOPE_API_KEY", "qwen-key"), \
                patch.object(radio, "MINIMAX_KEY", "minimax-key"), \
                patch.object(radio, "qwen_synth", new=AsyncMock(return_value=False)) as qwen, \
                patch.object(radio, "minimax_synth", new=AsyncMock(return_value=True)) as minimax, \
                patch.object(radio.asyncio, "sleep", new=AsyncMock()):
            ok = await radio.tts_to_mp3("欢迎收听", "/tmp/voice.mp3")
        self.assertTrue(ok)
        self.assertEqual(qwen.await_count, 3)
        minimax.assert_awaited_once()

    async def test_edge_tts_is_last_resort_when_cloud_providers_fail(self):
        communicate = types.SimpleNamespace(save=AsyncMock())
        edge_tts = types.SimpleNamespace(Communicate=lambda text, voice: communicate)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(radio, "DASHSCOPE_API_KEY", "qwen-key"), \
                patch.object(radio, "MINIMAX_KEY", ""), \
                patch.object(radio, "qwen_synth", new=AsyncMock(return_value=False)), \
                patch.object(radio.asyncio, "sleep", new=AsyncMock()), \
                patch.dict(sys.modules, {"edge_tts": edge_tts}), \
                patch.object(radio, "normalize_speech", return_value=b"MP3"):
            target = Path(directory) / "voice.mp3"
            target.write_bytes(b"WAV")
            ok = await radio.tts_to_mp3("欢迎收听", target)
        self.assertTrue(ok)
        communicate.save.assert_awaited_once()

    def test_cooldown_revision_tracks_qwen_voice(self):
        self.assertNotEqual(radio.COOLDOWN_CONTENT_VERSION,
                            radio._cooldown_revision(qwen_voice="Serena"))

    def test_cached_announcements_and_fallback_lines_are_voice_versioned(self):
        notice = radio._announcement_path("limited").name
        fallback = radio._fallback_path(0).name
        self.assertIn(radio.COOLDOWN_CONTENT_VERSION, notice)
        self.assertIn(radio.COOLDOWN_CONTENT_VERSION, fallback)
        self.assertNotEqual(notice, "notice_v1_limited.mp3")
        self.assertNotEqual(fallback, "fb_0.mp3")


if __name__ == "__main__":
    unittest.main()
