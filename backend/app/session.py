from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class RealtimeSession:
    window_samples: int
    pcm_buffer: bytearray = field(default_factory=bytearray)

    def append_pcm16(self, chunk: bytes) -> None:
        self.pcm_buffer.extend(chunk)

    def has_window(self) -> bool:
        return len(self.pcm_buffer) >= self.window_samples * 2

    def has_audio(self) -> bool:
        return len(self.pcm_buffer) > 0

    def pop_window_float32(self) -> np.ndarray:
        byte_count = self.window_samples * 2
        window_bytes = self.pcm_buffer[:byte_count]
        del self.pcm_buffer[:byte_count]

        audio_i16 = np.frombuffer(window_bytes, dtype=np.int16)
        return audio_i16.astype(np.float32) / 32768.0

    def pop_all_float32(self) -> np.ndarray:
        if not self.pcm_buffer:
            return np.array([], dtype=np.float32)

        # Copy out immutable bytes before clearing to avoid BufferError from live exports.
        pcm_bytes = bytes(self.pcm_buffer)
        audio_i16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        self.pcm_buffer.clear()
        return audio_i16.astype(np.float32) / 32768.0
