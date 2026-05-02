# Technical Note — PDF-Constrained Conversational Agent

## 1. Problem framing

Build an agent that answers a user's questions about an arbitrary uploaded PDF, with three hard constraints: (a) responses must be grounded **only** in the document, (b) the agent must explicitly refuse out-of-scope questions, and (c) responses must include verifiable page citations. Bonus: support multiple languages with consistent grounding.

The core risk in this kind of system is **silent hallucination** — the model knows things from its training data and will happily blend them with retrieved context, eroding the document-grounded contract.

## 2. Architecture

```
        ┌──────────────┐
Browser │  static/*    │  vanilla HTML/CSS/JS, no build step
        └──────┬───────┘
               │ HTTP (JSON / multipart)
        ┌──────▼─────────────────────────────────────────────┐
        │ FastAPI (main.py)                                  │
        │  /api/upload  /api/chat  /api/status  /api/reset   │
        │  /api/health  + request_id middleware              │
        └──────┬─────────────────────────────────────────────┘
               │
        ┌──────▼─────────────────────────────┐
        │ PDFAgent (core/agent.py)           │
        │  ─ ingest:                         │
        │     PDFProcessor → TextChunker     │
        │     → VectorStore.index            │
        │  ─ chat:                           │
        │     VectorStore.search             │
        │     → two-stage refusal gate       │
        │     → Groq (Llama 3.3 70B) w/       │
        │       system prompt (6 abs. rules) │
        │     → citation extraction          │
        └──────┬─────────────────────────────┘
               │
   ┌───────────▼──────────────┐    ┌──────────────────────────┐
   │ Chroma (in-memory)       │    │ Google AI (embeddings)   │
   │  cosine, HNSW            │    │  gemini-embedding-2      │
   │  langchain-chroma        │    ├──────────────────────────┤
   └──────────────────────────┘    │ Groq (chat LLM)          │
                                   │  llama-3.3-70b-versatile │
                                   └──────────────────────────┘
```

## 3. Hallucination prevention — four layers

1. **System prompt** with six numbered absolute rules (see `core/prompts.py`). Rule 1 forbids using any knowledge other than the provided context. Rule 3 specifies the exact refusal string to emit on out-of-scope questions.
2. **Two-stage refusal gate** in `PDFAgent.chat`:
   - Stage 1 (no LLM call): if the top retrieval score is below `RELEVANCE_HARD_FLOOR=0.25`, return the canonical refusal directly. Saves tokens, eliminates a class of LLM-tempting "almost relevant" prompts.
   - Stage 2 (LLM): retrieved chunks are concatenated with their page numbers and relevance scores so the model can self-assess; the prompt instructs it to emit the exact refusal phrase if context doesn't answer.
3. **Citations are extracted from the response** (`[Page X]` regex), so a response without any cite is detectable as a likely refusal/empty-grounding case.
4. **Retrieved-chunk metadata is returned to the client** alongside the LLM response (`sources`: top-3 `{page, score, preview}`). This makes the grounding **auditable**: a reviewer can verify what the model was *given*, not just what it said.

## 4. Multi-language approach

- Embeddings (`models/gemini-embedding-2`) are natively multilingual, so retrieval works across Hindi, Spanish, etc. without translation hops.
- Rule 4 in the system prompt instructs the LLM to **match the question's language** in its response.
- Citations stay in the ASCII `[Page X]` form — easier to render and parse, and matches how the brief specifies citations should look.
- The eval suite includes one Hindi and one Spanish case; `run_eval.py` checks that the response actually contains Devanagari script (Hindi) or Spanish-typical characters/words (Spanish).

## 5. Why these specific choices

| Choice | Rationale |
|---|---|
| **Groq (Llama 3.3 70B Versatile)** | Completely free tier with 14,400 requests/day — no billing required. Llama 3.3 70B follows structured citation instructions reliably and handles multilingual prompts well. Groq's inference hardware delivers sub-second latency on typical RAG contexts. |
| **gemini-embedding-2** | Multilingual out of the box (Hindi/Spanish bonus task), 3072-dim vectors, free on AI Studio. Only called on PDF upload (not every chat turn), so the embedding quota is rarely stressed. `text-embedding-004` is not accessible on the AI Studio free tier — `gemini-embedding-2` is the correct current model. |
| **Chroma in-memory** | Zero infra. Upload → index → query in seconds; a fresh Render dyno is ready in one upload step. Trade-off: state lost on container restart — acceptable for a demo, not for production. |
| **pdfplumber** | Preserves page boundaries cleanly (critical for citations), fewer surprises than PyPDF2 on tables/columns. No OCR — scanned PDFs would need a Tesseract pass; out of scope here. |
| **RecursiveCharacterTextSplitter, 800/200** | Standard "respect-paragraphs-then-sentences" chunker. 800-char chunks fit comfortably in Llama 3.3's context; 200-char overlap preserves cross-boundary context. |
| **Vanilla HTML/CSS/JS** | No build step → faster iteration, smaller image, no Node toolchain in Docker. |
| **FastAPI + Uvicorn** | Async I/O, automatic OpenAPI docs at `/docs`, first-class file upload, dead simple to deploy in a single container. |

## 6. Observability

Every meaningful step emits a structured log line via `core/logger.log_event`:

```
2026-05-01 23:21:09 INFO  core.pdf_processor | event=pdf_extracted filename=foo.pdf pages=12 skipped=0 ms=843
2026-05-01 23:21:10 INFO  core.chunker       | event=chunked pages=12 chunks=47
2026-05-01 23:21:14 INFO  core.vector_store  | event=indexed collection=pdf-7e2a9b1c docs=47 ms=3812
2026-05-01 23:21:22 INFO  core.vector_store  | event=search top_k=5 scores=[0.71, 0.62, 0.41, 0.18, 0.12] ms=204
2026-05-01 23:21:24 INFO  core.agent         | event=chat q_preview=What is... max_score=0.71 strong_count=2 is_refusal=false citations=[3, 7] ms=2103
```

A request ID middleware tags every HTTP request and includes its latency, so a single `grep rid=<id>` traces a request end-to-end.

## 7. Trade-offs and what I'd improve

| Limitation today | What I'd do with more time |
|---|---|
| In-memory Chroma — restart loses index | Persistent volume on Render or move to a hosted vector DB (Pinecone, Weaviate). |
| Single global agent instance, single conversation | Per-user session IDs and per-session histories; trivial to add. |
| No re-ranking of retrieved chunks | Add a cross-encoder reranker (e.g., bge-reranker) before passing to the LLM — measurably lifts grounded-QA quality. |
| No OCR for scanned PDFs | Tesseract fallback when pdfplumber yields too little text. |
| No automated grounding eval | Add a "golden answer" set per sample PDF + faithfulness scoring (RAGAS-style). |
| API has no auth or rate limiting | Behind a real deployment, add API key middleware + per-IP token bucket. |
| Refusal is a hard string match | Move to a small classifier or LLM-judge for nuanced "partially relevant" cases. |
| Chunk size and `RELEVANCE_HARD_FLOOR` are static | Per-PDF tuning based on document statistics (length, density, language). |

## 8. Failure modes I considered

- **Scanned PDF with no extractable text** → `PDFProcessor.process` returns an empty list; `process_pdf` raises `ValueError("No extractable text found in PDF.")`; the API returns 422. The frontend shows the message inline.
- **PDF > 20 MB** → API rejects with 413; frontend pre-checks too.
- **LLM API outage / quota exhaustion** → caught in `agent.chat`, returns a friendly error message with `is_refusal=true` so the UI shows it as a non-answer rather than crashing. Groq's free tier (14,400 RPD) is generous enough that quota exhaustion is unlikely during normal demo use.
- **Question lexically similar to the PDF but actually off-topic** (e.g., "Tell me a story about..." when the PDF is technical) → Stage 2 catches this: the model is told to emit the canonical refusal phrase if context doesn't actually answer, and the prompt makes the bar explicit.
- **LLM drops the `[Page X]` citation** → response still surfaces correctly because the API also returns `sources`, so the UI can show retrieved-chunk metadata even when in-text citations are missing.
