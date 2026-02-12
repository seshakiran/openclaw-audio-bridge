"""
Hybrid TTS module - Uses Edge TTS for reliability, with MLX as backup.
Edge TTS is fast, reliable, and sounds great.
"""

import subprocess
import threading
import time
import tempfile
import os
import re

_current_process = None
_current_text = ""
_recent_spoken_texts = []
_recent_lock = threading.Lock()
_temp_dir = tempfile.gettempdir()

# Edge TTS voice settings
VOICE = "en-US-GuyNeural"  # Good male voice
RATE = "+5%"


def _clean_text_for_tts(text):
    """Clean text for TTS - remove emojis, markdown, etc."""
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
    
    # Fix dashes
    text = text.replace('—', ' - ')
    text = text.replace('–', ' - ')
    
    # Replace special quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    
    # Clean whitespace
    text = re.sub(r'\n+', '. ', text)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def _generate_audio_file(text):
    """Generate audio file using edge-tts CLI."""
    audio_file = os.path.join(_temp_dir, f"tts_{os.getpid()}_{int(time.time()*1000)}.mp3")
    
    # Clean text
    cleaned = _clean_text_for_tts(text)
    if not cleaned:
        return None
    
    try:
        result = subprocess.run(
            ["edge-tts", "--voice", VOICE, "--rate", RATE, "--text", cleaned, "--write-media", audio_file],
            capture_output=True,
            timeout=60
        )
        if result.returncode == 0 and os.path.exists(audio_file):
            return audio_file
    except Exception as e:
        print(f"Edge-TTS error: {e}")
    
    return None


def speak(text, interruptible=True):
    """
    Speaks text using Edge TTS.
    Non-blocking - returns immediately while speech plays.
    """
    global _current_process, _current_text, _recent_spoken_texts
    if not text:
        return
    
    stop_speech()
    time.sleep(0.1)
    
    _current_text = text
    
    with _recent_lock:
        _recent_spoken_texts.append(text)
        if len(_recent_spoken_texts) > 5:
            _recent_spoken_texts.pop(0)
    
    print(f"Assistant: {text}")
    
    def _speak_thread():
        global _current_process
        try:
            audio_file = _generate_audio_file(text)
            
            if audio_file and os.path.exists(audio_file):
                _current_process = subprocess.Popen(
                    ["afplay", audio_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                _current_process.wait()
                try:
                    os.remove(audio_file)
                except:
                    pass
            else:
                # Fallback to macOS say
                _current_process = subprocess.Popen(['say', '-r', '180', _clean_text_for_tts(text)])
                _current_process.wait()
        except Exception as e:
            print(f"TTS thread error: {e}")
    
    thread = threading.Thread(target=_speak_thread, daemon=True)
    thread.start()


def speak_sync(text):
    """Synchronous speech - blocks until complete."""
    global _current_process, _current_text, _recent_spoken_texts
    if not text:
        return
    
    stop_speech()
    time.sleep(0.1)
    
    _current_text = text
    
    with _recent_lock:
        _recent_spoken_texts.append(text)
        if len(_recent_spoken_texts) > 5:
            _recent_spoken_texts.pop(0)
    
    print(f"Assistant: {text}")
    
    try:
        audio_file = _generate_audio_file(text)
        
        if audio_file and os.path.exists(audio_file):
            _current_process = subprocess.Popen(
                ["afplay", audio_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            _current_process.wait()
            try:
                os.remove(audio_file)
            except:
                pass
        else:
            subprocess.run(['say', '-r', '180', _clean_text_for_tts(text)])
    except Exception as e:
        print(f"TTS error: {e}")
        subprocess.run(['say', '-r', '180', _clean_text_for_tts(text)])


def speak_and_wait(text):
    """Speaks text and blocks until complete."""
    speak_sync(text)


def wait_for_speech():
    """Blocks until current speech is complete."""
    global _current_process
    if _current_process:
        try:
            _current_process.wait()
        except:
            pass


def stop_speech():
    """Stop current speech immediately. Only kills the TTS afplay, not music."""
    global _current_process, _current_text
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
    global _current_text
    return _current_text if is_speaking() else ""


def get_recent_texts():
    global _recent_spoken_texts
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
    """No-op for compatibility - Edge TTS doesn't need preloading."""
    pass


if __name__ == "__main__":
    print("Testing Edge TTS...")
    
    test_text = """Here's what I found. Today's News February 11, 2026. 
Breaking: School shooting in Canada. 
Politics: Pam Bondi hearing at House Judiciary Committee.
Economy: Mortgage rates around 6.87 percent.
Want me to dig into any of these?"""
    
    print(f"\nSpeaking: {test_text[:50]}...")
    speak_sync(test_text)
    print("Done!")
