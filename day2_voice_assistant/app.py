"""Voice-to-LLM-to-speech demo using Groq, SpeechRecognition and gTTS."""
import os
import tempfile
from pathlib import Path

import speech_recognition as sr
from dotenv import load_dotenv
from groq import Groq
from gtts import gTTS

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not api_key:
    raise SystemExit("Missing GROQ_API_KEY. Copy .env.example to .env and add your key.")

client = Groq(api_key=api_key)
recognizer = sr.Recognizer()


def ask_llm(prompt):
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful educational voice assistant. Answer clearly and concisely."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4,
        max_tokens=500,
    )
    return completion.choices[0].message.content.strip()


def speak(text):
    audio = gTTS(text=text, lang="en")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp:
        path = Path(temp.name)
    audio.save(str(path))
    print(f"Speech audio saved to: {path}")
    # Open the generated audio with your default player when supported.
    try:
        if os.name == "nt":
            os.startfile(str(path))
        elif os.uname().sysname == "Darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}" >/dev/null 2>&1')
    except Exception:
        print("Could not auto-play. Open the MP3 file manually.")


def main():
    print("AI Voice Assistant")
    print("Press Enter to speak. Type 'text' to enter a prompt, or 'quit' to exit.")
    while True:
        choice = input("\nMode [Enter=voice / text / quit]: ").strip().lower()
        if choice == "quit":
            break
        if choice == "text":
            prompt = input("You: ").strip()
        else:
            try:
                with sr.Microphone() as source:
                    print("Calibrating microphone for background noise...")
                    recognizer.adjust_for_ambient_noise(source, duration=0.6)
                    print("Speak now...")
                    audio = recognizer.listen(source, timeout=8, phrase_time_limit=20)
                prompt = recognizer.recognize_google(audio)
                print(f"Recognized: {prompt}")
            except sr.WaitTimeoutError:
                print("No speech detected. Try again.")
                continue
            except sr.UnknownValueError:
                print("Speech could not be understood. Try again or use text mode.")
                continue
            except sr.RequestError as exc:
                print(f"Speech recognition service error: {exc}")
                continue
            except Exception as exc:
                print(f"Microphone error: {exc}")
                print("Try text mode or check microphone/PyAudio setup.")
                continue

        if not prompt:
            continue
        try:
            answer = ask_llm(prompt)
            print(f"\nAssistant: {answer}")
            speak(answer)
        except Exception as exc:
            print(f"LLM or TTS error: {exc}")


if __name__ == "__main__":
    main()
