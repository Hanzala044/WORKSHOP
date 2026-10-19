# Day 4 — Retrieval-Augmented Generation (RAG)

## Setup
1. Use Python 3.10 or 3.11.
2. Install dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and add your Groq API key.
4. Run `streamlit run app.py`.

The first run downloads the `all-MiniLM-L6-v2` embedding model. Internet access is required for initial setup and for Groq answer generation.

## Pipeline
1. Extract text from PDF/TXT.
2. Split text into overlapping chunks.
3. Embed chunks as vectors using Sentence Transformers.
4. Store/search vectors with FAISS using cosine-like similarity (normalized vectors with inner product).
5. Retrieve top relevant chunks for the question.
6. Send the retrieved context and question to Groq.
7. Ask the LLM to answer only from the supplied context and say when the document does not contain the answer.

## Limitations
- Scanned PDFs may contain no selectable text; OCR would be a separate step.
- Chunk length and overlap affect retrieval quality.
- Similarity scores are relevance indicators, not guarantees of correctness.
- RAG reduces unsupported answers but cannot guarantee zero hallucinations. Verify important answers against the source document.
- Uploaded content is processed by this app and relevant chunks are sent to the configured LLM provider. Do not upload confidential documents unless you have permission.
