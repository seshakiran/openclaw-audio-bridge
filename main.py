import asyncio
import threading
import queue
import time
from stt_module import STTHandler
from tts_module import speak, speak_sync, stop_speech, is_speaking, get_recent_texts, clear_recent_texts, wait_for_speech
from brain_module import brain
from music_module import music
import config
import re

# Single STT queue
stt_queue = queue.Queue()

# Single STT handler (avoid conflicts from two models)
stt_handler = None

# Mode tracking
current_mode = 'idle'  # 'idle', 'listening', 'processing', 'speaking'
mode_lock = threading.Lock()

# Speech output tracking - to prevent echo
speech_end_time = 0
speech_end_lock = threading.Lock()
SPEECH_COOLDOWN = 1.5  # Seconds to ignore input after speech ends

def set_mode(mode):
    global current_mode
    with mode_lock:
        current_mode = mode

def get_mode():
    global current_mode
    with mode_lock:
        return current_mode

def mark_speech_ended():
    """Mark that speech just ended for cooldown."""
    global speech_end_time
    with speech_end_lock:
        speech_end_time = time.time()

def in_speech_cooldown():
    """Check if we're in post-speech cooldown period."""
    global speech_end_time
    with speech_end_lock:
        return (time.time() - speech_end_time) < SPEECH_COOLDOWN

def is_wake_word(text):
    lower = text.lower()
    wake_words = ["marvin", "marlin", "martin", "marving", "marvel"]
    return any(word in lower for word in wake_words)

def is_stop_command(text):
    lower = text.lower()
    if not is_wake_word(text):
        return False
    stop_words = ["stop", "quiet", "shut up", "enough", "pause", "cancel", "hold", "wait"]
    return any(word in lower for word in stop_words)

def extract_command(text):
    wake_words = ["marvin", "marlin", "martin", "marving", "marvel"]
    command = text
    for word in wake_words:
        if word in command.lower():
            pattern = re.compile(re.escape(word) + r'[\s,:\-\.]*', re.IGNORECASE)
            command = pattern.sub('', command, count=1).strip()
            break
    return command

def is_echo(text):
    """Check if text is an echo of recent assistant speech."""
    recent = get_recent_texts()
    if not recent:
        return False
    
    text_lower = text.lower()
    text_clean = re.sub(r'[^a-z0-9]', '', text_lower)
    
    # Very short text is likely noise/echo
    if len(text_clean) < 5:
        return True
    
    # Known filler/acknowledgment phrases that TTS says
    tts_phrases = [
        "let me work", "i'm on it", "looking into", "on it", "give me a moment",
        "here's what i found", "i found", "working on", "let me go",
        "close enough", "robot", "yes", "stopped", "goodbye"
    ]
    for phrase in tts_phrases:
        if phrase in text_lower:
            return True
    
    heard_words = set(re.findall(r'\w+', text_lower))
    stop_words = {'the', 'is', 'at', 'on', 'and', 'a', 'to', 'of', 'it', 'in', 'i', 'you', 
                  'my', 'an', 'be', 'for', 'that', 'this', 'are', 'was', 'have', 'do', 
                  'but', 'or', 'as', 'if', 'so', 'just', 'about', 'your', 'can', 'all',
                  'there', 'what', 'when', 'who', 'how', 'them', 'here', 'found',
                  'now', 'into', 'looking', 'moment', 'give', 'me', 'let', 'work',
                  'okay', 'sure', 'right', 'well', 'yes', 'no', 'good', 'got'}
    heard_keywords = heard_words - stop_words
    
    # Too few meaningful words = likely echo
    if len(heard_keywords) < 2:
        return True
    
    for spoken in recent:
        spoken_words = set(re.findall(r'\w+', spoken.lower()))
        spoken_keywords = spoken_words - stop_words
        
        # Specific terms indicate echo
        specific_terms = {'nvidia', 'amd', 'microsoft', 'alphabet', 'amazon', 'meta',
                         'palantir', 'broadcom', 'taiwan', 'micron', 'kiran', 'karen',
                         'stock', 'stocks', 'nebius', 'salesforce', 'goldman', 'tesla',
                         'trump', 'budget', 'system', 'processes', 'crashed', 'humming',
                         'robot', 'chanting', 'typing', 'phase', 'evening', 'emoji',
                         'analogies', 'mixing'}
        
        overlap = heard_keywords.intersection(spoken_keywords)
        specific_overlap = overlap.intersection(specific_terms)
        
        if specific_overlap:
            return True
        # More aggressive: 2+ keyword overlap = echo
        if len(overlap) >= 2:
            return True
    
    return False

def stt_thread_func(stt):
    """Single STT thread - adjusts recording duration based on mode."""
    while True:
        try:
            mode = get_mode()
            
            # During speaking or processing, only do short listens for interrupt detection
            if mode in ['speaking', 'processing']:
                result = stt.listen_short()
            else:
                result = stt.listen_normal()
            
            if result:
                # Skip if in post-speech cooldown (prevents echo)
                if in_speech_cooldown() and not is_wake_word(result):
                    print(f"  (ignored during cooldown: {result[:40]}...)")
                    continue
                    
                # Skip obvious echoes during/after speech
                if (is_speaking() or in_speech_cooldown()) and is_echo(result):
                    print(f"  (echo filtered: {result[:40]}...)")
                    continue
                
                print(f"Heard: {result}")
                stt_queue.put(result)
        except Exception as e:
            print(f"STT error: {e}")
            time.sleep(1)

async def get_complete_command(stt, initial_command):
    """Get complete command if it seems cut off."""
    if len(initial_command) > 15:
        return initial_command
    
    if re.search(r'[.?!]$', initial_command.strip()):
        return initial_command
    
    # Complete-sounding endings
    complete_endings = ['please', 'now', 'today', 'me', 'you', 'it', 'that', 'stocks', 
                       'news', 'weather', 'doing', 'going', 'up', 'down']
    if any(initial_command.lower().strip().endswith(word) for word in complete_endings):
        return initial_command
    
    print(f"(Waiting for more...)")
    
    loop = asyncio.get_event_loop()
    continuation = await loop.run_in_executor(None, stt.listen_long)
    
    if continuation:
        if is_wake_word(continuation):
            # New command
            stt_queue.put(continuation)
            return initial_command
        
        if not is_echo(continuation):
            full = f"{initial_command} {continuation}"
            print(f"Complete: {full}")
            return full
    
    return initial_command

async def main():
    global stt_handler
    
    # Use base model - good balance of speed and accuracy
    stt_handler = STTHandler(model_name="base", device_index=config.MICROPHONE_INDEX)
    
    # Start single STT thread
    stt_thread = threading.Thread(target=stt_thread_func, args=(stt_handler,), daemon=True)
    stt_thread.start()
    
    print("=" * 60)
    print("🎙️  Voice Assistant Ready!")
    print("    Say 'Marvin' + your question")
    print("    Say 'Marvin stop' to interrupt")
    print("=" * 60)

    running = True
    try:
        while running:
            # Get from queue
            try:
                heard = stt_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
            
            if not heard:
                continue
            
            # Priority: Stop command
            if is_stop_command(heard):
                print(f"\n🛑 STOP: '{heard}'")
                stop_speech()
                music.stop()
                clear_recent_texts()
                set_mode('idle')
                speak_sync("Stopped.")
                mark_speech_ended()
                continue
            
            # Wake word detected
            if is_wake_word(heard):
                stop_speech()
                music.stop()
                clear_recent_texts()
                
                command = extract_command(heard)
                
                if len(command) > 2:
                    set_mode('listening')
                    
                    full_command = await get_complete_command(stt_handler, command)
                    
                    print(f"\n👤 User: {full_command}")
                    
                    # Exit commands
                    if any(word in full_command.lower() for word in ["shutdown", "exit", "goodbye"]):
                        speak_sync("Goodbye!")
                        running = False
                        continue
                    
                    # Process
                    set_mode('processing')
                    response = await brain.process_command(full_command)
                    
                    if response:
                        set_mode('speaking')
                        speak(response)
                        
                        # Allow interrupts while speaking
                        while is_speaking():
                            # Check queue for stop commands
                            try:
                                interrupt_text = stt_queue.get_nowait()
                                if is_stop_command(interrupt_text):
                                    print(f"\n🛑 STOP: '{interrupt_text}'")
                                    stop_speech()
                                    music.stop()
                                    clear_recent_texts()
                                    mark_speech_ended()
                                    speak_sync("Stopped.")
                                    mark_speech_ended()
                                    break
                                elif is_wake_word(interrupt_text):
                                    # New command
                                    print(f"\n🔄 New command detected")
                                    stop_speech()
                                    music.stop()
                                    clear_recent_texts()
                                    mark_speech_ended()
                                    stt_queue.put(interrupt_text)
                                    break
                            except queue.Empty:
                                pass
                            await asyncio.sleep(0.1)
                        
                        mark_speech_ended()
                        set_mode('idle')
                else:
                    # Just wake word
                    if not is_speaking():
                        speak_sync("Yes?")
                        mark_speech_ended()
                
                continue
            
            # No wake word - check if echo during speech
            if is_speaking() and is_echo(heard):
                continue
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        stop_speech()
        music.stop()

if __name__ == "__main__":
    from filler_module import filler 
    asyncio.run(main())
