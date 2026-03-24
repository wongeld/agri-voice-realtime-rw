# Voice Backend (Live ASR -> Intent -> TTS)

This repository contains two parts:

1. Initial notebook experiments for ASR and TTS in `asr.ipynb`
2. Production-style FastAPI backend in `backend/`

This backend is focused only on:

1. Live audio ingestion
2. Kinyarwanda transcription with `faster-whisper`
3. Agriculture intent parsing (supports conditional clauses and multiple intents)
4. Text generation per detected intent and Kinyarwanda TTS synthesis

Optional agentic mode is now supported using Groq + LangChain. If enabled, responses are generated from live sensor readings fetched from configured GET endpoints.

Sensor collection, dashboards, and hardware calls remain out of scope and should be handled by your other API.

## Initial Notebook Experiments

The notebook `asr.ipynb` captures the early validation flow before backend refactoring:

1. ASR prototype with `faster-whisper`:
- Installs and loads `WhisperModel("small", device="cpu", compute_type="int8")`
- Transcribes `audio_test_1.ogg`
- Notes observed speed from initial run

2. TTS prototype with Meta MMS model:
- Loads `facebook/mms-tts-kin` (`VitsModel` + `AutoTokenizer`)
- Generates waveform from Kinyarwanda text
- Saves output audio to `output.wav`

3. Early API sketch:
- Includes an initial `/voice` endpoint concept in notebook cells
- This was later replaced with the modular FastAPI implementation under `backend/`

If you want to re-run the notebook experiments directly, open `asr.ipynb` and execute the code cells in order.

## Repository Layout

- `asr.ipynb`: initial ASR and TTS experimentation notebook
- `audio_test_1.ogg`: sample input used during early ASR tests
- `output.wav`: generated sample output from notebook TTS test
- `backend/`: current real-time ASR -> intent -> TTS service and web UI

## Endpoints

- `GET /health`
- `GET /` web UI for live demo
- `POST /voice` upload one audio file (expects 16kHz audio)
- `WS /ws/live` send PCM16 mono 16kHz chunks and receive transcript+intent+tts turns

## Run

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Optional Groq Agent Mode

Set these environment variables before starting FastAPI:

```bash
set GROQ_API_KEY=your_key_here
set GROQ_MODEL=llama-3.3-70b-versatile
set SENSOR_READINGS_ENDPOINTS=http://localhost:9000/readings/latest,http://localhost:9000/readings/latest-by-sensor
set AGENT_VERBOSE=true
set AGENT_TRACE_FILE_ENABLED=true
set AGENT_TRACE_FILE=agent_trace.jsonl
```

Notes:

- `SENSOR_READINGS_ENDPOINTS` accepts comma-separated GET URLs.
- Endpoints may return a single object or a list of objects.
- The agent uses these fields when available: `timestamp`, `metadata.sensorId`, `metadata.location`, `temperature`, `moisture`, `nitrogen`, `phosphorus`, `potassium`, `ph`, `ec`, `prediction`.
- Supported `prediction` labels are: `Tomato`, `Maize`, `Sugarcane`, `Wheat`, `Potato`, `Rice`.
- Agent responses are forced to be in Kinyarwanda.
- Set `AGENT_VERBOSE=true` to print LangChain execution steps in server logs.
- Set `AGENT_TRACE_FILE_ENABLED=true` to write intermediate steps and final output to `AGENT_TRACE_FILE` in JSONL format.
- If `GROQ_API_KEY` is not set, the backend automatically falls back to the existing static response behavior.

### Optional LangSmith Tracing

If you want centralized LangChain tracing UI:

```bash
set LANGSMITH_TRACING=true
set LANGSMITH_API_KEY=your_langsmith_key
set LANGSMITH_PROJECT=asr-agent
```

When these are set, LangChain traces are sent to LangSmith in addition to local logs.

## Component breakdown

- `main.py`: API wiring and websocket loop
- `ui/index.html`: demo interface
- `ui/styles.css`: UI styling
- `ui/app.js`: websocket + mic + upload logic
- `app/asr_service.py`: Whisper model loading and transcription
- `app/intent_service.py`: Intent parsing and condition extraction
- `app/response_service.py`: response text generation per intent
- `app/agent_service.py`: Groq + LangChain tool-calling agent (optional)
- `app/sensor_readings_service.py`: sensor API fetch + payload validation
- `app/tts_service.py`: Kinyarwanda TTS synthesis (WAV base64)
- `app/pipeline.py`: orchestration from audio to intent + tts response
- `app/session.py`: rolling 3-second PCM window buffer
- `app/schemas.py`: request/response models

Low-latency defaults now enabled:

- Whisper model size defaults to `tiny` for faster real-time decoding
- Streaming window reduced to 2 seconds
- Client silence flush reduced for faster end-of-utterance response
- TTS synthesis has in-memory caching for repeated responses

## WebSocket protocol (`/ws/live`)

- Send binary frames: raw PCM16 little-endian, mono, 16kHz.
- Backend groups audio into 2-second windows and transcribes each window.
- Backend responds with JSON messages:
  - `type = ready`
  - `type = partial`
  - `type = intent_turn` (contains transcript, intents, conditions, response_text, tts_wav_base64, tts_sample_rate)
- Optional control message: `{"type":"flush"}` forces processing of any remaining buffered audio (used when silence is detected).

Optional text message for direct intent parsing:

```json
{"type":"text_query","text":"Niba amazi ari hasi kandi conductivity y'ubutaka iri hejuru, nkore iki?"}
```

## Notes

- ASR is configured for Kinyarwanda input. If the loaded Whisper checkpoint does not support `rw` as a direct language code, the backend automatically falls back to auto-detection so live streaming does not crash.
- Intent parser includes agriculture sensor vocabulary and condition detection (`niba`, `mu gihe`, `keretse`, etc).
- TTS model: `facebook/mms-tts-kin`.

## Quick UI test

1. Start API: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
2. Open `http://localhost:8000`
3. Click `Start Assistant` once to grant microphone access
4. Speak naturally; when you pause, the UI auto-triggers a reply and then listens again automatically
