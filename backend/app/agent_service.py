from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

from app.schemas import IntentResult
from app.sensor_readings_service import SensorReadingsService

SUPPORTED_PREDICTIONS = {"Tomato", "Maize", "Sugarcane", "Wheat", "Potato", "Rice"}


class AgentService:
    def __init__(self, readings_service: SensorReadingsService) -> None:
        self.readings_service = readings_service
        self.enabled = False
        self.error_reason: str | None = None
        self.agent_executor = None
        self.trace_file = Path(os.getenv("AGENT_TRACE_FILE", "agent_trace.jsonl"))
        self.enable_trace_file = os.getenv("AGENT_TRACE_FILE_ENABLED", "false").lower() == "true"
        self._initialize_agent()

    def _append_trace(self, payload: dict) -> None:
        if not self.enable_trace_file:
            return

        try:
            line = json.dumps(payload, ensure_ascii=True) + "\n"
            self.trace_file.parent.mkdir(parents=True, exist_ok=True)
            with self.trace_file.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except Exception:
            # Never break runtime response path because of observability issues.
            return

    def _initialize_agent(self) -> None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            self.error_reason = "GROQ_API_KEY is not configured"
            return

        try:
            agents_mod = importlib.import_module("langchain.agents")
            prompts_mod = importlib.import_module("langchain_core.prompts")
            tools_mod = importlib.import_module("langchain_core.tools")
            groq_mod = importlib.import_module("langchain_groq")

            AgentExecutor = getattr(agents_mod, "AgentExecutor")
            create_tool_calling_agent = getattr(agents_mod, "create_tool_calling_agent")
            ChatPromptTemplate = getattr(prompts_mod, "ChatPromptTemplate")
            MessagesPlaceholder = getattr(prompts_mod, "MessagesPlaceholder")
            tool = getattr(tools_mod, "tool")
            ChatGroq = getattr(groq_mod, "ChatGroq")

            @tool
            def get_latest_sensor_readings(limit: int = 3, sensor_id: str = "") -> str:
                """Fetch latest sensor readings from configured FastAPI GET endpoints."""
                sid = sensor_id.strip() or None
                safe_limit = max(1, min(limit, 10))
                rows = self.readings_service.get_latest_readings(limit=safe_limit, sensor_id=sid)
                if not rows:
                    return "No latest readings were returned from configured endpoints."
                payload = [row.model_dump(mode="json") for row in rows]
                return json.dumps(payload, ensure_ascii=True)

            @tool
            def list_supported_predictions() -> str:
                """Return all supported crop prediction labels."""
                return json.dumps(sorted(SUPPORTED_PREDICTIONS), ensure_ascii=True)

            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are an agriculture assistant for IoT soil readings. "
                        "Always answer in clear Kinyarwanda. "
                        "Always ground your answer in tool output when available. "
                        "The only valid prediction labels are Tomato, Maize, Sugarcane, Wheat, Potato, Rice. "
                        "If prediction value is missing or '-', clearly say prediction is not available yet. "
                        "If user asks recommendation, tailor it to the current prediction and readings.",
                    ),
                    ("human", "User transcript: {transcript}\nDetected intents: {intents}\nConditions: {conditions}"),
                    MessagesPlaceholder("agent_scratchpad"),
                ]
            )

            model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            llm = ChatGroq(model=model_name, api_key=api_key, temperature=0.2)
            tools = [get_latest_sensor_readings, list_supported_predictions]
            agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)
            verbose = os.getenv("AGENT_VERBOSE", "true").lower() == "true"
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=verbose,
                return_intermediate_steps=True,
            )
            self.enabled = True
        except Exception as exc:
            self.error_reason = str(exc)
            self.enabled = False

    def answer(self, result: IntentResult) -> str | None:
        if not self.enabled or self.agent_executor is None:
            return None

        try:
            response = self.agent_executor.invoke(
                {
                    "transcript": result.transcript,
                    "intents": ", ".join(result.intents),
                    "conditions": ", ".join(result.conditions) if result.conditions else "none",
                }
            )
            output = response.get("output", "") if isinstance(response, dict) else ""
            if isinstance(response, dict):
                steps = response.get("intermediate_steps", [])
                self._append_trace(
                    {
                        "transcript": result.transcript,
                        "intents": result.intents,
                        "conditions": result.conditions,
                        "intermediate_steps": [str(step) for step in steps],
                        "output": str(output),
                    }
                )
            text = str(output).strip()
            return text or None
        except Exception:
            return None
