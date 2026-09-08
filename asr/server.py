# sherpa-onnx 中文 ASR 服务 (OpenAI /v1/audio/transcriptions 兼容)
# paraformer-zh int8, CPU 推理, 供 ai-radio /api/talk 调用
import array
import io
import os
import time
import wave

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

import sherpa_onnx

MODEL_DIR = os.getenv("MODEL_DIR", "/models")
TOKENS = os.path.join(MODEL_DIR, "tokens.txt")
MODEL = os.path.join(MODEL_DIR, "model.int8.onnx")
THREADS = int(os.getenv("ASR_THREADS", "2"))

recognizer = None

def load_model():
    global recognizer
    t0 = time.time()
    recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=MODEL,
        tokens=TOKENS,
        num_threads=THREADS,
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
        debug=False,
    )
    print(f"model loaded in {time.time()-t0:.2f}s", flush=True)

app = FastAPI()

@app.on_event("startup")
async def _startup():
    load_model()

@app.post("/v1/audio/transcriptions")
async def transcribe(file: UploadFile = File(...)):
    audio = await file.read()
    if not audio:
        raise HTTPException(400, "empty file")
    try:
        with wave.open(io.BytesIO(audio)) as w:
            rate = w.getframerate()
            samples = array.array("h", w.readframes(w.getnframes()))
    except Exception as e:
        raise HTTPException(400, f"bad wav: {e}")
    if rate != 16000:
        raise HTTPException(400, f"rate {rate} != 16000, need 16k mono wav")
    floats = [x / 32768.0 for x in samples]

    t0 = time.time()
    stream = recognizer.create_stream()
    stream.accept_waveform(16000, floats)
    recognizer.decode_stream(stream)
    text = stream.result.text.strip()
    print(f"decoded {len(samples)/16000:.2f}s audio in {time.time()-t0:.2f}s: {text}", flush=True)
    return JSONResponse({"text": text})

@app.get("/health")
async def health():
    return {"ok": recognizer is not None}

if __name__ == "__main__":
    import uvicorn
    load_model()
    uvicorn.run(app, host="0.0.0.0", port=8000)
