import io
import time
from typing import Dict, List

import pdfplumber

from core.logger import get_logger, log_event

logger = get_logger(__name__)


class PDFProcessor:

    def process(self, file_bytes: bytes, filename: str) -> List[Dict]:
        start   = time.time()
        records: List[Dict] = []
        skipped = 0

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                try:
                    text = (page.extract_text() or "").strip()
                except Exception as exc:
                    logger.warning("page_extract_failed page=%s err=%s", idx, exc)
                    skipped += 1
                    continue

                if not text:
                    skipped += 1
                    continue

                records.append({"page_number": idx, "text": text, "filename": filename})

        log_event(
            logger, "pdf_extracted",
            filename=filename,
            pages=len(records),
            skipped=skipped,
            ms=int((time.time() - start) * 1000),
        )
        return records
