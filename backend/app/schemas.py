from __future__ import annotations

from datetime import datetime

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


class LocationMetadata(BaseModel):
    city: str | None = None
    Country: str | None = None


class SensorMetadata(BaseModel):
    sensorId: str | None = None
    location: LocationMetadata | None = None


class SensorReading(BaseModel):
    timestamp: datetime
    metadata: SensorMetadata | None = None
    temperature: float | int | None = None
    moisture: float | int | None = None
    nitrogen: float | int | None = None
    phosphorus: float | int | None = None
    potassium: float | int | None = None
    ph: float | int | None = None
    ec: float | int | None = None
    prediction: str | None = None
