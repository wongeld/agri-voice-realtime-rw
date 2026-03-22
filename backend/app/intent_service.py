from __future__ import annotations

import re

from app.schemas import IntentResult


class IntentService:
    def __init__(self) -> None:
        self.intent_keywords = {
            "soil_moisture": ["ubutaka", "moisture", "humidity y'ubutaka", "ubushuhe bw'ubutaka"],
            "soil_conductivity": ["conductivity", "ec", "ubuyobozi bw'amashanyarazi", "soil conductivity"],
            "water_level": ["amazi", "water", "tank", "water level"],
            "temperature": ["temperature", "ubushyuhe", "temp"],
            "humidity": ["humidity", "ubushuhe bw'ikirere", "air humidity"],
            "ph": ["ph", "acidity", "ubukana"],
            "npk": ["npk", "nitrogen", "phosphorus", "potassium", "ifumbire"],
            "irrigation": ["irrigation", "kuhira", "gutera amazi"],
            "alerts": ["alert", "risk", "ikibazo", "warning", "akangaratete"],
        }
        self.condition_patterns = [
            r"\bniba\b[^,.!?;]*",
            r"\bmu gihe\b[^,.!?;]*",
            r"\bigihe\b[^,.!?;]*",
            r"\bkeretse\b[^,.!?;]*",
            r"\bif\b[^,.!?;]*",
            r"\bunless\b[^,.!?;]*",
            r"\bwhen\b[^,.!?;]*",
        ]

    def parse(self, transcript: str) -> IntentResult:
        lower = transcript.lower()
        found_intents: list[str] = []

        for intent, keys in self.intent_keywords.items():
            if any(key in lower for key in keys):
                found_intents.append(intent)

        if not found_intents:
            found_intents = ["general_agri_assistant"]

        conditions: list[str] = []
        for pattern in self.condition_patterns:
            conditions.extend(re.findall(pattern, lower))

        and_split = re.split(r"\b(na|and|kandi|cyangwa|or)\b", lower)
        if len(and_split) > 3 and len(found_intents) == 1:
            found_intents.append("multi_intent_query")

        return IntentResult(
            transcript=transcript,
            intents=sorted(set(found_intents)),
            conditions=conditions,
        )
