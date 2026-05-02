# Submission — PDF-Constrained Conversational Agent (Task 3)

**Candidate:** Kushal Talati — kushal.talati@scaler.com
**Submission to:** yashwardhansinghrathore1@gmail.com (CC: saraffshubham@gmail.com)

---

## Deliverables checklist

- [x] Working agent system (this repo)
- [x] Short technical note → [TECHNICAL_NOTE.md](TECHNICAL_NOTE.md)
- [x] Test instructions for evaluators → this file, section "How to test"
- [x] Demo video → https://youtu.be/HIZGAao6Emk
- [x] Deployed interface → https://pdf-agent-hkd1.onrender.com
- [x] Sample PDF → `tests/sample.pdf` *(replace with your chosen sample before submission)*
- [x] 5 valid + 3 invalid + 2 multilingual queries → `tests/test_cases.json`
- [x] Bonus: multi-language support (Hindi + Spanish demonstrated)

---

## Live URLs

- **Repo:** https://github.com/netram75/Assignment_Project
- **Live demo:** https://pdf-agent-hkd1.onrender.com — health check at https://pdf-agent-hkd1.onrender.com/api/health
- **Demo video:** https://youtu.be/HIZGAao6Emk

---

## How to test (for evaluators)

### Option A — One command, Docker

```bash
docker build -t pdf-agent .
docker run --rm -p 8000:8000 \
  -e GROQ_API_KEY=YOUR_GROQ_KEY \
  pdf-agent
# open http://localhost:8000
```

### Option B — Local Python

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
echo "GROQ_API_KEY=YOUR_GROQ_KEY" > .env
python main.py
# open http://localhost:8000
```

### Manual testing flow

1. Drop `tests/sample.pdf` into the upload zone (or any PDF you have).
2. Try one valid query → expect a substantive answer with `Page X` chips.
3. Try `What is the weather today?` → expect the canonical refusal message.
4. Try the Hindi query from `tests/test_cases.json` → expect a response in Hindi (Devanagari script) with English-bracket citations.

### Automated eval

While the server is running, in a separate terminal:

```bash
python tests/run_eval.py --url https://pdf-agent-hkd1.onrender.com
```

Output: a PASS/FAIL table for all 10 cases, exit code 0 if every case passes.

> Note: the 5 "valid" questions and 2 multilingual questions in `tests/test_cases.json` are written specifically for `tests/sample.pdf` (a 2-page ML introduction document). All 10 cases pass.

---

## What we built — at a glance

- FastAPI backend, **Groq Llama 3.3 70B** (chat, free 14 400 req/day via `langchain-groq`) + **local all-MiniLM-L6-v2 ONNX** embeddings (bundled with ChromaDB — no API key needed), Chroma in-memory vector store via `langchain-chroma`, pdfplumber for parsing.
- **Two-stage refusal**: similarity threshold gate before any LLM call, then a strict system prompt with six numbered absolute rules.
- **Auditable grounding**: API returns retrieved chunks (page + score + preview) alongside the LLM response, so reviewers can verify what the model was *given*, not just what it said.
- **Structured logging** on every step (extract → chunk → index → search → chat) with request IDs and per-stage latency.
- Vanilla HTML/CSS/JS frontend (no build step, glassmorphism dark UI, drag-and-drop upload, citation chips, source attribution panel).
- Ready to deploy on Render free tier (`render.yaml` + `Dockerfile` + `/api/health`).

For full architecture, design choices, trade-offs, and failure-mode analysis: [TECHNICAL_NOTE.md](TECHNICAL_NOTE.md).

---

## Demo video script (3–5 min)

1. **Project overview (30s)** — repo tree, point at `core/`, `static/`, `tests/`.
2. **Strict prompt (30s)** — open `core/prompts.py`, scroll through the 6 rules.
3. **Two-stage refusal (30s)** — open `core/agent.py`, point at `RELEVANCE_HARD_FLOOR` check vs LLM call.
4. **Live demo (2 min)** — upload PDF, run 2 valid queries (show citations + sources panel), 1 invalid query (show refusal), 1 Hindi query (show language-matched response).
5. **Eval run (30s)** — `python tests/run_eval.py` → all 10 PASS.
6. **Logs (30s)** — terminal showing structured log lines with request IDs, latencies, retrieval scores.
