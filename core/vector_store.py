import time
import uuid
from typing import List, Tuple

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

import config
from core.logger import get_logger, log_event

logger = get_logger(__name__)


class VectorStore:
    # in-memory Chroma collection; wiped on every new upload

    def __init__(self) -> None:
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model=config.EMBEDDING_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
        )
        self._store: Chroma | None = None
        self._collection_name: str = ""

    def _new_collection(self) -> Chroma:
        self._collection_name = f"pdf-{uuid.uuid4().hex[:8]}"
        return Chroma(
            collection_name=self._collection_name,
            embedding_function=self.embeddings,
            collection_metadata={"hnsw:space": "cosine"},
        )

    def index_documents(self, documents: List[Document]) -> int:
        if not documents:
            return 0

        start = time.time()
        # Build the new store before assigning — if add_documents fails,
        # self._store stays None (or previous value) rather than pointing
        # at an empty collection that looks loaded but returns nothing.
        new_store = self._new_collection()
        try:
            new_store.add_documents(documents)
        except Exception:
            self._store = None
            self._collection_name = ""
            raise

        self._store = new_store
        log_event(
            logger, "indexed",
            collection=self._collection_name,
            docs=len(documents),
            ms=int((time.time() - start) * 1000),
        )
        return len(documents)

    def search(self, query: str, top_k: int = config.TOP_K) -> List[Tuple[Document, float]]:
        if self._store is None:
            return []

        start = time.time()
        raw = self._store.similarity_search_with_relevance_scores(query, k=top_k)

        # Chroma cosine scores can drift slightly outside [0, 1] due to float precision
        results = [(doc, max(0.0, min(1.0, float(score)))) for doc, score in raw]

        log_event(
            logger, "search",
            top_k=top_k,
            scores=[round(s, 3) for _, s in results],
            ms=int((time.time() - start) * 1000),
        )
        return results

    def clear(self) -> None:
        if self._store is not None:
            try:
                self._store.delete_collection()
            except Exception as exc:
                logger.warning("delete_collection_failed err=%s", exc)
        self._store = None
        self._collection_name = ""

    @property
    def is_loaded(self) -> bool:
        return self._store is not None
