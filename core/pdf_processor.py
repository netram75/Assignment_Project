import io
import time
from typing import Dict, List

import pdfplumber

from core.logger import get_logger, log_event

logger = get_logger(__name__)

# OCR is an optional fallback for scanned / image-only PDFs. We import lazily so
# the app still runs if the OCR stack (PyMuPDF + Tesseract) is unavailable.
try:
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    _OCR_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on system install
    _OCR_AVAILABLE = False
    logger.warning("ocr_unavailable err=%s", exc)


class PDFProcessor:

    def process(self, file_bytes: bytes, filename: str) -> List[Dict]:
        start   = time.time()
        records: List[Dict] = []
        skipped = 0
        ocr_pages = 0

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                try:
                    text = (page.extract_text() or "").strip()
                except Exception as exc:
                    logger.warning("page_extract_failed page=%s err=%s", idx, exc)
                    text = ""

                if text:
                    records.append({"page_number": idx, "text": text, "filename": filename})
                    continue

                # No text layer on this page — fall back to OCR if available.
                ocr_text = self._ocr_page(file_bytes, idx) if _OCR_AVAILABLE else ""
                if ocr_text:
                    ocr_pages += 1
                    records.append({"page_number": idx, "text": ocr_text, "filename": filename})
                else:
                    skipped += 1

        log_event(
            logger, "pdf_extracted",
            filename=filename,
            pages=len(records),
            ocr_pages=ocr_pages,
            skipped=skipped,
            ms=int((time.time() - start) * 1000),
        )
        return records

    def _ocr_page(self, file_bytes: bytes, page_number: int) -> str:
        """Render one page to an image and OCR it. Returns '' on any failure."""
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                page = doc[page_number - 1]
                # 2x zoom ~= 144 DPI, a good accuracy/speed tradeoff for OCR.
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
            return (pytesseract.image_to_string(img) or "").strip()
        except Exception as exc:
            logger.warning("ocr_failed page=%s err=%s", page_number, exc)
            return ""
