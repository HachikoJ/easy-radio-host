"""Expressive prosody rendering for the local single-style TTS model.

`vits-melo-tts-zh_en` has one fixed style: the sherpa-onnx API exposes no
emotion label, style vector or reference audio, so the voice itself cannot act.
What can be shaped on CPU is prosody around the model: the text is split into
clauses, every clause is synthesized with its own speaking rate and gain trim,
and the gaps between clauses are written explicitly.  The voice stays the same,
but the read gets a livelier rhythm, clearer breaths and a calmer close.
"""
from dataclasses import dataclass
import re

from tts.engine import DEFAULT_SPEED, pcm16_from_samples


HARD_ENDINGS = "。！？!?…"
SOFT_ENDINGS = "，,、；;：:"
SPLIT_ENDINGS = HARD_ENDINGS + SOFT_ENDINGS

MIN_CLAUSE_CHARS = 6
MAX_CLAUSE_CHARS = 28
FADE_SECONDS = 0.008

# 模型自己会在标点处留下约 120ms 静音, 这里只补差价, 让分句听得出来但不拖沓。
PAUSE_MS = {
    "。": 170, "！": 150, "!": 150, "？": 160, "?": 160, "…": 320,
    "；": 140, ";": 140, "：": 130, ":": 130,
    "，": 110, ",": 110, "、": 90,
}
DEFAULT_PAUSE_MS = 130

SPEED_FACTORS = {"！": 1.06, "!": 1.06, "…": 0.95, "？": 0.98, "?": 0.98}
GAIN_FACTORS = {"！": 1.06, "!": 1.06, "…": 0.94, "？": 0.98, "?": 0.98}
OPENING_SPEED_FACTOR = 0.98
LAST_SPEED_FACTOR = 0.97
LAST_GAIN_FACTOR = 0.96


@dataclass(frozen=True)
class Clause:
    """One synthesized unit: text, model speed, trailing pause and gain trim."""

    text: str
    speed: float
    pause_ms: int
    gain: float


def _clause_ending(clause):
    for char in reversed(clause):
        if char in SPLIT_ENDINGS or char in HARD_ENDINGS:
            return char
        if not char.isspace():
            return ""
    return ""


def _force_cut_index(buffer):
    """Break a punctuation-free run at a space when one is close to the edge."""
    space = buffer.rfind(" ")
    return space + 1 if space >= MIN_CLAUSE_CHARS else len(buffer)


def split_clauses(text):
    """Split narration into clause-sized chunks the model can voice separately."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    clauses, buffer = [], ""
    for char in normalized:
        buffer += char
        if char in SPLIT_ENDINGS:
            long_enough = len(buffer.strip()) >= MIN_CLAUSE_CHARS or (
                char in HARD_ENDINGS and len(buffer.strip()) >= 3)
            if long_enough:
                clauses.append(buffer.strip())
                buffer = ""
        elif len(buffer) >= MAX_CLAUSE_CHARS:
            cut = _force_cut_index(buffer)
            clauses.append(buffer[:cut].strip())
            buffer = buffer[cut:]
    if buffer.strip():
        clauses.append(buffer.strip())
    return [clause for clause in clauses if clause]


def plan(text, base_speed=DEFAULT_SPEED):
    """Turn narration into per-clause synthesis instructions."""
    clauses = split_clauses(text)
    total = len(clauses)
    planned = []
    for index, clause in enumerate(clauses):
        ending = _clause_ending(clause)
        speed_factor = SPEED_FACTORS.get(ending, 1.0)
        gain = GAIN_FACTORS.get(ending, 1.0)
        pause_ms = PAUSE_MS.get(ending, DEFAULT_PAUSE_MS)
        if index == 0 and total > 2:
            speed_factor *= OPENING_SPEED_FACTOR
        if index == total - 1:
            speed_factor *= LAST_SPEED_FACTOR
            gain *= LAST_GAIN_FACTOR
            pause_ms = 0
        planned.append(Clause(
            text=clause,
            speed=round(min(1.5, max(0.5, base_speed * speed_factor)), 4),
            pause_ms=pause_ms,
            gain=round(gain, 4),
        ))
    return planned


def _shape(pcm, gain, sample_rate):
    """Apply the gain trim and short fades so clause joins never click."""
    if gain != 1.0:
        for index, value in enumerate(pcm):
            pcm[index] = max(-32768, min(32767, int(value * gain)))
    fade = min(max(1, int(sample_rate * FADE_SECONDS)), len(pcm) // 2)
    for index in range(fade):
        factor = index / fade
        pcm[index] = int(pcm[index] * factor)
        pcm[len(pcm) - 1 - index] = int(pcm[len(pcm) - 1 - index] * factor)


def render(engine, text, base_speed=DEFAULT_SPEED):
    """Synthesize narration clause by clause; returns (pcm16 bytes, sample rate)."""
    clauses = plan(text, base_speed)
    if not clauses:
        raise ValueError("empty text")
    sample_rate = int(engine.sample_rate)
    chunks = []
    for clause in clauses:
        audio = engine.generate(clause.text, 0, clause.speed)
        pcm = pcm16_from_samples(audio.samples)
        _shape(pcm, clause.gain, sample_rate)
        chunks.append(pcm.tobytes())
        if clause.pause_ms > 0:
            chunks.append(b"\x00\x00" * max(1, int(sample_rate * clause.pause_ms / 1000)))
    return b"".join(chunks), sample_rate
