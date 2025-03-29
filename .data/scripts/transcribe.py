#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "pyaudio>=0.2.13",
#   "openai>=1.0.0",
#   "pyperclip>=1.8.2",
#   "wave>=0.0.2",
#   "pydub>=0.25.1",
#   "keyboard>=0.13.5"
# ]
# ///
import os
import time
import pyaudio
import wave
import pyperclip
import threading
import openai
import tempfile
import keyboard
from pathlib import Path
from pydub import AudioSegment

# Use a lock file instead of a state file for better performance
LOCK_FILE = Path(tempfile.gettempdir()) / "mic_recording.lock"
OUTPUT_FILE = Path(tempfile.gettempdir()) / "recording.wav"

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
API_KEY = os.environ.get("OPENAI_API_KEY")


def is_recording():
    return LOCK_FILE.exists()


def set_recording_state(state):
    if state == "recording" and not LOCK_FILE.exists():
        LOCK_FILE.touch()
    elif state == "stop" and LOCK_FILE.exists():
        LOCK_FILE.unlink()


def record_audio():
    # Create a lightweight lock file instead of writing content
    set_recording_state("recording")

    p = pyaudio.PyAudio()
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    frames = []
    print("Recording started. Run the script again to stop recording.")

    try:
        while is_recording():
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
            # Reduced sleep time for better responsiveness
            time.sleep(0.005)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

        if frames:  # Only save if we recorded something
            wf = wave.open(str(OUTPUT_FILE), 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
            wf.close()

            return True
        return False


def transcribe_audio():
    client = openai.OpenAI(api_key=API_KEY)

    with open(OUTPUT_FILE, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )

    return transcript.text


def paste_text():
    time.sleep(0.5)
    keyboard.press_and_release('ctrl+v')


def copy_to_clipboard_and_paste(text):
    pyperclip.copy(text)
    print(f"Transcription copied to clipboard: {text[:50]}...")
    threading.Thread(target=paste_text).start()


def main():
    if not API_KEY:
        print("Error: OPENAI_API_KEY environment variable not set.")
        return

    if is_recording():
        set_recording_state("stop")
        print("Stopping recording...")
        time.sleep(0.2)
        return

    if not record_audio():
        return

    print("Recording stopped. Transcribing...")

    try:
        transcription = transcribe_audio()
        copy_to_clipboard_and_paste(transcription)
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
        print("Process completed successfully!")
    except Exception as e:
        print(f"Error during transcription: {e}")
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()


if __name__ == "__main__":
    main()