"""Exercise the real ASGI app without calling AI, TTS, or music services."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("radio_contract", ROOT / "backend" / "app.py")
radio = importlib.util.module_from_spec(spec)
with patch.dict(os.environ, {"DATA_DIR": tempfile.mkdtemp(prefix="tingjian-contract-")}):
    spec.loader.exec_module(radio)


async def request(path, body=None, headers=()):
    payload = json.dumps(body).encode() if body is not None else b""
    messages = []

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        messages.append(message)

    await radio.app({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST" if body is not None else "GET", "scheme": "http",
        "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
        "server": ("testserver", 80), "client": ("127.0.0.1", 1234),
        "headers": [(b"content-type", b"application/json"), *headers],
    }, receive, send)
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    content = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, content


class FrontendContract(unittest.IsolatedAsyncioTestCase):
    async def test_static_assets_and_license(self):
        for path in ("/", "/app.js", "/listening.js", "/style.css", "/listening.css", "/recommendations.js", "/recommendations.css", "/assets/ThumbsDown.svg", "/lyrics.js", "/lyrics-data.js", "/lyrics.css", "/vendor/lrc-kit/lrc.js", "/vendor/lrc-kit/line-parser.js", "/vendor/lrc-kit/LICENSE", "/credits.html", "/assets/brand.svg", "/licenses/Claudio-MIT.txt"):
            status, content = await request(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(content, path)
        for path in ("/record-motion.js", "/record-scene.js", "/vendor/three/three.module.min.js", "/vendor/three/LICENSE"):
            status, content = await request(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(content, path)
        status, content = await request("/assets/demo-chimes.wav", headers=[(b"range", b"bytes=0-43")])
        self.assertEqual(status, 206)
        self.assertEqual(content[:4], b"RIFF")
        self.assertEqual(len(content), 44)

    async def test_show_keeps_theme_and_song_text_contract_when_tts_unavailable(self):
        library = [{"title": "Contract Song", "rel": "s/netease/123.mp3"}]
        with patch.object(radio, "fetch_library", return_value=library), \
             patch.object(radio, "llm_json", return_value={"show": [{"type": "talk", "text": "Contract narration"}, {"type": "song", "title": "Contract Song"}]}), \
             patch.object(radio, "tts_to_mp3", new=AsyncMock(return_value=False)), \
             patch.object(radio, "ensure_fallback_voice", new=AsyncMock(return_value=False)):
            status, content = await request("/api/show", {"exclude": [], "theme": "午后咖啡"})
        self.assertEqual(status, 200)
        result = json.loads(content)
        self.assertEqual(result["meta"]["theme"], "午后咖啡")
        self.assertEqual([item["kind"] for item in result["items"]], ["text", "song"])
        self.assertEqual(result["items"][0]["text"], "Contract narration")
        self.assertTrue(result["items"][1]["url"].endswith("s/netease/123.mp3"))

    async def test_intent_preserves_control_actions_without_inserting_a_song(self):
        with patch.object(radio, "fetch_library", return_value=[]), \
             patch.object(radio, "llm_json", return_value={"reply": "", "actions": [{"type": "pause"}, {"type": "set_auto", "on": False}]}):
            status, content = await request("/api/intent", {"message": "暂停", "exclude": [], "state": {"playing": True, "paused": False, "current": "Contract Song", "theme": "午后咖啡", "auto": True}})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content), {"items": [], "actions": [{"type": "pause"}, {"type": "set_auto", "on": False}]})


if __name__ == "__main__":
    unittest.main()
