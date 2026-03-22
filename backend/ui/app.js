const statusEl = document.getElementById('status');
const enableAutoBtn = document.getElementById('enableAutoBtn');
const turnsEl = document.getElementById('turns');
const uploadForm = document.getElementById('uploadForm');
const audioFileEl = document.getElementById('audioFile');
const uploadOutputEl = document.getElementById('uploadOutput');

const VAD_MIN_THRESHOLD = 0.0035;
const VAD_MULTIPLIER = 2.2;
const VAD_NOISE_ALPHA = 0.95;
const SPEECH_START_FRAMES = 2;
const SILENCE_FLUSH_MS = 700;
const HANGOVER_MS = 220;

let ws = null;
let audioContext = null;
let mediaStream = null;
let sourceNode = null;
let processorNode = null;
let muteGainNode = null;
let isStreaming = false;
let isSpeaking = false;
let assistantSpeaking = false;
let lastVoiceMs = 0;
let sentVoiceSinceFlush = false;
let speechFrames = 0;
let noiseFloor = 0.002;

const ttsPlayer = new Audio();
ttsPlayer.preload = 'auto';

function setStatus(text) {
  statusEl.textContent = `Status: ${text}`;
}

function toWsUrl() {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}/ws/live`;
}

function decodeBase64ToBlob(base64, mimeType) {
  const byteChars = atob(base64);
  const bytes = new Uint8Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i += 1) {
    bytes[i] = byteChars.charCodeAt(i);
  }
  return new Blob([bytes], { type: mimeType });
}

function appendTurn(payload) {
  const card = document.createElement('div');
  card.className = 'turn';

  const meta = document.createElement('div');
  meta.className = 'meta';
  meta.textContent = `intents: ${payload.intents?.join(', ') || 'none'} | conditions: ${payload.conditions?.join(', ') || 'none'}`;

  const txt = document.createElement('div');
  txt.className = 'txt';
  txt.textContent = `Transcript: ${payload.transcript || '(empty)'}\nReply: ${payload.response_text || '(none)'}`;

  card.appendChild(meta);
  card.appendChild(txt);

  turnsEl.prepend(card);
}

function floatToPcm16(float32Array) {
  const pcm16 = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i += 1) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm16;
}

async function connectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return;
  }

  if (ws && ws.readyState === WebSocket.CONNECTING) {
    await new Promise((resolve, reject) => {
      const handleOpen = () => {
        ws.removeEventListener('error', handleError);
        resolve();
      };
      const handleError = () => {
        ws.removeEventListener('open', handleOpen);
        reject(new Error('websocket failed while connecting'));
      };
      ws.addEventListener('open', handleOpen, { once: true });
      ws.addEventListener('error', handleError, { once: true });
    });
    return;
  }

  ws = new WebSocket(toWsUrl());
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => {
    setStatus('connected, waiting for voice');
  };

  ws.onmessage = (event) => {
    if (typeof event.data !== 'string') {
      return;
    }

    const msg = JSON.parse(event.data);
    if (msg.type === 'ready') {
      setStatus('ready for mic stream');
    }
    if (msg.type === 'partial') {
      setStatus(msg.message || 'partial');
    }
    if (msg.type === 'intent_turn') {
      appendTurn(msg);
      playAssistantAudio(msg.tts_wav_base64);
    }
  };

  ws.onerror = () => {
    setStatus('websocket error');
  };

  ws.onclose = () => {
    setStatus('disconnected');
    stopMic();
    isStreaming = false;
    enableAutoBtn.disabled = false;
    enableAutoBtn.textContent = 'Enable Hands-Free Mode';
  };

  await new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      reject(new Error('websocket connect timeout'));
    }, 6000);

    ws.addEventListener(
      'open',
      () => {
        clearTimeout(timeoutId);
        resolve();
      },
      { once: true },
    );

    ws.addEventListener(
      'error',
      () => {
        clearTimeout(timeoutId);
        reject(new Error('websocket connect error'));
      },
      { once: true },
    );
  });
}

function playAssistantAudio(base64Wav) {
  if (!base64Wav) {
    setStatus('listening for your voice...');
    return;
  }

  assistantSpeaking = true;
  setStatus('assistant speaking...');

  if (ttsPlayer.src) {
    URL.revokeObjectURL(ttsPlayer.src);
  }
  const wavBlob = decodeBase64ToBlob(base64Wav, 'audio/wav');
  ttsPlayer.src = URL.createObjectURL(wavBlob);
  ttsPlayer.currentTime = 0;
  ttsPlayer.play().catch(() => {
    assistantSpeaking = false;
    setStatus('listening for your voice...');
  });
}

ttsPlayer.addEventListener('ended', () => {
  assistantSpeaking = false;
  setStatus('listening for your voice...');
});

ttsPlayer.addEventListener('pause', () => {
  if (ttsPlayer.ended) {
    return;
  }
  assistantSpeaking = false;
  setStatus('listening for your voice...');
});

function calculateRms(floatArray) {
  let sum = 0;
  for (let i = 0; i < floatArray.length; i += 1) {
    sum += floatArray[i] * floatArray[i];
  }
  return Math.sqrt(sum / floatArray.length);
}

function currentThreshold() {
  return Math.max(VAD_MIN_THRESHOLD, noiseFloor * VAD_MULTIPLIER);
}

async function startMic() {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    setStatus('connect first');
    return;
  }
  if (isStreaming) {
    return;
  }

  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
    video: false,
  });

  audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
  await audioContext.resume();
  sourceNode = audioContext.createMediaStreamSource(mediaStream);
  processorNode = audioContext.createScriptProcessor(4096, 1, 1);
  muteGainNode = audioContext.createGain();
  muteGainNode.gain.value = 0;

  processorNode.onaudioprocess = (event) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }

    if (assistantSpeaking) {
      return;
    }

    const input = event.inputBuffer.getChannelData(0);
    const rms = calculateRms(input);
    const now = Date.now();

    if (!isSpeaking) {
      noiseFloor = VAD_NOISE_ALPHA * noiseFloor + (1 - VAD_NOISE_ALPHA) * rms;
    }

    if (rms >= currentThreshold()) {
      speechFrames += 1;
    } else {
      speechFrames = 0;
    }

    if (speechFrames >= SPEECH_START_FRAMES) {
      isSpeaking = true;
      lastVoiceMs = now;
      sentVoiceSinceFlush = true;

      const pcm16 = floatToPcm16(input);
      ws.send(pcm16.buffer);
      setStatus('you are speaking...');
      return;
    }

    if (isSpeaking && now - lastVoiceMs <= HANGOVER_MS) {
      const pcm16 = floatToPcm16(input);
      ws.send(pcm16.buffer);
      return;
    }

    if (isSpeaking && rms >= currentThreshold()) {
      lastVoiceMs = now;
      const pcm16 = floatToPcm16(input);
      ws.send(pcm16.buffer);
      return;
    }

    if (isSpeaking && now - lastVoiceMs >= SILENCE_FLUSH_MS) {
      isSpeaking = false;
      speechFrames = 0;
      if (sentVoiceSinceFlush) {
        ws.send(JSON.stringify({ type: 'flush' }));
        sentVoiceSinceFlush = false;
        setStatus('silence detected, generating reply...');
      }
    }
  };

  sourceNode.connect(processorNode);
  processorNode.connect(muteGainNode);
  muteGainNode.connect(audioContext.destination);

  isStreaming = true;
  setStatus('hands-free mode active');
}

function stopMic() {
  if (!isStreaming) {
    return;
  }

  if (processorNode) {
    processorNode.disconnect();
  }
  if (muteGainNode) {
    muteGainNode.disconnect();
  }
  if (sourceNode) {
    sourceNode.disconnect();
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
  }
  if (audioContext) {
    audioContext.close();
  }

  processorNode = null;
  sourceNode = null;
  mediaStream = null;
  audioContext = null;
  muteGainNode = null;
  isStreaming = false;
  isSpeaking = false;
  assistantSpeaking = false;
  sentVoiceSinceFlush = false;
  speechFrames = 0;

  setStatus('mic stopped');
}

async function enableHandsFree() {
  enableAutoBtn.disabled = true;
  try {
    await connectWebSocket();
    await startMic();
    enableAutoBtn.textContent = 'Hands-Free Active';
    setStatus('listening for your voice...');
  } catch (err) {
    const message = err && err.message ? err.message : 'microphone permission denied or unavailable';
    setStatus(message);
    enableAutoBtn.disabled = false;
    console.error(err);
  }
}

async function uploadAudio(event) {
  event.preventDefault();
  const file = audioFileEl.files[0];
  if (!file) {
    return;
  }

  const form = new FormData();
  form.append('file', file);

  uploadOutputEl.textContent = 'Uploading...';
  const response = await fetch('/voice', {
    method: 'POST',
    body: form,
  });

  if (!response.ok) {
    uploadOutputEl.textContent = `Error: ${response.status} ${response.statusText}`;
    return;
  }

  const data = await response.json();
  const sanitized = { ...data, tts_wav_base64: '[hidden]' };
  uploadOutputEl.textContent = JSON.stringify(sanitized, null, 2);
  appendTurn(data);
}

enableAutoBtn.addEventListener('click', enableHandsFree);
uploadForm.addEventListener('submit', uploadAudio);
