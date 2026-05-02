# PDF Agent — PDF-Constrained Conversational Agent

A retrieval-augmented agent that chats with you about an uploaded PDF, answering **only** from the document with page-level citations and explicitly refusing out-of-scope questions. Multilingual.

Built for STAIR Digital × Scaler School of Technology internship assessment, Task 3.

## Features

- **Strict grounding** — answers come only from the uploaded PDF; no training-knowledge leakage.
- **Two-stage refusal** — low-similarity questions are refused without an LLM call (fast + deterministic); the LLM is also prompted to refuse explicitly.
- **Page citations** — every factual claim cites `[Page X]`; the API also returns retrieved-chunk metadata (page + score + preview) so reviewers can audit grounding.
- **Multilingual** — Hindi, Spanish, etc. Embeddings (`gemini-embedding-2`) are multilingual; the prompt instructs the LLM to match the user's language.
- **Observability** — structured stdout logging on every upload, retrieval, and chat turn.
- **One-command eval** — `python tests/run_eval.py` runs 10 cases (5 valid + 3 invalid + 2 multilingual) and prints a PASS/FAIL table.

## Quick start

### Prerequisites

- Python 3.11+
- **Google AI Studio key** (embeddings only) — get one at <https://aistudio.google.com/apikey>
- **Groq API key** (chat LLM, free 14 400 req/day) — get one at <https://console.groq.com>

### Setup

```bash
# 1. clone and enter
cd pdf-agent

# 2. create venv
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. install
pip install -r requirements.txt

# 4. configure
cp .env.example .env
# edit .env and paste your GOOGLE_API_KEY (embeddings) and GROQ_API_KEY (chat)

# 5. run
python main.py
```

Open <http://localhost:8000>, drop a PDF, and ask away.

### Run with Docker

```bash
docker build -t pdf-agent .
docker run --rm -p 8000:8000 \
  -e GOOGLE_API_KEY=your_google_key \
  -e GROQ_API_KEY=your_groq_key \
  pdf-agent
```

### Run the test suite

In one terminal: `python main.py`. In another:

```bash
# place a sample PDF at tests/sample.pdf, then:
python tests/run_eval.py --pdf tests/sample.pdf
```

You should see all 10 cases PASS (after editing `tests/test_cases.json` valid-case questions to match your sample PDF).

## API

| Method | Path           | Purpose                                    |
|--------|----------------|--------------------------------------------|
| GET    | `/`            | Frontend                                   |
| GET    | `/api/health`  | Health probe (used by Render)              |
| GET    | `/api/status`  | Whether a PDF is loaded + filename + pages |
| POST   | `/api/upload`  | Upload a PDF (multipart `file`, max 20 MB) |
| POST   | `/api/chat`    | `{message, history?}` → grounded response  |
| POST   | `/api/reset`   | Clear PDF + conversation                   |

## Architecture

```
Browser  →  FastAPI
              │
              ├─ PDFProcessor  (pdfplumber, page-by-page text)
              ├─ TextChunker   (RecursiveCharacterTextSplitter, 800/200)
              ├─ VectorStore   (Chroma in-memory, cosine, Gemini embeddings)
              └─ PDFAgent      (Groq Llama 3.3 70B, two-stage refusal)
```

Detailed write-up: see [TECHNICAL_NOTE.md](TECHNICAL_NOTE.md).

## Deployment

The repo is Render-ready. Push to GitHub, create a new Web Service on Render pointing at the repo, and set both `GOOGLE_API_KEY` and `GROQ_API_KEY` as environment variables. `render.yaml` and the `Dockerfile` handle the rest.

> **Render free tier note**: cold starts take ~30 s. Hit `/api/health` first if the app has been idle.

## Project layout

```
pdf-agent/
├── main.py             FastAPI entrypoint
├── config.py           Tunables (model, thresholds, limits)
├── core/
│   ├── pdf_processor.py
│   ├── chunker.py
│   ├── vector_store.py
│   ├── prompts.py      System + query prompts (grounding rules)
│   ├── agent.py        Orchestration + two-stage refusal
│   └── logger.py
├── static/             Vanilla HTML / CSS / JS frontend
├── tests/
│   ├── test_cases.json 10 cases (5 valid + 3 invalid + 2 multilingual)
│   └── run_eval.py     One-command eval runner
├── Dockerfile
├── render.yaml
├── requirements.txt
├── TECHNICAL_NOTE.md
└── SUBMISSION.md       What evaluators need
```
