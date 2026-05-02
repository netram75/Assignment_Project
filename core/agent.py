import re
import time
from typing import Dict, List, Tuple

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

import config
from core.chunker import TextChunker
from core.logger import get_logger, log_event
from core.pdf_processor import PDFProcessor
from core.prompts import QUERY_PROMPT, SYSTEM_PROMPT
from core.vector_store import VectorStore

logger = get_logger(__name__)

CITATION_RE = re.compile(r"\[Pages?\s+([0-9,\s]+)\]", re.IGNORECASE)


class PDFAgent:

    def __init__(self) -> None:
        self.processor = PDFProcessor()
        self.chunker = TextChunker()
        self.vector_store = VectorStore()
        self.llm = ChatGroq(
            model=config.GROQ_MODEL,
            temperature=0.1,
            groq_api_key=config.GROQ_API_KEY,
            max_retries=2,  # handles transient 5xx from Groq without hanging
        )
        self.filename: str = ""
        self.total_pages: int = 0

    # ── ingestion ──────────────────────────────────────────────────────────

    def process_pdf(self, file_bytes: bytes, filename: str) -> Dict:
        if self.vector_store.is_loaded:
            self.vector_store.clear()

        pages = self.processor.process(file_bytes, filename)
        if not pages:
            raise ValueError("No extractable text found in PDF.")

        documents = self.chunker.chunk(pages)
        chunk_count = self.vector_store.index_documents(documents)

        self.filename = filename
        self.total_pages = max(p["page_number"] for p in pages)
        return {"pages": len(pages), "total_pages": self.total_pages, "chunks": chunk_count}

    # ── chat ───────────────────────────────────────────────────────────────

    def chat(self, message: str, conversation_history: List[Dict]) -> Dict:
        start = time.time()

        if not self.vector_store.is_loaded:
            return {
                "response": "Please upload a PDF first before asking questions.",
                "citations": [],
                "sources": [],
                "is_refusal": True,
            }

        try:
            results = self.vector_store.search(message, top_k=config.TOP_K)
        except Exception as exc:
            logger.exception("retrieval_failed err=%s", exc)
            return self._error_payload("I hit an error retrieving from the document. Please try again.")

        if not results:
            return self._refusal_payload([])

        max_score = max(score for _, score in results)
        strong_count = sum(1 for _, s in results if s >= config.RELEVANCE_STRONG)

        # Stage 1: refuse without touching the LLM if nothing is relevant
        if max_score < config.RELEVANCE_HARD_FLOOR:
            log_event(logger, "hard_refusal", max_score=round(max_score, 3), q_preview=message[:60])
            return self._refusal_payload(results)

        # Stage 2: pass context to the LLM
        # Use plain string replacement instead of .format() so that curly braces
        # in the PDF text (code snippets, JSON, math) don't crash the template.
        user_prompt = (
            QUERY_PROMPT
            .replace("{context}",  self._format_context(results),  1)
            .replace("{history}",  self._format_history(conversation_history), 1)
            .replace("{question}", message, 1)
        )

        try:
            ai = self.llm.invoke(
                [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
            )
            response_text = (ai.content or "").strip()
        except Exception as exc:
            logger.exception("llm_failed err=%s", exc)
            return self._error_payload("I hit an error generating a response. Please try again.")

        is_refusal = self._looks_like_refusal(response_text)
        citations  = self._extract_citations(response_text)
        sources    = self._format_sources(results)

        log_event(
            logger, "chat",
            q_preview=message[:60],
            max_score=round(max_score, 3),
            strong_count=strong_count,
            is_refusal=is_refusal,
            citations=citations,
            ms=int((time.time() - start) * 1000),
        )

        return {
            "response":   response_text,
            "citations":  citations,
            "sources":    sources,
            "is_refusal": is_refusal,
        }

    # ── helpers ────────────────────────────────────────────────────────────

    def _format_context(self, results: List[Tuple[Document, float]]) -> str:
        parts = []
        for doc, score in results:
            page = doc.metadata.get("page_number", "?")
            parts.append(f"[Page {page} | relevance={score:.2f}]\n{doc.page_content}")
        return "\n\n---\n\n".join(parts)

    def _format_history(self, history: List[Dict]) -> str:
        if not history:
            return "(no prior turns)"
        recent = history[-config.HISTORY_TURNS_IN_PROMPT * 2:]
        lines = []
        for turn in recent:
            role    = turn.get("role", "user")
            content = (turn.get("content") or "").strip()
            if content:
                lines.append(f"{role.upper()}: {content}")
        return "\n".join(lines) if lines else "(no prior turns)"

    def _format_sources(self, results: List[Tuple[Document, float]]) -> List[Dict]:
        out = []
        for doc, score in results[:3]:
            out.append({
                "page":    doc.metadata.get("page_number"),
                "score":   round(float(score), 3),
                "preview": doc.page_content[:160].replace("\n", " "),
            })
        return out

    def _extract_citations(self, text: str) -> List[int]:
        pages: set[int] = set()
        for match in CITATION_RE.finditer(text):
            for raw in match.group(1).split(","):
                raw = raw.strip()
                if raw.isdigit():
                    pages.add(int(raw))
        return sorted(pages)

    def _looks_like_refusal(self, text: str) -> bool:
        if not text:
            return True
        # The system prompt requires the refusal to always be in English,
        # so checking the first 60 chars of the canonical message is enough.
        return config.REFUSAL_MESSAGE[:60].lower() in text.lower()

    def _refusal_payload(self, results: List[Tuple[Document, float]]) -> Dict:
        return {
            "response":   config.REFUSAL_MESSAGE,
            "citations":  [],
            "sources":    self._format_sources(results) if results else [],
            "is_refusal": True,
        }

    def _error_payload(self, msg: str) -> Dict:
        return {"response": msg, "citations": [], "sources": [], "is_refusal": True}

    # ── lifecycle ──────────────────────────────────────────────────────────

    def reset(self) -> None:
        self.vector_store.clear()
        self.filename   = ""
        self.total_pages = 0

    @property
    def is_loaded(self) -> bool:
        return self.vector_store.is_loaded
