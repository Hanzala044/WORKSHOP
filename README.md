# Four-Day AI & Web Development Workshop — Starter Projects

This repository contains four independent, runnable workshop modules:
1. Web scraping and product price comparison
2. LLM voice assistant using Groq, speech-to-text, and text-to-speech
3. Hand detection in Google Colab using OpenCV + MediaPipe
4. Document question answering using Retrieval-Augmented Generation (RAG)

## Important notes
- These are working starter implementations, not a claim that they use the exact libraries/models taught at your campus.
- Use websites only where scraping is permitted. Respect each site's terms, robots.txt, rate limits, and access controls. Do not bypass logins, CAPTCHAs, or anti-bot protections.
- Keep API keys private. Never commit `.env` files or paste keys into screenshots.
- Web scraping selectors differ by website. The scraper lets you configure CSS selectors for each supported page; inspect a page's HTML and adjust them.
- The voice assistant uses Groq for LLM responses, Google Web Speech through `SpeechRecognition` for transcription, and gTTS for spoken replies. These speech services may require internet access.
- The Colab hand-detection notebook processes an uploaded video file. Colab does not provide ordinary local webcam access in the same way a desktop Python script does.
- The RAG app uses local sentence-transformer embeddings and FAISS retrieval, then Groq for grounded answer generation.

## Suggested setup
Use Python 3.10 or 3.11 for the local Python modules. Create a separate virtual environment for each module to avoid dependency conflicts.

### Module 1
```bash
cd day1_price_comparator
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

### Module 2
```bash
cd day2_voice_assistant
python -m venv .venv
# Activate the environment, then:
pip install -r requirements.txt
```
Create `.env` from `.env.example`, add your Groq API key, then run:
```bash
python app.py
```
You may need to select the correct microphone/speaker and grant microphone permission.

### Module 3 — Google Colab
1. Open a new notebook at https://colab.research.google.com/
2. Copy the cells from `day3_hand_detection/colab_notebook.md` into separate Colab cells.
3. Run the install cell, upload a short video, and run the processing cell.
4. The annotated video is saved as `hand_detection_output.mp4`.

### Module 4
```bash
cd day4_rag_assistant
python -m venv .venv
# Activate the environment, then:
pip install -r requirements.txt
```
Create `.env` from `.env.example`, add your Groq API key, then run:
```bash
streamlit run app.py
```

## How to explain the modules
- Web scraping: sends an HTTP request, parses HTML, extracts configured fields, normalizes prices, and compares records.
- Voice assistant: records speech, transcribes it, sends text to an LLM API, and synthesizes the response as audio.
- Hand detection: OpenCV reads video frames; MediaPipe's open-source hand landmark model detects hand landmarks; OpenCV draws them.
- RAG: extracts document text, splits it into chunks, embeds chunks, retrieves the most relevant chunks for a question, and passes that context to an LLM to answer.

## Evaluation checklist
- [ ] Test with a small, permitted sample first.
- [ ] Capture screenshots of input, processing, and output.
- [ ] Record limitations and failed cases honestly.
- [ ] Do not claim model training if you only used a pre-trained model.
