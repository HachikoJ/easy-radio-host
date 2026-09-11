"""Local sherpa-onnx TTS service: WAV encoding and client integration."""
import importlib.util
import io
import os
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tts import engine


ROOT = Path(__file__).resolve().parents[1]


class _FakeResponse:
    def __init__(self, payload=b"", error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    async def read(self):
        return self.payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    def __init__(self, response, calls, **kwargs):
        self.response = response
        self.calls = calls
        self.kwargs = kwargs

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs, self.kwargs))
        return self.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def load_radio_app():
    spec = importlib.util.spec_from_file_location("radio_local_tts", ROOT / "backend" / "app.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, {"DATA_DIR": tempfile.mkdtemp(prefix="tingjian-local-tts-")}):
        spec.loader.exec_module(module)
    return module


class WavEncoding(unittest.TestCase):
    def test_float_samples_become_pcm16_mono_wav(self):
        audio = types.SimpleNamespace(samples=[0.0, 0.5, -0.5, 1.0, -1.0], sample_rate=44100)
        payload = engine.encode_wav(audio)
        with wave.open(io.BytesIO(payload), "rb") as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getframerate(), 44100)
            self.assertEqual(wav.getnframes(), 5)
            frames = wav.readframes(5)
        self.assertEqual(
            list(int.from_bytes(frames[i:i + 2], "little", signed=True) for i in range(0, 10, 2)),
            [0, 16383, -16383, 32767, -32767],
        )

    def test_out_of_range_samples_are_clipped(self):
        audio = types.SimpleNamespace(samples=[2.0, -2.0], sample_rate=8000)
        payload = engine.encode_wav(audio)
        with wave.open(io.BytesIO(payload), "rb") as wav:
            frames = wav.readframes(2)
        self.assertEqual(
            list(int.from_bytes(frames[i:i + 2], "little", signed=True) for i in range(0, 4, 2)),
            [32767, -32768],
        )

    def test_missing_model_files_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(engine, "MODEL_PATH", root / "model.onnx"), \
                    patch.object(engine, "LEXICON_PATH", root / "lexicon.txt"), \
                    patch.object(engine, "TOKENS_PATH", root / "tokens.txt"):
                self.assertEqual(len(engine.missing_model_files()), 3)
                (root / "model.onnx").write_bytes(b"onnx")
                self.assertEqual(engine.missing_model_files(), [str(root / "lexicon.txt"),
                                                                 str(root / "tokens.txt")])

    def test_engine_load_rejects_missing_files_before_importing_runtime(self):
        with patch.object(engine, "MODEL_PATH", Path("/nonexistent/model.onnx")), \
                patch.object(engine, "LEXICON_PATH", Path("/nonexistent/lexicon.txt")), \
                patch.object(engine, "TOKENS_PATH", Path("/nonexistent/tokens.txt")):
            with self.assertRaises(FileNotFoundError):
                engine.load_engine()


class LocalTtsServer(unittest.TestCase):
    def test_server_module_exposes_health_and_synthesize(self):
        if importlib.util.find_spec("fastapi") is None:
            self.skipTest("fastapi is only installed in the service virtualenv")
        from tts import server

        paths = {route.path for route in server.app.routes}
        self.assertIn("/health", paths)
        self.assertIn("/synthesize", paths)
        self.assertIsNone(getattr(server.app.state, "engine", None))


class LocalSynthClient(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.radio = load_radio_app()

    async def test_posts_text_and_speed_then_writes_normalized_audio(self):
        calls = []
        response = _FakeResponse(b"PCM16 WAV")
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(self.radio, "LOCAL_TTS_URL", "http://127.0.0.1:8101"), \
                patch.object(self.radio, "LOCAL_TTS_SPEED", 1.1), \
                patch.object(self.radio.aiohttp, "ClientSession",
                             lambda **kwargs: _FakeSession(response, calls, **kwargs)), \
                patch.object(self.radio, "normalize_speech", return_value=b"MP3") as normalize:
            target = Path(directory) / "voice.mp3"
            self.assertTrue(await self.radio.local_synth("欢迎收听", target))
            self.assertEqual(target.read_bytes(), b"MP3")
        normalize.assert_called_once_with(b"PCM16 WAV")
        url, request, session_kwargs = calls[0]
        self.assertEqual(url, "http://127.0.0.1:8101/synthesize")
        self.assertEqual(request["json"], {"text": "欢迎收听", "speed": 1.1})
        self.assertEqual(session_kwargs["timeout"].total, self.radio.LOCAL_TTS_TIMEOUT)

    async def test_disabled_local_tts_never_opens_a_session(self):
        with patch.object(self.radio, "LOCAL_TTS_URL", ""), \
                patch.object(self.radio.aiohttp, "ClientSession") as session:
            self.assertFalse(await self.radio.local_synth("欢迎收听", "/tmp/voice.mp3"))
        session.assert_not_called()

    async def test_http_error_returns_false_without_writing(self):
        calls = []
        response = _FakeResponse(b"", error=RuntimeError("503 model is not ready"))
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(self.radio, "LOCAL_TTS_URL", "http://127.0.0.1:8101"), \
                patch.object(self.radio.aiohttp, "ClientSession",
                             lambda **kwargs: _FakeSession(response, calls, **kwargs)), \
                patch.object(self.radio, "normalize_speech", new=AsyncMock()) as normalize:
            target = Path(directory) / "voice.mp3"
            self.assertFalse(await self.radio.local_synth("欢迎收听", target))
            self.assertFalse(target.exists())
        normalize.assert_not_called()

    async def test_empty_audio_body_returns_false(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(self.radio, "LOCAL_TTS_URL", "http://127.0.0.1:8101"), \
                patch.object(self.radio.aiohttp, "ClientSession",
                             lambda **kwargs: _FakeSession(_FakeResponse(b""), calls, **kwargs)):
            target = Path(directory) / "voice.mp3"
            self.assertFalse(await self.radio.local_synth("欢迎收听", target))
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
