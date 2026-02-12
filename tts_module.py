import subprocess
import threading
import time
import tempfile
import os

_current_process = None
_current_text = ""
_recent_spoken_texts = []
_recent_lock = threading.Lock()
_temp_dir = tempfile.gettempdir()

# Edge TTS voice settings
VOICE = "en-US-GuyNeural"
RATE = "+5%"

def _generate_audio_file(text):
    """Generate audio file using edge-tts CLI (avoids async issues)."""
    audio_file = os.path.join(_temp_dir, f"tts_{threading.current_thread().ident}.mp3")
    
    try:
        # Use edge-tts command line tool instead of async API
        result = subprocess.run(
            ["edge-tts", "--voice", VOICE, "--rate", RATE, "--text", text, "--write-media", audio_file],
            capture_output=True,
            timeout=30
        )
        if result.returncode == 0 and os.path.exists(audio_file):
            return audio_file
    except Exception as e:
        print(f"Edge-TTS error: {e}")
    
    return None

def speak(text, interruptible=True):
    """
    Speaks text using Microsoft Edge TTS.
    Non-blocking - returns immediately while speech plays.
    """
    global _current_process, _current_text, _recent_spoken_texts
    if not text:
        return
    
    stop_speech()
    
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
                # Cleanup
                try:
                    os.remove(audio_file)
                except:
                    pass
            else:
                # Fallback to macOS say
                _current_process = subprocess.Popen(['say', '-r', '180', text])
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
            # Fallback
            subprocess.run(['say', '-r', '180', text])
    except Exception as e:
        print(f"TTS error: {e}")
        subprocess.run(['say', '-r', '180', text])

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
    """Stop current speech immediately."""
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
    
    # Kill any afplay
    try:
        subprocess.run(["pkill", "-9", "afplay"], capture_output=True, timeout=1)
    except:
        pass

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


if __name__ == "__main__":
    print("Testing Edge TTS...")
    speak_sync("Hello! This is a test of Microsoft Edge neural text to speech.")
    print("Done!")
