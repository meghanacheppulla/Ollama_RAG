from __future__ import annotations

import html
import re
from collections import Counter
from typing import Any

try:
    import pymupdf as fitz  # PyMuPDF (new name)
except ImportError:  # older PyMuPDF versions
    import fitz
import requests
import streamlit as st

OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_URL = f"{OLLAMA_BASE}/api/generate"
DEFAULT_MODEL = "llama3.2:latest"
STOP_WORDS = {
    "a", "about", "after", "all", "also", "an", "and", "are", "as", "at", "be",
    "been", "before", "being", "but", "by", "can", "did", "do", "does", "for",
    "from", "had", "has", "have", "he", "her", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "me", "more", "most", "my", "no", "not", "of",
    "on", "or", "our", "she", "so", "some", "than", "that", "the", "their", "them",
    "there", "these", "they", "this", "to", "too", "was", "we", "were", "what", "when",
    "where", "which", "who", "will", "with", "would", "you", "your",
}

st.set_page_config(page_title="PDF Whisper", page_icon="🤫", layout="wide")

# Colour palette: light blue background, navy ink, blue + pink accents.
st.markdown(
    """
    <style>
    :root {
        --ink:#14213d; --muted:#5a6b85; --paper:#d6e6fb;
        --accent:#2563eb; --accent-2:#db2777; --line:#c7d8ee; --card:#fde7f1;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    .block-container { max-width: 1180px; padding-top: 2.2rem; }
    h1, h2, h3, h4, p, label { font-family: Georgia, 'Times New Roman', serif; color: var(--ink); }
    h1 { font-size: clamp(2.5rem, 6vw, 5rem); line-height: .95; letter-spacing: -0.04em; margin-bottom: .8rem; }
    h2 { letter-spacing: -0.02em; }
    .kicker { color: var(--accent); font-family: Consolas, 'Courier New', monospace; font-size: .78rem; text-transform: uppercase; letter-spacing: .12em; }
    .subhead { color: var(--muted); font-size: 1.1rem; max-width: 680px; line-height: 1.55; }
    .rule { border-top: 1px solid var(--line); margin: 1.8rem 0; }
    .panel { border: 1px solid var(--line); background: var(--card); padding: 1.1rem 1.25rem; border-radius: 6px; margin-top: .8rem; }
    .answer { border-left: 5px solid var(--accent-2); background: var(--card); padding: 1.25rem 1.4rem; line-height: 1.7; font-size: 1.04rem; border-radius: 0 6px 6px 0; white-space: pre-wrap; }
    .source { border-top: 1px solid var(--line); padding: .8rem 0; color: var(--muted); font-size: .9rem; }
    .source strong { color: var(--accent-2); }
    .metric { font-family: Consolas, 'Courier New', monospace; font-size: .8rem; color: var(--muted); }
    .stButton > button { background: var(--accent); color: #ffffff; border: 0; border-radius: 4px; font-family: Georgia, 'Times New Roman', serif; font-weight: 600; padding: .7rem 1.2rem; }
    .stButton > button:hover { background: var(--accent-2); color: #ffffff; }
    .stButton > button p { color: #ffffff; }
    [data-testid="stFileUploader"] { border: 1px dashed var(--accent); background: var(--card); padding: .4rem; border-radius: 6px; }
    [data-testid="stFileUploaderDropzone"] { background: var(--card); border-radius: 6px; }
    [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"] { background: var(--card); }
    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea { background: var(--card); border: 1px solid var(--line); border-radius: 4px; color: var(--ink); }
    [data-testid="stTextArea"] textarea::placeholder { color: var(--muted); opacity: 1; }
    </style>
    """,
    unsafe_allow_html=True,
)


def tokenize(text: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-zA-Z0-9']+", text.lower())
        if word not in STOP_WORDS and len(word) > 2
    ]


def extract_chunks(pdf_bytes: bytes, chunk_words: int = 180, overlap: int = 35) -> list[dict[str, Any]]:
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks: list[dict[str, Any]] = []
    try:
        for page_number, page in enumerate(document, start=1):
            text = " ".join(page.get_text("text").split())
            if not text:
                continue
            words = text.split()
            start = 0
            while start < len(words):
                end = min(start + chunk_words, len(words))
                chunk_text = " ".join(words[start:end])
                chunks.append({"page": page_number, "text": chunk_text, "terms": Counter(tokenize(chunk_text))})
                if end == len(words):
                    break
                start = end - overlap
    finally:
        document.close()
    return chunks


def rank_chunks(chunks: list[dict[str, Any]], question: str, limit: int = 5) -> list[dict[str, Any]]:
    query_terms = Counter(tokenize(question))
    normalized_question = question.lower().strip()
    scored = []
    for chunk in chunks:
        overlap_score = sum(
            min(query_terms[term], count) for term, count in chunk["terms"].items() if term in query_terms
        )
        phrase_bonus = 2 if normalized_question and normalized_question in chunk["text"].lower() else 0
        scored.append((overlap_score + phrase_bonus, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    useful = [chunk for score, chunk in scored if score > 0]
    return (useful or [chunk for _, chunk in scored])[:limit]


def ask_ollama(question: str, context_chunks: list[dict[str, Any]], model: str) -> str:
    context = "\n\n".join(f"[Page {chunk['page']}] {chunk['text']}" for chunk in context_chunks)
    prompt = f"""You answer questions about a PDF using only the supplied excerpts.
If the excerpts do not contain the answer, say exactly that the PDF does not provide enough information.
Do not invent film titles, dates, roles, awards, or biographical details.
Include every directly relevant fact from the excerpts, especially release date, language, setting, genre, character, and plot when those facts are present.
Use page references like (Page 3) when making a claim. Answer in a short paragraph or bullets, not just one sentence.

PDF EXCERPTS:
{context}

QUESTION:
{question}

ANSWER:"""
    response = requests.post(
        OLLAMA_URL,
        json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}},
        timeout=180,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("response", "").strip() or "Ollama returned an empty answer."


def safe(text: str) -> str:
    """Escape text so PDF/model content can never break the page HTML."""
    return html.escape(str(text))


if "chunks" not in st.session_state:
    st.session_state.chunks = []
if "file_name" not in st.session_state:
    st.session_state.file_name = ""

st.markdown('<div class="kicker">LOCAL PDF INTELLIGENCE / OLLAMA POWERED</div>', unsafe_allow_html=True)
st.title("PDF Whisper")
st.markdown(
    '<p class="subhead">Ask grounded questions about your uploaded PDF. Your document stays on this computer, '
    "and answers come from its extracted pages.</p>",
    unsafe_allow_html=True,
)
st.markdown('<div class="rule"></div>', unsafe_allow_html=True)

left, right = st.columns([1.05, 1.6], gap="large")

with left:
    st.markdown("### 01 / Add your source")
    uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"], label_visibility="collapsed")
    if uploaded_file:
        st.caption(f"Ready: {uploaded_file.name}")
        if st.button("Index this PDF", use_container_width=True):
            with st.spinner("Extracting pages and building a local index..."):
                try:
                    st.session_state.chunks = extract_chunks(uploaded_file.getvalue())
                    st.session_state.file_name = uploaded_file.name
                except Exception as error:  # corrupted / encrypted PDF
                    st.session_state.chunks = []
                    st.session_state.file_name = ""
                    st.error(f"Could not read this PDF: {error}")
                else:
                    if st.session_state.chunks:
                        st.success(f"Indexed {len(st.session_state.chunks)} passages.")
                    else:
                        st.warning("No selectable text was found. This may be a scanned PDF; OCR is needed first.")
    if st.session_state.chunks:
        st.markdown(
            f'<div class="panel"><div class="metric">ACTIVE SOURCE</div>'
            f"<strong>{safe(st.session_state.file_name)}</strong><br>"
            f'<span class="metric">{len(st.session_state.chunks)} passages ready for retrieval</span></div>',
            unsafe_allow_html=True,
        )
    st.markdown("### 02 / Choose your local model")
    model = st.text_input(
        "Ollama model",
        value=DEFAULT_MODEL,
        help="Use llama3.2:latest or another model already installed in Ollama.",
    )
    st.caption("Ollama must be running at 127.0.0.1:11434. No internet API is used.")

with right:
    st.markdown("### 03 / Ask the document")
    question = st.text_area(
        "Prompt",
        placeholder="Which films did Prabhas act in between 2010 and 2015?",
        height=125,
        label_visibility="collapsed",
    )
    ask = st.button("Enter  →  Find the answer", use_container_width=True)
    if ask:
        model_name = model.strip() or DEFAULT_MODEL
        if not st.session_state.chunks:
            st.warning("Upload and index a PDF first.")
        elif not question.strip():
            st.warning("Enter a question about the PDF.")
        else:
            matches = rank_chunks(st.session_state.chunks, question)
            with st.spinner("Reading the most relevant pages locally..."):
                try:
                    answer = ask_ollama(question.strip(), matches, model_name)
                except requests.exceptions.ConnectionError:
                    answer = "Ollama is not reachable. Start it with `ollama serve`, then try again."
                except requests.exceptions.Timeout:
                    answer = "Ollama took too long to respond. Try a smaller model or ask again."
                except requests.exceptions.HTTPError as error:
                    if error.response is not None and error.response.status_code == 404:
                        answer = f"The model `{model_name}` is not installed. Run `ollama pull {model_name}` and try again."
                    else:
                        answer = f"Ollama returned an error: {error}"
                except (requests.RequestException, ValueError) as error:
                    answer = f"Could not contact Ollama: {error}"
            st.markdown('<div class="kicker">RESPONSE / GROUNDED IN YOUR PDF</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="answer">{safe(answer)}</div>', unsafe_allow_html=True)
            st.markdown("#### Retrieved pages")
            for chunk in matches:
                preview = chunk["text"][:220] + ("..." if len(chunk["text"]) > 220 else "")
                st.markdown(
                    f'<div class="source"><strong>Page {chunk["page"]}</strong> &nbsp; {safe(preview)}</div>',
                    unsafe_allow_html=True,
                )

st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
st.caption(
    "Local-first workflow: PDF extraction and retrieval happen in this app; "
    "Ollama generates the final response on your machine."
)
