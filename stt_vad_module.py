"""
Improved STT module with Voice Activity Detection (VAD).
Uses sounddevice for low-latency recording and webrtcvad for speech detection.
This reduces echo issues by only processing audio with actual speech.
"""

from faster_whisper import WhisperModel
import sounddevice as sd
import numpy as np
import webrtcvad
import collections
import os
import tempfile
import soundfile as sf
import re
import time

class STTVADHandler:
    def __init__(self, model_name="base", device_index=None, wake_word="marvin"):
        print(f"Loading Faster-Whisper model '{model_name}'...")
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
        
        # Audio settings
        self.sample_rate = 16000
        self.frame_duration_ms = 30  # VAD frame size
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)
        
        # Device setup
        if device_index is not None:
            try:
                self.device = int(device_index)
            except (ValueError, TypeError):
                self.device = None
        else:
            self.device = None  # Use default
        
        # VAD setup - aggressiveness 0-3 (3 = most aggressive)
        self.vad = webrtcvad.Vad(2)
        
        # State
        self.wake_word = wake_word.lower()
        self.is_active = False
        self.temp_dir = tempfile.gettempdir()
        
        # For tracking when we're outputting speech (to ignore echo)
        self._output_active = False
        self._output_end_time = 0
        self._echo_cooldown = 1.5  # seconds
        
        print(f"STT VAD Handler initialized (device: {self.device})")

    def set_output_active(self, active):
        """Call this when TTS starts/stops to help filter echo."""
        self._output_active = active
        if not active:
            self._output_end_time = time.time()

    def _in_echo_window(self):
        """Check if we're in the echo danger zone."""
        if self._output_active:
            return True
        return (time.time() - self._output_end_time) < self._echo_cooldown

    def _record_with_vad(self, max_duration=5.0, min_speech_duration=0.3, 
                         silence_timeout=1.5, pre_speech_buffer=0.3):
        """
        Record audio using VAD to detect speech boundaries.
        Returns audio data only if speech was detected.
        """
        frames = []
        speech_frames = []
        triggered = False
        speech_start_time = None
        last_speech_time = None
        
        # Ring buffer for pre-speech audio
        pre_speech_frames = int(pre_speech_buffer * 1000 / self.frame_duration_ms)
        ring_buffer = collections.deque(maxlen=pre_speech_frames)
        
        start_time = time.time()
        
        def callback(indata, frame_count, time_info, status):
            nonlocal triggered, speech_start_time, last_speech_time
            
            if status:
                pass  # Ignore status warnings
            
            # Convert to int16 for VAD
            audio_int16 = (indata[:, 0] * 32767).astype(np.int16)
            
            # Process in VAD frame sizes
            for i in range(0, len(audio_int16) - self.frame_size + 1, self.frame_size):
                frame = audio_int16[i:i + self.frame_size].tobytes()
                
                try:
                    is_speech = self.vad.is_speech(frame, self.sample_rate)
                except:
                    is_speech = False
                
                frame_float = indata[i:i + self.frame_size, 0].copy()
                
                if not triggered:
                    ring_buffer.append(frame_float)
                    if is_speech:
                        triggered = True
                        speech_start_time = time.time()
                        last_speech_time = speech_start_time
                        # Include pre-speech buffer
                        speech_frames.extend(list(ring_buffer))
                        speech_frames.append(frame_float)
                else:
                    speech_frames.append(frame_float)
                    if is_speech:
                        last_speech_time = time.time()
        
        # Start recording
        try:
            with sd.InputStream(
                device=self.device,
                channels=1,
                samplerate=self.sample_rate,
                blocksize=self.frame_size * 4,  # Process multiple frames at once
                callback=callback
            ):
                while True:
                    elapsed = time.time() - start_time
                    
                    # Check timeout conditions
                    if elapsed >= max_duration:
                        break
                    
                    if triggered:
                        # Check silence timeout
                        silence_duration = time.time() - (last_speech_time or start_time)
                        if silence_duration >= silence_timeout:
                            break
                        
                        # Check minimum speech duration
                        speech_duration = time.time() - (speech_start_time or start_time)
                        if speech_duration >= max_duration * 0.8:
                            break
                    
                    time.sleep(0.05)
        
        except Exception as e:
            print(f"Recording error: {e}")
            return None
        
        # Check if we got enough speech
        if not triggered:
            return None
        
        speech_duration = (last_speech_time or start_time) - (speech_start_time or start_time)
        if speech_duration < min_speech_duration:
            return None
        
        # Concatenate speech frames
        if speech_frames:
            audio = np.concatenate(speech_frames)
            return audio
        
        return None

    def _transcribe(self, audio):
        """Transcribe audio array using faster-whisper."""
        if audio is None or len(audio) < self.sample_rate * 0.3:
            return None
        
        # Save to temp file
        temp_file = os.path.join(self.temp_dir, f"stt_vad_{os.getpid()}.wav")
        try:
            sf.write(temp_file, audio, self.sample_rate)
            
            segments, info = self.model.transcribe(
                temp_file,
                language="en",
                beam_size=5,
                best_of=3,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=False,
                word_timestamps=False,
                without_timestamps=True,
            )
            
            texts = []
            for segment in segments:
                texts.append(segment.text.strip())
            
            text = " ".join(texts).strip()
            
            # Filter artifacts
            artifacts = ["", "thank you", "thanks for watching", "subscribe"]
            if not text or text.lower().strip() in artifacts:
                return None
            
            if len(re.sub(r'[^a-zA-Z]', '', text)) < 2:
                return None
            
            return text
            
        except Exception as e:
            print(f"Transcribe error: {e}")
            return None
        finally:
            try:
                os.remove(temp_file)
            except:
                pass

    def listen_short(self):
        """Short listen for interrupt detection (2 seconds max)."""
        if self._in_echo_window():
            time.sleep(0.5)  # Reduce CPU during echo window
            return None
        
        audio = self._record_with_vad(
            max_duration=2.0,
            min_speech_duration=0.2,
            silence_timeout=0.5
        )
        return self._transcribe(audio)

    def listen_normal(self):
        """Normal listen for commands (4 seconds max)."""
        audio = self._record_with_vad(
            max_duration=4.0,
            min_speech_duration=0.3,
            silence_timeout=1.0
        )
        return self._transcribe(audio)

    def listen_long(self):
        """Long listen for complete questions (8 seconds max)."""
        audio = self._record_with_vad(
            max_duration=8.0,
            min_speech_duration=0.3,
            silence_timeout=2.0
        )
        return self._transcribe(audio)

    def listen_and_transcribe_single(self, duration=3):
        """Compatibility method - record and transcribe."""
        audio = self._record_with_vad(
            max_duration=duration,
            min_speech_duration=0.3,
            silence_timeout=1.0
        )
        return self._transcribe(audio)


if __name__ == "__main__":
    print("Testing STT with VAD...")
    
    handler = STTVADHandler(model_name="base", device_index=0)
    
    print("\nSpeak something (listening for 5 seconds)...")
    for i in range(3):
        text = handler.listen_normal()
        if text:
            print(f"Heard: {text}")
        else:
            print("(no speech detected)")
    
    print("Done!")
