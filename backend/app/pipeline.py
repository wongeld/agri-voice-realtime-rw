from __future__ import annotations

from app.asr_service import ASRService
from app.intent_service import IntentService
from app.response_service import ResponseService
from app.schemas import QueryResponse
from app.tts_service import TTSService


class VoiceIntentPipeline:
    def __init__(
        self,
        asr_service: ASRService,
        intent_service: IntentService,
        response_service: ResponseService,
        tts_service: TTSService,
    ) -> None:
        self.asr_service = asr_service
        self.intent_service = intent_service
        self.response_service = response_service
        self.tts_service = tts_service

    def from_audio(self, audio_input) -> QueryResponse:
        transcript = self.asr_service.transcribe(audio_input)
        return self.from_text(transcript)

    def from_text(self, transcript: str) -> QueryResponse:
        cleaned = transcript.strip()
        if not cleaned:
            return QueryResponse(
                transcript="",
                intents=["general_agri_assistant"],
                conditions=[],
                response_text="",
                tts_wav_base64="",
                tts_sample_rate=self.tts_service.sample_rate,
            )

        intent_result = self.intent_service.parse(transcript)
        response_text = self.response_service.build_text(intent_result)
        tts_wav_base64 = self.tts_service.synthesize_base64_wav(response_text)

        return QueryResponse(
            transcript=intent_result.transcript,
            intents=intent_result.intents,
            conditions=intent_result.conditions,
            response_text=response_text,
            tts_wav_base64=tts_wav_base64,
            tts_sample_rate=self.tts_service.sample_rate,
        )
