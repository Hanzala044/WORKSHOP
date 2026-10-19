"""Small document-grounded RAG demo: PDF/TXT -> chunks -> embeddings -> FAISS -> Groq."""
import os
from pathlib import Path

import faiss
import numpy as np
import streamlit as st
from dotenv import load_dotenv
from groq import Groq
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

load_dotenv()
st.set_page_config(page_title="Workshop RAG Assistant", page_icon="📄")
st.title("Document Q&A — Retrieval-Augmented Generation")
st.write("Upload a PDF or TXT file, then ask a question grounded in that document.")

API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

@st.cache_resource
def get_embedder():
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def extract_text(uploaded_file):
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(uploaded_file)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    if suffix == ".txt":
        return uploaded_file.getvalue().decode("utf-8", errors="replace")
    raise ValueError("Please upload a PDF or TXT file.")

def chunk_text(text, chunk_size=900, overlap=150):
    text = " ".join(text.split())
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks

def build_index(chunks, embedder):
    vectors = embedder.encode(
        chunks,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False
    ).astype("float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    return index

def retrieve(question, chunks, index, embedder, k=4):
    query_vector = embedder.encode(
        [question], convert_to_numpy=True, normalize_embeddings=True
    ).astype("float32")
    scores, indices = index.search(query_vector, min(k, len(chunks)))
    return [(chunks[int(i)], float(score)) for score, i in zip(scores[0], indices[0]) if i >= 0]

def generate_answer(question, retrieved):
    if not API_KEY:
        raise RuntimeError("Missing GROQ_API_KEY. Copy .env.example to .env and add your key.")
    context = "\n\n".join(
        f"[Source chunk {i+1}]\n{chunk}" for i, (chunk, _) in enumerate(retrieved)
    )
    client = Groq(api_key=API_KEY)
    result = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "Answer using only the supplied document context. "
                    "If the answer is not present, say you could not find it in the uploaded document. "
                    "Do not invent facts. Mention the relevant source chunk number(s) when possible."
                )
            },
            {
                "role": "user",
                "content": f"DOCUMENT CONTEXT:\n{context}\n\nQUESTION:\n{question}"
            }
        ],
        temperature=0.1,
        max_tokens=700,
    )
    return result.choices[0].message.content.strip()

uploaded = st.file_uploader("Upload a document", type=["pdf", "txt"])

if uploaded:
    try:
        document_text = extract_text(uploaded)
        chunks = chunk_text(document_text)
        if not chunks:
            st.error("No extractable text found. A scanned PDF may need OCR first.")
            st.stop()

        st.success(f"Extracted text and created {len(chunks)} chunks.")
        with st.expander("Preview first chunk"):
            st.write(chunks[0])

        with st.spinner("Loading embedding model and building search index..."):
            embedder = get_embedder()
            index = build_index(chunks, embedder)

        question = st.text_input("Ask a question about the uploaded document")
        if st.button("Get answer", type="primary", disabled=not question.strip()):
            with st.spinner("Retrieving relevant chunks and generating answer..."):
                retrieved = retrieve(question, chunks, index, embedder)
                st.subheader("Answer")
                try:
                    st.write(generate_answer(question, retrieved))
                except Exception as exc:
                    st.error(str(exc))
                with st.expander("Retrieved context (for transparency)"):
                    for i, (chunk, score) in enumerate(retrieved, start=1):
                        st.markdown(f"**Chunk {i} · similarity {score:.3f}**")
                        st.write(chunk)
    except Exception as exc:
        st.error(f"Could not process this document: {exc}")
else:
    st.info("Upload a text-based PDF or TXT document to begin.")
