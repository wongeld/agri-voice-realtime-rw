from __future__ import annotations

import io
import json
from pathlib import Path

import soundfile as sf
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.asr_service import ASRService
from app.intent_service import IntentService
from app.pipeline import VoiceIntentPipeline
from app.response_service import ResponseService
from app.schemas import QueryResponse
from app.session import RealtimeSession
from app.tts_service import TTSService

SAMPLE_RATE = 16000
WINDOW_SECONDS = 2
WINDOW_SAMPLES = SAMPLE_RATE * WINDOW_SECONDS

app = FastAPI(title="Agri Voice ASR Intent Backend", version="2.0.0")
UI_DIR = Path(__file__).parent / "ui"
app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")


@app.on_event("startup")
def startup() -> None:
    asr_service = ASRService(model_size="tiny", language="rw", vad_filter=False)
    intent_service = IntentService()
    response_service = ResponseService()
    tts_service = TTSService(model_name="facebook/mms-tts-kin", sample_rate=SAMPLE_RATE)
    app.state.pipeline = VoiceIntentPipeline(
        asr_service=asr_service,
        intent_service=intent_service,
        response_service=response_service,
        tts_service=tts_service,
    )


def decode_upload_to_float32(audio_bytes: bytes):
    audio_f32, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    if audio_f32.ndim > 1:
        audio_f32 = audio_f32.mean(axis=1)
    return audio_f32, sr


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "asr_intent"}


@app.get("/")
def ui_home() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.post("/voice", response_model=QueryResponse)
async def voice(file: UploadFile = File(...)) -> QueryResponse:
    audio_bytes = await file.read()
    audio_f32, sr = decode_upload_to_float32(audio_bytes)
    if sr != SAMPLE_RATE:
        raise HTTPException(status_code=400, detail="Input sample rate must be 16000 Hz")

    return app.state.pipeline.from_audio(audio_f32)


@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket) -> None:
    await ws.accept()
    session = RealtimeSession(window_samples=WINDOW_SAMPLES)

    await ws.send_json(
        {
            "type": "ready",
            "message": "Send raw PCM16 mono 16kHz audio chunks. Processing every 2 seconds.",
        }
    )

    try:
        while True:
            try:
                message = await ws.receive()

                chunk = message.get("bytes")
                if chunk is not None:
                    session.append_pcm16(chunk)
                    while session.has_window():
                        window_audio = session.pop_window_float32()
                        result = app.state.pipeline.from_audio(window_audio)
                        if result.transcript:
                            await ws.send_json({"type": "intent_turn", **result.model_dump()})
                        else:
                            await ws.send_json(
                                {
                                    "type": "partial",
                                    "transcript": "",
                                    "message": "No speech recognized in this 2-second window.",
                                }
                            )
                    continue

                text_payload = message.get("text")
                if text_payload is None:
                    continue

                command = json.loads(text_payload)
                if command.get("type") == "text_query":
                    transcript = str(command.get("text", "")).strip()
                    if transcript:
                        result = app.state.pipeline.from_text(transcript)
                        await ws.send_json({"type": "intent_turn", **result.model_dump()})
                elif command.get("type") == "flush":
                    if not session.has_audio():
                        continue

                    tail_audio = session.pop_all_float32()
                    if tail_audio.size == 0:
                        continue

                    result = app.state.pipeline.from_audio(tail_audio)
                    if result.transcript:
                        await ws.send_json({"type": "intent_turn", **result.model_dump()})
                    else:
                        await ws.send_json(
                            {
                                "type": "partial",
                                "transcript": "",
                                "message": "No speech recognized after silence flush.",
                            }
                        )
            except Exception as processing_error:
                await ws.send_json(
                    {
                        "type": "error",
                        "message": f"Processing error: {processing_error}",
                    }
                )
    except WebSocketDisconnect:
        return
