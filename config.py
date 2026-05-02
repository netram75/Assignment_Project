import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")

# Chat model (Groq free tier — 14,400 req/day)
GROQ_MODEL      = "llama-3.3-70b-versatile"
# Embedding model (Google AI Studio — only called on upload, not every chat)
EMBEDDING_MODEL = "models/text-embedding-004"

CHUNK_SIZE    = 800
CHUNK_OVERLAP = 200
TOP_K         = 5

RELEVANCE_HARD_FLOOR = 0.25   # below this → refuse without calling LLM
RELEVANCE_STRONG     = 0.40   # used for logging only

MAX_HISTORY            = 10
HISTORY_TURNS_IN_PROMPT = 6

MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", 8000))

REFUSAL_MESSAGE = (
    "I can only answer questions based on the uploaded PDF document. "
    "This question appears to be outside the scope of the document. "
    "Please ask something related to the PDF content."
)
