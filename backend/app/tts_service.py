from __future__ import annotations

import base64
import io
from collections import OrderedDict

import soundfile as sf
import torch
from transformers import AutoTokenizer, VitsModel


class TTSService:
    def __init__(
        self,
        model_name: str = "facebook/mms-tts-kin",
        sample_rate: int = 16000,
        cache_size: int = 128,
    ) -> None:
        self.sample_rate = sample_rate
        self.cache_size = cache_size
        self.model = VitsModel.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._audio_cache: OrderedDict[str, str] = OrderedDict()

    def synthesize_base64_wav(self, text: str) -> str:
        cached = self._audio_cache.get(text)
        if cached is not None:
            self._audio_cache.move_to_end(text)
            return cached

        inputs = self.tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            waveform = self.model(**inputs).waveform

        audio = waveform.squeeze().cpu().numpy()
        buffer = io.BytesIO()
        sf.write(buffer, audio, samplerate=self.sample_rate, format="WAV")
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

        self._audio_cache[text] = encoded
        self._audio_cache.move_to_end(text)
        if len(self._audio_cache) > self.cache_size:
            self._audio_cache.popitem(last=False)

        return encoded
