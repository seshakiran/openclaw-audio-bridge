# 🎙️ OpenClaw Audio Bridge

A voice-powered AI assistant that bridges **OpenClaw** with natural speech — entirely local, running on Apple Silicon. Think ElevenLabs-quality TTS + Whisper STT + real-time echo cancellation, all on your Mac.

> **Say "Marvin, what's the latest news?"** and get a spoken response while background music plays. Interrupt anytime with **"Marvin, stop."**

---

## ⚡ TL;DR — Get Running in 60 Seconds

```bash
git clone https://github.com/seshakiran/openclaw-audio-bridge.git
cd openclaw-audio-bridge
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg                       # if not already installed
cp .env.example .env
python list_devices.py                    # find your mic index
nano .env                                 # set MICROPHONE_INDEX to your mic
# Drop some .mp3 files into music/ folder (optional, for background music)
python main_v2.py                         # 🎙️ Say "Marvin, what's the news?"
```

> **Requires:** macOS 13+ with Apple Silicon (M1/M2/M3/M4), Python 3.10+, and [OpenClaw CLI](https://openclaw.ai) installed.

---

## ✨ Features

| Feature | Tech | Details |
|---------|------|---------|
| 🗣️ **Text-to-Speech** | MLX (Chatterbox-Turbo) | ElevenLabs-quality neural TTS, runs 100% locally on Apple Silicon GPU |
| 👂 **Speech-to-Text** | Faster-Whisper | Real-time transcription with Whisper `base` model on CPU |
| 🔇 **Echo Cancellation** | WebRTC VAD + Software | Voice Activity Detection prevents the mic from picking up its own speech |
| 🎵 **Background Music** | afplay | Plays ambient music while waiting for OpenClaw responses |
| 💬 **Filler Chat** | SQLite | Tells jokes and small talk during long processing waits |
| 🧠 **AI Backend** | OpenClaw | Sends commands to OpenClaw agent, parses JSON responses |
| ⚡ **Streaming TTS** | Chunked generation | Long responses are split and streamed — hear audio in ~5 seconds, not 30+ |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Main Event Loop                       │
│                    (main_v2.py)                           │
│                                                          │
│   ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│   │  STT     │    │  Wake    │    │   Command        │  │
│   │  Thread  │───▶│  Word    │───▶│   Processing     │  │
│   │          │    │  Detect  │    │                   │  │
│   └──────────┘    └──────────┘    └────────┬─────────┘  │
│        ▲                                    │            │
│        │                                    ▼            │
│   ┌──────────┐                      ┌──────────────┐    │
│   │  Micro-  │                      │  OpenClaw    │    │
│   │  phone   │                      │  Agent CLI   │    │
│   │  (VAD)   │                      │              │    │
│   └──────────┘                      └──────┬───────┘    │
│        ▲                                    │            │
│        │                                    ▼            │
│   ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│   │  Echo    │    │  Music   │    │   MLX TTS        │  │
│   │  Filter  │◀───│  Player  │    │  (Chatterbox)    │  │
│   │          │    │  🎵      │    │  Streaming       │  │
│   └──────────┘    └──────────┘    └──────────────────┘  │
│                                          │               │
│                                          ▼               │
│                                   ┌──────────────┐      │
│                                   │   Speaker    │      │
│                                   │   (afplay)   │      │
│                                   └──────────────┘      │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. 🎤 Microphone records audio (sounddevice)
2. 🔇 WebRTC VAD filters silence — only processes speech frames
3. 📝 Faster-Whisper transcribes speech to text (CPU, int8)
4. 🔍 Wake word detection ("Marvin" + variants)
5. 🔄 Echo filter rejects mic picking up speaker output
6. 🧠 Command sent to OpenClaw agent CLI (async subprocess)
7. 🎵 Background music plays while waiting
8. 💬 Filler chat (jokes/small talk) during long waits
9. 📨 OpenClaw JSON response parsed
10. ✂️ Response cleaned (markdown, emojis stripped) & truncated
11. 🗣️ MLX Chatterbox-Turbo generates speech in streaming chunks
12. 🔊 Each chunk plays immediately via afplay while next generates
```

### Module Map

| Module | Purpose |
|--------|---------|
| `main_v2.py` | Main event loop, wake word detection, mode management |
| `stt_vad_module.py` | Speech-to-text with Voice Activity Detection |
| `tts_mlx_module.py` | MLX-based TTS with streaming chunk generation |
| `brain_module_v2.py` | OpenClaw integration, acknowledgments, filler chat |
| `music_module.py` | Background music player (random tracks, volume control) |
| `filler_module.py` | SQLite-backed jokes and small talk |
| `config.py` | Configuration (loads from `.env`) |
| `list_devices.py` | Utility to find your microphone device index |

---

## 📋 Prerequisites

### Hardware
- **Mac with Apple Silicon** (M1/M2/M3/M4) — required for MLX
- **Microphone** — built-in, USB webcam mic, or external
- **Speakers** — for TTS output

### Software
- **macOS 13+** (Ventura or later)
- **Python 3.10+**
- **ffmpeg** — for audio processing
- **OpenClaw CLI** — installed and configured ([openclaw.ai](https://openclaw.ai))

---

## 🚀 Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/seshakiran/openclaw-audio-bridge.git
cd openclaw-audio-bridge
```

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install system dependencies

```bash
# ffmpeg (required for audio processing)
brew install ffmpeg
```

### 5. Configure your environment

```bash
# Copy the example env file
cp .env.example .env

# Find your microphone index
python list_devices.py

# Edit .env with your mic index
nano .env
```

### 6. Add background music (optional)

Place `.mp3` files in the `music/` directory. See [`music/README.md`](music/README.md) for recommended sources.

### 7. Verify OpenClaw is installed

```bash
# Make sure OpenClaw CLI is available
openclaw --version

# Test it works
openclaw agent --session-id agent:main:main --message "hello" --json
```

### 8. Run the assistant

```bash
python main_v2.py
```

You should see:

```
============================================================
🚀 Voice Assistant v2 - MLX TTS + VAD STT
============================================================
Loading TTS model...
MLX TTS model loaded! Sample rate: 24000
Loading STT model...
STT VAD Handler initialized (device: 2)
============================================================
🎙️  Voice Assistant Ready!
    Say 'Marvin' + your question
    Say 'Marvin stop' to interrupt
============================================================
```

---

## 🗣️ Usage

| Command | Action |
|---------|--------|
| **"Marvin, what's the news?"** | Sends question to OpenClaw |
| **"Marvin, stop"** | Interrupts current speech |
| **"Marvin, shutdown"** | Exits the assistant |
| **"Marvin"** (alone) | Assistant says "Yes?" and waits |

The assistant recognizes these wake word variants:
`marvin`, `marlin`, `martin`, `marving`, `marvel`, `marin`, `marben`, `marv`

---

## ⚙️ Configuration

All settings can be configured via `.env` or environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MICROPHONE_INDEX` | `0` | Audio input device index (run `python list_devices.py`) |
| `WHISPER_MODEL` | `base` | STT model: `tiny` (fast), `base` (balanced), `small` (accurate) |
| `TTS_MODEL` | `quality` | TTS model: `fast` (pocket-tts) or `quality` (Chatterbox-Turbo) |
| `OPENCLAW_SESSION_ID` | `agent:main:main` | OpenClaw session identifier |

### TTS Model Comparison

| Model | Speed | Quality | VRAM | Best For |
|-------|-------|---------|------|----------|
| `fast` (pocket-tts) | ~0.5x RT | Good | ~200MB | Short responses, low-end Macs |
| `quality` (Chatterbox-Turbo) | ~0.36x RT | Excellent | ~1.5GB | Long responses, ElevenLabs-like quality |

---

## 🔧 Troubleshooting

### "No speech detected"
- Run `python list_devices.py` and verify your `MICROPHONE_INDEX`
- Make sure your mic isn't muted in System Settings → Sound

### TTS sounds distorted
- Switch to `quality` model in `.env`: `TTS_MODEL=quality`
- The `fast` model can distort on long text

### Metal GPU crash
- This happens if two MLX operations run simultaneously
- The code uses locks to prevent this — if it still occurs, file an issue

### "command not found: openclaw"
- Install OpenClaw: follow the setup guide at [openclaw.ai](https://openclaw.ai)
- Make sure it's in your `PATH`

### Microphone picks up speaker audio (echo)
- The VAD + echo filter handles most cases
- For best results, use headphones or a directional microphone
- Adjust `SPEECH_COOLDOWN` in `main_v2.py` (default: 1.5 seconds)

---

## 📁 Project Structure

```
openclaw-audio-bridge/
├── main_v2.py              # 🎯 Main entry point
├── stt_vad_module.py        # 👂 Speech-to-text with VAD
├── tts_mlx_module.py        # 🗣️ MLX TTS (streaming chunks)
├── brain_module_v2.py       # 🧠 OpenClaw integration
├── music_module.py          # 🎵 Background music player
├── filler_module.py         # 💬 Jokes & small talk
├── config.py                # ⚙️ Configuration loader
├── list_devices.py          # 🎤 Audio device utility
├── tts_hybrid_module.py     # 🔄 Edge TTS fallback module
├── requirements.txt         # 📦 Python dependencies
├── .env.example             # 📝 Example environment config
├── music/                   # 🎵 Background music (add your own .mp3s)
│   └── README.md
└── data/                    # 💾 Auto-generated SQLite databases
```

---

## 🧪 Legacy Modules

These modules are included for reference and as alternative configurations:

| Module | Description |
|--------|-------------|
| `main.py` | Original main loop (uses ffmpeg recording, edge-tts) |
| `stt_module.py` | Original STT (ffmpeg-based recording, no VAD) |
| `tts_module.py` | Original TTS (Edge TTS only) |
| `brain_module.py` | Original brain (uses edge-tts imports) |
| `tts_hybrid_module.py` | Edge TTS with text cleaning (cloud-based fallback) |

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [MLX Audio](https://github.com/ml-explore/mlx-audio) — Apple's ML framework for audio
- [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) — CTranslate2-based Whisper
- [OpenClaw](https://openclaw.ai) — AI agent framework
- [WebRTC VAD](https://github.com/wiseman/py-webrtcvad) — Voice Activity Detection
- [Chatterbox TTS](https://huggingface.co/mlx-community/Chatterbox-Turbo-TTS-8bit) — Neural TTS model
