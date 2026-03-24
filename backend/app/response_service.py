from __future__ import annotations

from app.agent_service import AgentService
from app.schemas import IntentResult


class ResponseService:
    def __init__(self, agent_service: AgentService | None = None) -> None:
        self.agent_service = agent_service
        self.intent_text = {
            "soil_moisture": "Nabonye ikibazo cy'ubushuhe bw'ubutaka.",
            "soil_conductivity": "Nabonye ikibazo cya soil conductivity.",
            "water_level": "Nabonye ikibazo kijyanye n'amazi.",
            "temperature": "Nabonye ikibazo cy'ubushyuhe.",
            "humidity": "Nabonye ikibazo cy'ubushuhe bw'ikirere.",
            "ph": "Nabonye ikibazo cya pH y'ubutaka.",
            "npk": "Nabonye ikibazo cya NPK.",
            "irrigation": "Nabonye ikibazo cyo kuhira.",
            "alerts": "Nabonye ikibazo cy'ibyago cyangwa warning.",
            "multi_intent_query": "Wabajije intents nyinshi icyarimwe.",
            "general_agri_assistant": "Niteguye kugufasha ku bibazo by'ubuhinzi.",
        }

    def build_text(self, result: IntentResult) -> str:
        if self.agent_service is not None:
            agent_answer = self.agent_service.answer(result)
            if agent_answer:
                return agent_answer

        chunks: list[str] = []
        for intent in result.intents:
            if intent in self.intent_text:
                chunks.append(self.intent_text[intent])

        if result.conditions:
            chunks.append("Nabonye n'ibice by'ibisabwa nka: " + ", ".join(result.conditions[:3]))

        if not chunks:
            chunks.append(self.intent_text["general_agri_assistant"])

        return " ".join(chunks)
