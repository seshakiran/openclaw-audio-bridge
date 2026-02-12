from faster_whisper import WhisperModel
import subprocess
import os
import time
import re

class STTHandler:
    def __init__(self, model_name="base", device_index="0", wake_word="marvin"):
        print(f"Loading Faster-Whisper model '{model_name}'...")
        # faster-whisper with int8 for speed
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
        self.device = f":{device_index}"
        self.wake_word = wake_word.lower()
        self.is_active = False
        self.temp_file = f"temp_audio_{model_name}.wav"

    def _record_audio(self, duration):
        """Record audio for specified duration."""
        if os.path.exists(self.temp_file):
            try:
                os.remove(self.temp_file)
            except:
                pass
        
        cmd = [
            "ffmpeg", "-y", "-f", "avfoundation", 
            "-i", self.device, "-t", str(duration),
            "-ar", "16000",
            "-ac", "1",
            "-loglevel", "quiet",
            self.temp_file
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, timeout=duration + 5)
            return os.path.exists(self.temp_file) and os.path.getsize(self.temp_file) > 5000
        except:
            return False

    def _transcribe(self):
        """Transcribe using faster-whisper with better settings."""
        if not os.path.exists(self.temp_file):
            return None
            
        try:
            # More permissive settings for better recognition
            segments, info = self.model.transcribe(
                self.temp_file, 
                language="en",
                beam_size=5,          # Higher = more accurate
                best_of=3,            # Consider multiple hypotheses
                temperature=0.0,      # Deterministic
                condition_on_previous_text=False,
                vad_filter=False,     # Disable VAD - was causing issues
                word_timestamps=False,
                without_timestamps=True,
            )
            
            # Combine segments
            texts = []
            for segment in segments:
                texts.append(segment.text.strip())
            
            text = " ".join(texts).strip()
            
            # Only filter obvious artifacts
            artifacts = ["", "thank you", "thanks for watching", "subscribe"]
            if not text or text.lower().strip() in artifacts:
                return None
            
            # Must have some letters
            if len(re.sub(r'[^a-zA-Z]', '', text)) < 2:
                return None

            return text
        except Exception as e:
            print(f"Transcribe error: {e}")
            return None

    def listen_and_transcribe_single(self, duration=3):
        """Record and transcribe a single chunk."""
        if self._record_audio(duration):
            text = self._transcribe()
            return text
        return None
    
    def listen_short(self):
        """2-second listen for interrupt detection."""
        return self.listen_and_transcribe_single(duration=2)
    
    def listen_normal(self):
        """3-second listen for commands."""
        return self.listen_and_transcribe_single(duration=3)
    
    def listen_long(self):
        """5-second listen for complete questions."""
        return self.listen_and_transcribe_single(duration=5)

    def listen_and_transcribe(self):
        """Original blocking loop."""
        wake_words = ["marvin", "marlin", "martin", "marving", "marvel"]
        
        while True:
            text = self.listen_and_transcribe_single()
            
            if not text:
                continue

            processed_text = text.lower()

            if not self.is_active:
                if any(word in processed_text for word in wake_words):
                    print(f"Wake word detected!")
                    self.is_active = True
                    
                    command = text
                    for word in wake_words:
                        if word in command.lower():
                            pattern = re.compile(re.escape(word) + r'[\s,:\-\.]*', re.IGNORECASE)
                            command = pattern.sub('', command, count=1).strip()
                            break
                    
                    if len(command) > 2:
                        return command
                    else:
                        from tts_module import speak_sync
                        speak_sync("Yes?")
                        continue
                else:
                    continue
            else:
                if any(end in processed_text for end in ["goodbye marvin", "exit", "that is all"]):
                    self.is_active = False
                
                return text
