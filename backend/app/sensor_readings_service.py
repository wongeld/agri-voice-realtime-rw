from __future__ import annotations

import os
from collections.abc import Iterable

import httpx

from app.schemas import SensorReading


class SensorReadingsService:
    def __init__(
        self,
        endpoints: list[str] | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        configured = endpoints if endpoints is not None else self._load_endpoints_from_env()
        self.endpoints = [url.strip() for url in configured if url.strip()]
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _load_endpoints_from_env() -> list[str]:
        raw = os.getenv("SENSOR_READINGS_ENDPOINTS", "")
        if not raw.strip():
            return []
        return [entry.strip() for entry in raw.split(",") if entry.strip()]

    def _coerce_payload(self, payload: object) -> Iterable[dict]:
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def get_latest_readings(self, limit: int = 1, sensor_id: str | None = None) -> list[SensorReading]:
        if not self.endpoints:
            return []

        readings: list[SensorReading] = []

        with httpx.Client(timeout=self.timeout_seconds) as client:
            for endpoint in self.endpoints:
                try:
                    params: dict[str, str | int] = {}
                    if limit > 0:
                        params["limit"] = limit
                    if sensor_id:
                        params["sensorId"] = sensor_id

                    response = client.get(endpoint, params=params)
                    response.raise_for_status()
                    payload = response.json()

                    for item in self._coerce_payload(payload):
                        try:
                            readings.append(SensorReading.model_validate(item))
                        except Exception:
                            continue
                except Exception:
                    continue

        readings.sort(key=lambda item: item.timestamp, reverse=True)
        if limit <= 0:
            return readings
        return readings[:limit]
