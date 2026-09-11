"""CPU-only local TTS service backed by sherpa-onnx and MeloTTS."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from tts.engine import (
    DEFAULT_SPEED,
    MAX_TEXT_CHARS,
    NUM_THREADS,
    encode_wav,
    load_engine,
)

_synth_lock = asyncio.Lock()


class SynthesisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)
    speed: float = Field(default=DEFAULT_SPEED, ge=0.5, le=1.5)


@asynccontextmanager
async def lifespan(app):
    app.state.engine = await asyncio.to_thread(load_engine)
    yield
    app.state.engine = None


app = FastAPI(title="Tingjian local TTS", lifespan=lifespan)


@app.get("/health")
def health():
    engine = getattr(app.state, "engine", None)
    if engine is None:
        raise HTTPException(503, "model is not ready")
    return {
        "status": "ok",
        "model": "vits-melo-tts-zh_en",
        "sample_rate": engine.sample_rate,
        "num_threads": NUM_THREADS,
        "max_text_chars": MAX_TEXT_CHARS,
    }


@app.post("/synthesize")
async def synthesize(req: SynthesisRequest):
    engine = getattr(app.state, "engine", None)
    if engine is None:
        raise HTTPException(503, "model is not ready")
    try:
        async with _synth_lock:
            audio = await asyncio.to_thread(engine.generate, req.text, 0, req.speed)
    except Exception as exc:
        raise HTTPException(500, f"synthesis failed: {type(exc).__name__}") from exc
    if not len(audio.samples):
        raise HTTPException(500, "synthesis returned empty audio")
    return Response(
        content=encode_wav(audio),
        media_type="audio/wav",
        headers={"X-TTS-Sample-Rate": str(audio.sample_rate)},
    )
