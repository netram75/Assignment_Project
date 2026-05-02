import time
import uuid
from typing import List, Tuple

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as _ChromaEF
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

import config
from core.logger import get_logger, log_event

logger = get_logger(__name__)


class _LocalEmbeddings(Embeddings):
    # Wraps Chroma's bundled all-MiniLM-L6-v2 ONNX model — no API key needed.
    def __init__(self) -> None:
        self._fn = _ChromaEF()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [[float(x) for x in v] for v in self._fn(texts)]

    def embed_query(self, text: str) -> List[float]:
        return [float(x) for x in self._fn([text])[0]]


class VectorStore:
    # in-memory Chroma collection; wiped on every new upload

    def __init__(self) -> None:
        self.embeddings = _LocalEmbeddings()
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
