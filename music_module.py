import subprocess
import os
import random
import threading
import time

class MusicPlayer:
    """
    Background music player using afplay (macOS native).
    Supports volume control and fade effects.
    """
    
    def __init__(self, music_dir="music"):
        self.music_dir = music_dir
        self.current_process = None
        self.is_playing = False
        self.current_volume = 0.5
        self._stop_fade = False
        self._lock = threading.Lock()
        
        # Get list of mp3 files
        self.tracks = self._load_tracks()
        print(f"Music player loaded {len(self.tracks)} tracks")
    
    def _load_tracks(self):
        """Load all mp3 files from the music directory."""
        tracks = []
        if os.path.exists(self.music_dir):
            for f in os.listdir(self.music_dir):
                if f.endswith('.mp3') and not f.startswith('.'):
                    tracks.append(os.path.join(self.music_dir, f))
        return tracks
    
    def _stop_internal(self):
        """Internal stop without lock - called from within locked context."""
        self._stop_fade = True
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=1)
            except:
                try:
                    self.current_process.kill()
                except:
                    pass
        self.current_process = None
        self.is_playing = False
        
        # Kill any lingering afplay processes for music
        try:
            import subprocess
            subprocess.run(["pkill", "-f", "afplay.*music"], capture_output=True, timeout=1)
        except:
            pass
    
    def play(self, volume=0.5):
        """
        Start playing a random track at specified volume.
        Volume: 0.0 to 1.0
        Uses macOS afplay for reliable playback.
        """
        if not self.tracks:
            print("No music tracks available")
            return
        
        with self._lock:
            # Stop any current playback first
            self._stop_internal()
            
            track = random.choice(self.tracks)
            self.current_volume = volume
            
            try:
                cmd = ["afplay", "-v", str(volume), track]
                self.current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self.is_playing = True
                print(f"🎵 Playing: {os.path.basename(track)[:40]}... (vol: {int(volume*100)}%)")
            except Exception as e:
                print(f"Could not play music: {e}")
    
    def stop(self):
        """Stop the current track immediately."""
        with self._lock:
            self._stop_internal()
    
    def fade_out(self, duration=2.0, callback=None):
        """
        Fade out by stopping after a delay.
        Note: afplay doesn't support live volume changes, so we just delay then stop.
        """
        self._stop_fade = False
        
        def _fade():
            steps = int(duration / 0.1)
            for _ in range(steps):
                if self._stop_fade:
                    break
                time.sleep(0.1)
            
            self.stop()
            print("🎵 Music faded out")
            
            if callback:
                try:
                    callback()
                except:
                    pass
        
        thread = threading.Thread(target=_fade, daemon=True)
        thread.start()
    
    def set_volume_low(self):
        """Restart at lower volume for background during speech."""
        if self.is_playing and self.tracks:
            self.play(volume=0.15)
    
    def set_volume_normal(self):
        """Restart at normal volume."""
        if self.is_playing and self.tracks:
            self.play(volume=0.4)
    
    def playing(self):
        """Check if music is currently playing."""
        with self._lock:
            if self.current_process and self.current_process.poll() is not None:
                self.is_playing = False
            return self.is_playing


# Global instance
music = MusicPlayer()


if __name__ == "__main__":
    print("Testing music player...")
    music.play(volume=0.3)
    time.sleep(3)
    print("Stopping...")
    music.stop()
    print("Done")
