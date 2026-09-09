"""Balance generated narration for the same listening level as online music."""
from pathlib import Path
import json
import math
import shutil
import subprocess
import tempfile


def normalize_speech(audio):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("TTS loudness normalization unavailable: ffmpeg not found")
        return audio
    try:
        filter_spec = "loudnorm=I=-14:TP=-1.5:LRA=7:dual_mono=true"
        measured = subprocess.run([
            ffmpeg, "-hide_banner", "-nostdin", "-threads", "1",
            "-filter_threads", "1", "-i", "pipe:0", "-vn", "-af",
            filter_spec + ":print_format=json", "-f", "null", "-",
        ], input=audio, capture_output=True, timeout=20, check=False)
        report = measured.stderr.decode("utf-8", errors="replace")
        stats = json.loads(report[report.rfind("{"):])
        fields = {"measured_I": "input_i", "measured_TP": "input_tp",
                  "measured_LRA": "input_lra", "measured_thresh": "input_thresh",
                  "offset": "target_offset"}
        values = {key: float(stats[source]) for key, source in fields.items()}
        if measured.returncode != 0 or not all(math.isfinite(value) for value in values.values()):
            return audio
        filter_spec += ":" + ":".join(f"{key}={value}" for key, value in values.items())
        # A seekable output lets the MP3 encoder retain accurate duration metadata.
        with tempfile.TemporaryDirectory(prefix="tingjian-tts-") as directory:
            output = Path(directory) / "speech.mp3"
            result = subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                "-threads", "1", "-filter_threads", "1", "-i", "pipe:0",
                "-vn", "-af", filter_spec,
                "-ar", "32000", "-ac", "1", "-codec:a", "libmp3lame",
                "-b:a", "128k", str(output),
            ], input=audio, capture_output=True, timeout=20, check=False)
            if result.returncode == 0 and output.is_file() and output.stat().st_size > 128:
                return output.read_bytes()
            print("TTS loudness normalization failed; retaining original audio")
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        print("TTS loudness normalization unavailable; retaining original audio")
    return audio
