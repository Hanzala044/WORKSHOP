# Day 2 — LLM Voice Assistant

## Flow
Microphone → speech-to-text → prompt → Groq-hosted LLM → text response → gTTS audio.

## Setup
1. Install Python 3.10 or 3.11.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Add your Groq API key. Never share or commit `.env`.
5. Run `python app.py`.

### Notes
- SpeechRecognition's Google recognizer sends audio to an online service. It requires internet and may not be appropriate for private audio.
- PyAudio can be difficult to install on some systems. If microphone mode fails, use `text` mode to test the Groq and TTS stages independently.
- Model availability can change in Groq. If the configured model is not available to your account, set `GROQ_MODEL` to a currently supported chat model in your Groq console.
- gTTS needs internet access. The generated MP3 is saved to a temporary file and the script attempts to open it with your system's default audio player.
