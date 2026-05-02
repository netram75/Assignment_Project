import time
import uuid
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from core.agent import PDFAgent
from core.logger import get_logger, log_event

logger = get_logger("main")

BASE_DIR = Path(__file__).parent

app = FastAPI(title="PDF Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: Optional[List[ChatTurn]] = None


_agent: Optional[PDFAgent] = None
_history: List[dict] = []


def get_agent() -> PDFAgent:
    global _agent
    if _agent is None:
        if not config.GROQ_API_KEY:
            raise HTTPException(status_code=500, detail="GROQ_API_KEY is not set. Add it to .env.")
        _agent = PDFAgent()
    return _agent


# paths that shouldn't clutter the log (Chrome probes, favicon, etc.)
_QUIET_PREFIXES = ("/.well-known", "/favicon")


@app.middleware("http")
async def request_logger(request: Request, call_next):
    rid = uuid.uuid4().hex[:8]
    start = time.time()
    response = await call_next(request)
    if not any(request.url.path.startswith(p) for p in _QUIET_PREFIXES):
        log_event(
            logger, "request",
            rid=rid,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ms=int((time.time() - start) * 1000),
        )
    response.headers["X-Request-Id"] = rid
    return response


@app.get("/")
async def root():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "pdf_loaded": _agent.is_loaded if _agent else False,
        "filename": _agent.filename if _agent else "",
        "model": config.GROQ_MODEL,
        "embedding_model": config.EMBEDDING_MODEL,
    }


@app.get("/api/status")
async def status():
    if _agent is None or not _agent.is_loaded:
        return {"pdf_loaded": False, "filename": "", "total_pages": 0}
    return {
        "pdf_loaded": True,
        "filename": _agent.filename,
        "total_pages": _agent.total_pages,
    }


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted.")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > config.MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF exceeds the {config.MAX_PDF_BYTES // (1024 * 1024)} MB limit.",
        )

    agent = get_agent()
    try:
        result = agent.process_pdf(file_bytes, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("upload_failed err=%s", exc)
        raise HTTPException(status_code=500, detail="Failed to process PDF.")

    _history.clear()
    return {
        "status": "ok",
        "filename": file.filename,
        "pages": result["pages"],
        "total_pages": result["total_pages"],
        "chunks": result["chunks"],
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    agent = get_agent()
    history = [t.model_dump() for t in req.history] if req.history is not None else _history
    payload = agent.chat(req.message, history)

    if req.history is None:
        _history.append({"role": "user", "content": req.message})
        _history.append({"role": "assistant", "content": payload["response"]})
        if len(_history) > config.MAX_HISTORY * 2:
            del _history[: len(_history) - config.MAX_HISTORY * 2]

    return payload


@app.post("/api/reset")
async def reset():
    if _agent is not None:
        _agent.reset()
    _history.clear()
    return {"status": "cleared"}


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=False)
