"""
MLX-based TTS module using Chatterbox-Turbo.
ElevenLabs-quality voice synthesis running locally on Apple Silicon.

Features:
- Streams audio in chunks (play while generating next chunk)
- Truncates long responses to spoken-friendly length
- Cleans markdown/emojis before speaking
"""

import subprocess
import threading
import time
import tempfile
import os
import re
import numpy as np

# Lazy load MLX models
_model = None
_model_lock = threading.Lock()
_generation_lock = threading.Lock()

_current_process = None
_stop_requested = False
_current_text = ""
_recent_spoken_texts = []
_recent_lock = threading.Lock()
_temp_dir = tempfile.gettempdir()

# Model config
MODELS = {
    'fast': 'mlx-community/pocket-tts',
    'quality': 'mlx-community/Chatterbox-Turbo-TTS-8bit',
}
DEFAULT_MODEL = 'quality'

# Max characters to speak (prevents 2+ minute TTS for huge responses)
MAX_SPOKEN_LENGTH = 600


def _clean_text_for_tts(text):
    """Clean text for TTS - remove emojis, markdown, special chars."""
    # Remove emojis
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        u"\U0001F900-\U0001F9FF"
        u"\U0001FA00-\U0001FA6F"
        u"\U0001FA70-\U0001FAFF"
        u"\U00002600-\U000026FF"
        u"\U00002700-\U000027BF"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub('', text)

    # Remove markdown
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^\s*[-*•]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)

    # Fix dashes and quotes
    text = text.replace('—', ' - ').replace('–', ' - ')
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2018', "'").replace('\u2019', "'")

    # Percentages and currency
    text = re.sub(r'(\d+\.?\d*)%', r'\1 percent', text)
    text = re.sub(r'\$(\d+)B', r'\1 billion dollars', text)
    text = re.sub(r'\$(\d+)', r'\1 dollars', text)

    # Newlines to periods
    text = re.sub(r'\n+', '. ', text)

    # Remove non-ASCII
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)

    # Clean whitespace/punctuation
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\.+', '.', text)
    text = re.sub(r'\s*\.\s*', '. ', text)

    return text.strip()


def _truncate_for_speech(text):
    """Truncate long text to a spoken-friendly length, ending at a sentence boundary."""
    if len(text) <= MAX_SPOKEN_LENGTH:
        return text

    # Find a sentence boundary near the limit
    truncated = text[:MAX_SPOKEN_LENGTH]
    # Look for last sentence end
    last_period = truncated.rfind('. ')
    last_question = truncated.rfind('? ')
    last_excl = truncated.rfind('! ')
    cut_point = max(last_period, last_question, last_excl)

    if cut_point > MAX_SPOKEN_LENGTH * 0.4:
        truncated = truncated[:cut_point + 1]
    
    # Add a note that there's more
    truncated += " There's more detail available if you'd like."
    return truncated


def _split_into_chunks(text, max_length=250):
    """Split text into chunks at sentence boundaries for streaming."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_length:
            current = f"{current} {sentence}".strip() if current else sentence
        else:
            if current:
                chunks.append(current)
            if len(sentence) > max_length:
                # Force split long sentences at commas or spaces
                while len(sentence) > max_length:
                    cut = sentence[:max_length].rfind(', ')
                    if cut < max_length * 0.3:
                        cut = sentence[:max_length].rfind(' ')
                    if cut < 1:
                        cut = max_length
                    chunks.append(sentence[:cut])
                    sentence = sentence[cut:].strip(' ,')
                current = sentence
            else:
                current = sentence
    if current:
        chunks.append(current)
    return chunks


def _get_model(model_key=None):
    """Lazy-load the MLX TTS model."""
    global _model
    if model_key is None:
        model_key = DEFAULT_MODEL
    model_path = MODELS.get(model_key, model_key)

    with _model_lock:
        if _model is None:
            print(f"Loading MLX TTS model: {model_path}...")
            os.environ.pop('HF_TOKEN', None)
            os.environ.pop('HUGGING_FACE_HUB_TOKEN', None)
            from mlx_audio.tts import load
            _model = load(model_path)
            print(f"MLX TTS model loaded! Sample rate: {_model.sample_rate}")
        return _model


def _generate_chunk_audio(model, text):
    """Generate audio for one text chunk. Returns numpy array or None."""
    try:
        audio_parts = []
        for result in model.generate(text):
            if hasattr(result, 'audio') and result.audio is not None:
                data = np.array(result.audio)
                if len(data) > 0:
                    audio_parts.append(data)
        if audio_parts:
            return np.concatenate(audio_parts)
    except Exception as e:
        print(f"  Chunk TTS error: {e}")
    return None


def _play_audio_file(filepath):
    """Play audio file with afplay. Returns the Popen process."""
    return subprocess.Popen(
        ["afplay", filepath],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def _speak_streamed(text):
    """
    Generate and play audio in streaming chunks.
    Generates chunk N+1 while playing chunk N.
    """
    global _current_process, _stop_requested
    import soundfile as sf
    import mlx.core as mx

    cleaned = _clean_text_for_tts(text)
    if not cleaned:
        return

    truncated = _truncate_for_speech(cleaned)
    chunks = _split_into_chunks(truncated)

    with _generation_lock:
        model = _get_model()
        temp_files = []

        try:
            for i, chunk in enumerate(chunks):
                if _stop_requested:
                    break

                chunk = chunk.strip()
                if not chunk:
                    continue

                # Generate audio for this chunk
                audio = _generate_chunk_audio(model, chunk)
                mx.eval([])

                if audio is None or len(audio) == 0:
                    continue

                # Save to temp file
                tf = os.path.join(_temp_dir, f"tts_chunk_{os.getpid()}_{i}.wav")
                sf.write(tf, audio, model.sample_rate)
                temp_files.append(tf)

                if _stop_requested:
                    break

                # Play this chunk
                _current_process = _play_audio_file(tf)
                _current_process.wait()

        finally:
            # Cleanup temp files
            for tf in temp_files:
                try:
                    os.remove(tf)
                except:
                    pass


def speak(text, interruptible=True):
    """Non-blocking speech. Streams chunks in background thread."""
    global _current_process, _current_text, _stop_requested
    if not text:
        return

    stop_speech()
    time.sleep(0.05)

    _stop_requested = False
    _current_text = text

    with _recent_lock:
        _recent_spoken_texts.append(text)
        if len(_recent_spoken_texts) > 5:
            _recent_spoken_texts.pop(0)

    print(f"Assistant: {text}")

    def _thread():
        try:
            _speak_streamed(text)
        except Exception as e:
            print(f"TTS thread error: {e}")
            # Fallback
            global _current_process
            _current_process = subprocess.Popen(['say', '-r', '180', _clean_text_for_tts(text)[:500]])
            _current_process.wait()

    threading.Thread(target=_thread, daemon=True).start()


def speak_sync(text):
    """Synchronous speech - blocks until complete."""
    global _current_text, _stop_requested
    if not text:
        return

    stop_speech()
    time.sleep(0.05)

    _stop_requested = False
    _current_text = text

    with _recent_lock:
        _recent_spoken_texts.append(text)
        if len(_recent_spoken_texts) > 5:
            _recent_spoken_texts.pop(0)

    print(f"Assistant: {text}")

    try:
        _speak_streamed(text)
    except Exception as e:
        print(f"TTS error: {e}")
        subprocess.run(['say', '-r', '180', _clean_text_for_tts(text)[:500]])


def speak_and_wait(text):
    speak_sync(text)


def wait_for_speech():
    global _current_process
    if _current_process:
        try:
            _current_process.wait()
        except:
            pass


def stop_speech():
    """Stop current speech immediately."""
    global _current_process, _current_text, _stop_requested
    _stop_requested = True
    _current_text = ""
    if _current_process and _current_process.poll() is None:
        try:
            _current_process.terminate()
            _current_process.wait(timeout=1)
        except:
            try:
                _current_process.kill()
            except:
                pass
    _current_process = None


def get_current_text():
    return _current_text if is_speaking() else ""


def get_recent_texts():
    with _recent_lock:
        return list(_recent_spoken_texts)


def clear_recent_texts():
    global _recent_spoken_texts
    with _recent_lock:
        _recent_spoken_texts.clear()


def is_speaking():
    global _current_process
    return _current_process is not None and _current_process.poll() is None


def preload_model(model_key=None):
    _get_model(model_key)


if __name__ == "__main__":
    print("Testing MLX TTS streaming...")
    preload_model()

    # Short
    print("\n--- Short text ---")
    speak_sync("Hello! I am Marvin.")

    # Long (simulated news)
    print("\n--- Long news text ---")
    long_text = """Here's what I found. **Today's News** (Feb 11, 2026):

**Breaking:** School shooting in Canada — Tumbler Ridge, police identify suspect.

**Politics:** Pam Bondi hearing — Still testifying at House Judiciary Committee, clashing with lawmakers over Epstein files.

**Economy:** Mortgage rates — 30-year around 6.87%. Jobs report shows 130,000 jobs added in January.

**International:** Gaza conflict dominating global diplomacy. EU pushing new trade agreements. 484 migrants dead in Mediterranean.

**Science:** SpaceX Crew-12 launch targeting Feb 20. China showcased new moon ship. James Webb found rich organic chemistry in nearby galaxy.

**AI:** OpenAI dropped GPT-5.3. Anthropic upgraded Claude. Google released Gemini 3. Big 4 planning 600 billion dollar AI investment.

**TL;DR:** Jobs look good but 2025 was flat. Immigration tensions rising. Gaza dominant crisis. Space race heating up. AI wars continue.

Want me to dig deeper into anything?"""

    speak_sync(long_text)
    print("\nDone!")
