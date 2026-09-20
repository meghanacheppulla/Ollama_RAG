# Filmography Lens (streamlit_ollama)

A fully local Streamlit PDF question-answering app. Upload a PDF, index its text, and ask questions that are answered by a local Ollama model using passages retrieved from the PDF.

## Requirements

- Python 3.10+ (Windows, macOS or Linux)
- [Ollama](https://ollama.com) installed and running locally
- `llama3.2:latest` downloaded once

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
ollama pull llama3.2:latest
ollama serve
```

Keep `ollama serve` running in one window. In a second window:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

Streamlit prints a local address, usually `http://localhost:8501`.

## Setup (macOS / Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ollama pull llama3.2:latest
ollama serve &
streamlit run app.py
```

## Use it

1. Upload a PDF.
2. Click **Index this PDF**.
3. Type a question in the prompt box.
4. Click **Enter → Find the answer**.

PyMuPDF extracts the text and a local keyword retriever picks the best passages. Answers are instructed to use only those excerpts and show page references.

## Scanned PDFs

If the PDF is only images, no text can be extracted. Run OCR first, then upload the searchable version.

## Changing the model

Type any installed model name in the model field (see `ollama list`).

## Colours

The theme lives in two places: the `:root` CSS variables at the top of `app.py` and `.streamlit/config.toml`.
