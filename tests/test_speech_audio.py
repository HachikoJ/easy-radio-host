"""Generated speech stays playable when optional loudness processing fails."""
from pathlib import Path
import json
import subprocess
import unittest
from unittest.mock import patch

from backend import speech_audio


class SpeechAudioTests(unittest.TestCase):
    def test_normalized_audio_replaces_input_only_after_success(self):
        original = b"original narration"
        normalized = b"normalized MP3" * 20

        def process(command, **kwargs):
            self.assertEqual(kwargs["input"], original)
            self.assertLessEqual(kwargs["timeout"], 20)
            if command[-1] == "-":
                stats = {"input_i": "-24", "input_tp": "-9", "input_lra": "2",
                         "input_thresh": "-34", "target_offset": "0"}
                report = ("[Parsed_loudnorm_0 @ test]\n" + json.dumps(stats) +
                          "\n[out#0/null @ test] trailing output\n").encode()
                return subprocess.CompletedProcess(command, 0, stderr=report)
            Path(command[-1]).write_bytes(normalized)
            return subprocess.CompletedProcess(command, 0)

        with patch.object(speech_audio.shutil, "which", return_value="/usr/bin/ffmpeg"), \
             patch.object(speech_audio.subprocess, "run", side_effect=process):
            self.assertEqual(speech_audio.normalize_speech(original), normalized)

    def test_missing_ffmpeg_preserves_original(self):
        with patch.object(speech_audio.shutil, "which", return_value=None), \
             patch.object(speech_audio.subprocess, "run") as process:
            self.assertEqual(speech_audio.normalize_speech(b"original"), b"original")
            process.assert_not_called()

    def test_timeout_preserves_original(self):
        with patch.object(speech_audio.shutil, "which", return_value="ffmpeg"), \
             patch.object(speech_audio.subprocess, "run", side_effect=subprocess.TimeoutExpired("ffmpeg", 20)):
            self.assertEqual(speech_audio.normalize_speech(b"original"), b"original")

    def test_failed_or_empty_encoding_preserves_original(self):
        stats = {"input_i": "-24", "input_tp": "-9", "input_lra": "2",
                 "input_thresh": "-34", "target_offset": "0"}
        for returncode in (0, 1):
            with self.subTest(returncode=returncode), \
                 patch.object(speech_audio.shutil, "which", return_value="ffmpeg"), \
                 patch.object(speech_audio.subprocess, "run", side_effect=[
                     subprocess.CompletedProcess([], 0, stderr=json.dumps(stats).encode()),
                     subprocess.CompletedProcess([], returncode),
                 ]) as process:
                self.assertEqual(speech_audio.normalize_speech(b"original"), b"original")
                self.assertEqual(process.call_count, 2)

    def test_invalid_measurement_preserves_original(self):
        with patch.object(speech_audio.shutil, "which", return_value="ffmpeg"), \
             patch.object(speech_audio.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, stderr=b"invalid input")) as process:
            self.assertEqual(speech_audio.normalize_speech(b"original"), b"original")
            self.assertEqual(process.call_count, 1)

    def test_silent_audio_preserves_original(self):
        stats = {"input_i": "-inf", "input_tp": "-inf", "input_lra": "0",
                 "input_thresh": "-70", "target_offset": "inf"}
        with patch.object(speech_audio.shutil, "which", return_value="ffmpeg"), \
             patch.object(speech_audio.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stderr=json.dumps(stats).encode())) as process:
            self.assertEqual(speech_audio.normalize_speech(b"silent audio"), b"silent audio")
            self.assertEqual(process.call_count, 1)


if __name__ == "__main__":
    unittest.main()
