from typing import Dict, List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config
from core.logger import get_logger, log_event

logger = get_logger(__name__)


class TextChunker:

    def __init__(
        self,
        chunk_size: int = config.CHUNK_SIZE,
        chunk_overlap: int = config.CHUNK_OVERLAP,
    ) -> None:
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk(self, pages: List[Dict]) -> List[Document]:
        docs: List[Document] = []
        for page in pages:
            page_num = page["page_number"]
            for i, piece in enumerate(self.splitter.split_text(page["text"])):
                docs.append(
                    Document(
                        page_content=piece,
                        metadata={
                            "page_number": page_num,
                            "chunk_index": i,
                            "source": page["filename"],
                        },
                    )
                )
        log_event(logger, "chunked", pages=len(pages), chunks=len(docs))
        return docs
