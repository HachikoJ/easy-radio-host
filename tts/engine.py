"""Model loading and WAV encoding for the local sherpa-onnx TTS service."""
import array
import io
import os
import wave
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = REPO_ROOT / "models" / "vits-melo-tts-zh_en"
MODEL_DIR = Path(os.getenv("LOCAL_TTS_MODEL_DIR", str(DEFAULT_MODEL_DIR)))
MODEL_PATH = MODEL_DIR / os.getenv("LOCAL_TTS_MODEL_FILE", "model.onnx")
LEXICON_PATH = MODEL_DIR / os.getenv("LOCAL_TTS_LEXICON_FILE", "lexicon.txt")
TOKENS_PATH = MODEL_DIR / os.getenv("LOCAL_TTS_TOKENS_FILE", "tokens.txt")
NUM_THREADS = max(1, int(os.getenv("LOCAL_TTS_THREADS", "2")))
DEFAULT_SPEED = max(0.5, min(1.5, float(os.getenv("LOCAL_TTS_SPEED", "1.0"))))
MAX_TEXT_CHARS = max(1, int(os.getenv("LOCAL_TTS_MAX_TEXT_CHARS", "500")))


def missing_model_files():
    return [str(path) for path in (MODEL_PATH, LEXICON_PATH, TOKENS_PATH) if not path.is_file()]


def load_engine():
    """Load the model once for the lifetime of the service process."""
    missing = missing_model_files()
    if missing:
        raise FileNotFoundError("missing local TTS model files: " + ", ".join(missing))

    import sherpa_onnx

    vits = sherpa_onnx.OfflineTtsVitsModelConfig(
        model=str(MODEL_PATH),
        lexicon=str(LEXICON_PATH),
        tokens=str(TOKENS_PATH),
    )
    model = sherpa_onnx.OfflineTtsModelConfig(
        vits=vits,
        num_threads=NUM_THREADS,
        provider="cpu",
        debug=False,
    )
    config = sherpa_onnx.OfflineTtsConfig(model=model)
    return sherpa_onnx.OfflineTts(config)


def pcm16_from_samples(samples):
    """Convert sherpa-onnx floating-point samples to clipped PCM16 values."""
    return array.array(
        "h",
        (max(-32768, min(32767, int(sample * 32767))) for sample in samples),
    )


def wav_bytes(pcm, sample_rate):
    """Wrap raw mono PCM16 bytes in a WAV container."""
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return output.getvalue()


def encode_wav(audio):
    """Convert sherpa-onnx floating-point samples to a PCM16 WAV file."""
    return wav_bytes(pcm16_from_samples(audio.samples).tobytes(), audio.sample_rate)
