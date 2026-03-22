from __future__ import annotations

import numpy as np
from faster_whisper import WhisperModel


class ASRService:
    def __init__(
        self,
        model_size: str = "tiny",
        language: str = "rw",
        vad_filter: bool = False,
    ) -> None:
        self.language = language
        self.vad_filter = vad_filter
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio: str | np.ndarray) -> str:
        base_kwargs = {
            "vad_filter": self.vad_filter,
            "beam_size": 1,
            "best_of": 1,
            "temperature": 0.0,
            "condition_on_previous_text": False,
        }

        try:
            segments, _ = self.model.transcribe(
                audio,
                language=self.language,
                **base_kwargs,
            )
        except ValueError as exc:
            # Some Whisper checkpoints do not support all language codes (e.g. rw).
            # Fall back to auto language detection instead of interrupting live streaming.
            if "not a valid language code" not in str(exc):
                raise
            segments, _ = self.model.transcribe(
                audio,
                language=None,
                **base_kwargs,
            )

        return " ".join(seg.text.strip() for seg in segments).strip()
