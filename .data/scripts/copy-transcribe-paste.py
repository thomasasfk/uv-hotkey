#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "pyaudio>=0.2.13",
#   "openai>=1.0.0",
#   "pyperclip>=1.8.2",
#   "wave>=0.0.2",
#   "pydub>=0.25.1",
#   "keyboard>=0.13.5",
#   "anthropic>=0.16.0",
#   "python-dotenv>=1.0.0",
#   "google-genai>=0.3.0"
# ]
# ///
import os
import json
import time
import pyaudio
import wave
import pyperclip
import threading
import openai
import tempfile
import keyboard
import anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SCRIPT_NAME = Path(__file__).stem
LOCK_FILE = Path(tempfile.gettempdir()) / f"{SCRIPT_NAME}.mic_recording.lock"
OUTPUT_FILE = Path(tempfile.gettempdir()) / f"{SCRIPT_NAME}.recording.wav"
SELECTED_TEXT_FILE = Path(tempfile.gettempdir()) / f"{SCRIPT_NAME}.selected_text.txt"

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

CLAUDE_MODEL = "claude-3-sonnet-20240229"
GEMINI_MODEL = "gemini-1.5-pro"
USE_CLAUDE = os.environ.get("USE_CLAUDE", "0") == "1"
USE_GEMINI = os.environ.get("USE_GEMINI", "0") == "1"
DEFAULT_MODEL = "gemini" if USE_GEMINI and not USE_CLAUDE else "claude"


def is_recording():
    return LOCK_FILE.exists()


def set_recording_state(state):
    if state == "recording" and not LOCK_FILE.exists():
        LOCK_FILE.touch()
    elif state == "stop" and LOCK_FILE.exists():
        LOCK_FILE.unlink()


def save_selected_text():
    selected_text = pyperclip.paste()
    if selected_text:
        with open(SELECTED_TEXT_FILE, 'w', encoding='utf-8') as f:
            f.write(selected_text)
        return True
    return False


def record_audio():
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
            time.sleep(0.005)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

        if frames:
            wf = wave.open(str(OUTPUT_FILE), 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
            wf.close()

            return True
        return False


def transcribe_audio():
    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    with open(OUTPUT_FILE, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )

    return transcript.text


def get_ai_response(selected_text, instructions, model_choice="claude"):
    schema = {
        "type": "object",
        "required": ["modified_text"],
        "properties": {
            "modified_text": {
                "type": "string",
                "description": "The text after applying the requested modifications"
            }
        }
    }

    prompt = f"""
Here is some text:
```
{selected_text}
```

Instructions for modifying the text: {instructions}

IMPORTANT: Make only the minimum necessary changes to implement the instructions. If this is code:
1. Preserve the original structure - don't add wrappers, functions, or classes that weren't requested
2. Keep the same indentation and formatting style
3. The text may be part of a larger file - don't add imports or change scope
4. Return only the modified block of text, including indentation, quotation marks, etc.
"""

    if model_choice.lower() == "claude":
        return _get_claude_response(prompt, schema, CLAUDE_MODEL)
    elif model_choice.lower() == "gemini":
        return _get_gemini_response(prompt, schema, GEMINI_MODEL)
    else:
        raise ValueError(f"Unsupported model choice: {model_choice}")


def _get_claude_response(prompt, schema, model):
    if not CLAUDE_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    tools = [{
        "name": "get_structured_response",
        "description": "Generate the modified text based on instructions",
        "input_schema": schema
    }]

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}],
        tools=tools,
        tool_choice={"type": "tool", "name": "get_structured_response"}
    )

    if hasattr(response, 'content') and len(response.content) > 0:
        for content in response.content:
            if content.type == 'tool_use' and hasattr(content, 'input'):
                return content.input.get('modified_text', '')

    return "Error: Could not extract modified text from Claude response"


def _get_gemini_response(prompt, schema, model):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set.")

    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)

    response = client.models.generate_content(
        model=model,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        config={
            "temperature": 0.0,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 4000,
            "response_mime_type": "application/json",
            "response_schema": schema
        }
    )

    try:
        json_response = json.loads(response.text)
        return json_response.get("modified_text", "")
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        return "Error: Could not extract modified text from Gemini response"

def paste_text():
    time.sleep(0.5)
    keyboard.press_and_release('ctrl+v')


def copy_to_clipboard_and_paste(text):
    pyperclip.copy(text)
    print(f"Response copied to clipboard: {text[:50]}...")
    threading.Thread(target=paste_text).start()


def main():
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY environment variable not set.")
        return

    model_choice = DEFAULT_MODEL
    print(f"Using model: {model_choice.capitalize()} (set with USE_CLAUDE=1 or USE_GEMINI=1)")

    if model_choice.lower() == "claude" and not CLAUDE_API_KEY:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        return
    elif model_choice.lower() == "gemini" and not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY environment variable not set.")
        return

    if is_recording():
        set_recording_state("stop")
        print("Stopping recording...")
        time.sleep(0.2)

        if not SELECTED_TEXT_FILE.exists():
            print("No selected text was saved before recording started.")
            return

        try:
            transcription = transcribe_audio()
            print(f"Transcribed: {transcription[:50]}...")

            with open(SELECTED_TEXT_FILE, 'r', encoding='utf-8') as f:
                selected_text = f.read()

            print(f"Getting response from {model_choice.capitalize()}...")
            response = get_ai_response(selected_text, transcription, model_choice)

            copy_to_clipboard_and_paste(response)

            if SELECTED_TEXT_FILE.exists():
                SELECTED_TEXT_FILE.unlink()
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()

            print("Process completed successfully!")
        except Exception as e:
            print(f"Error processing: {e}")
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
        return

    print("Copying selected text...")
    keyboard.press_and_release('ctrl+c')
    time.sleep(0.1)

    if save_selected_text():
        print("Selected text saved. Starting recording...")
        record_audio()
    else:
        print("No text was selected. Please select text before running the script.")


if __name__ == "__main__":
    main()