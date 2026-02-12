#!/usr/bin/env python3
"""
Utility to list available audio input devices.
Use the device index in your .env file as MICROPHONE_INDEX.
"""

def list_devices():
    print("=" * 50)
    print("🎤 Available Audio Devices")
    print("=" * 50)
    
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        print(devices)
        
        print("\n" + "=" * 50)
        print("📌 Input Devices (microphones):")
        print("=" * 50)
        
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_input_channels'] > 0:
                default = " ← DEFAULT" if i == sd.default.device[0] else ""
                print(f"  [{i}] {dev['name']} ({dev['max_input_channels']} channels){default}")
        
        print(f"\n💡 Set MICROPHONE_INDEX in your .env file to the device number above.")
        
    except ImportError:
        print("sounddevice not installed. Run: pip install sounddevice")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_devices()
