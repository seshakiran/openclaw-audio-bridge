"""
Brain module v2 - Uses MLX TTS.
"""

import subprocess
import json
import asyncio
from filler_module import filler
from music_module import music
import random
from tts_mlx_module import speak, speak_sync, stop_speech, is_speaking, wait_for_speech, clear_recent_texts
import time


class OpenClawBrain:
    def __init__(self, session_id="agent:main:main"):
        self.session_id = session_id

    async def process_command(self, text):
        """
        Sends the command to the OpenClaw agent and returns the response.
        Plays background music while waiting.
        """
        print(f"Sending to OpenClaw: {text}")
        
        # Initial acknowledgment - use sync to ensure it completes before music starts
        acknowledgments = [
            "Let me work on that.",
            "I'm on it.",
            "Looking into that now.",
            "On it!",
            "Give me a moment.",
        ]
        speak_sync(random.choice(acknowledgments))
        
        # Start background music while we work
        await asyncio.sleep(0.3)
        music.play(volume=0.4)
        
        # Start the OpenClaw process
        cmd = [
            "openclaw", "agent", 
            "--session-id", self.session_id, 
            "--message", text, 
            "--json"
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            claw_task = asyncio.create_task(process.communicate())
            
            # Occasionally add filler chat over the music
            filler_count = 0
            start_time = time.time()
            
            while not claw_task.done():
                done, pending = await asyncio.wait([claw_task], timeout=2.0)
                
                if not claw_task.done():
                    elapsed = time.time() - start_time
                    # Say one filler after ~15 seconds
                    if elapsed > 15 and filler_count == 0:
                        music.set_volume_low()
                        await asyncio.sleep(0.3)
                        
                        filler_text = filler.get_filler()
                        # Use sync speech to ensure it completes before continuing
                        speak_sync(filler_text)
                        
                        await asyncio.sleep(0.3)
                        music.set_volume_normal()
                        filler_count += 1
                else:
                    break

            # Stop music BEFORE generating TTS (prevents audio conflicts)
            print("OpenClaw responded.")
            music.stop()
            await asyncio.sleep(0.5)  # Give audio system time to settle
            
            # Process the response
            stdout, stderr = await claw_task
            stdout_str = stdout.decode().strip()
            
            json_start = stdout_str.find('{')
            if json_start == -1:
                return "I'm back, but I couldn't parse the response."

            json_str = stdout_str[json_start:]
            response_data = json.loads(json_str)
            
            payloads = response_data.get("result", {}).get("payloads", [])
            if payloads:
                response_text = " ".join([p.get("text", "") for p in payloads if p.get("text")])
                return f"Here's what I found. {response_text}"
            else:
                return "I checked, but didn't get a specific answer."

        except Exception as e:
            music.stop()
            print(f"Exception in process_command: {e}")
            return f"Sorry, I ran into trouble: {str(e)}"


brain = OpenClawBrain()
