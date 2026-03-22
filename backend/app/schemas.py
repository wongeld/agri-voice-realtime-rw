from __future__ import annotations

from pydantic import BaseModel


class IntentResult(BaseModel):
    intents: list[str]
    conditions: list[str]
    transcript: str


class QueryResponse(BaseModel):
    transcript: str
    intents: list[str]
    conditions: list[str]
    response_text: str
    tts_wav_base64: str
    tts_sample_rate: int
