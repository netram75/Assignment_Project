"""End-to-end eval runner. Hits a running server, prints PASS/FAIL table.

Usage:
    1. Start the server:    python main.py
    2. In another shell:    python tests/run_eval.py [--pdf tests/sample.pdf] [--url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

import urllib.request
import urllib.error
import mimetypes

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = ROOT / "tests" / "sample.pdf"
TEST_CASES = ROOT / "tests" / "test_cases.json"

REFUSAL_MARKER = "I can only answer questions based on the uploaded PDF document"
CITATION_RE = re.compile(r"\[Pages?\s+[0-9,\s]+\]", re.IGNORECASE)

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def post_multipart(url: str, file_path: Path) -> Dict:
    boundary = "----PDFAgentEvalBoundary"
    mime = mimetypes.guess_type(file_path.name)[0] or "application/pdf"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    body += file_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, payload: Dict) -> Dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def evaluate(case: Dict, response: Dict) -> tuple[bool, str]:
    text = response.get("response", "")
    is_refusal = response.get("is_refusal", False)
    has_citation = bool(CITATION_RE.search(text))
    looks_refusal = REFUSAL_MARKER.lower() in text.lower() or is_refusal

    ctype = case["type"]
    if ctype == "invalid":
        if looks_refusal:
            return True, "refused as expected"
        return False, "expected refusal, got substantive answer"

    if ctype == "valid":
        if looks_refusal:
            return False, "expected answer, got refusal"
        if not has_citation:
            return False, "answer present but no [Page X] citation"
        return True, "answered with citation"

    if ctype == "multilingual":
        if looks_refusal:
            return False, "expected answer, got refusal"
        if not has_citation:
            return False, "answer present but no [Page X] citation"
        lang = case.get("language", "")
        if lang == "hi" and not DEVANAGARI_RE.search(text):
            return False, "expected Devanagari (Hindi) script in response"
        if lang == "es":
            spanish_hints = ("é", "í", "ó", "á", "ú", "ñ", "¿", "¡", " el ", " la ", " es ")
            if not any(h in text.lower() for h in spanish_hints):
                return False, "response doesn't look like Spanish"
        return True, f"answered in {lang} with citation"

    return False, f"unknown case type: {ctype}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8000", help="Base URL of running server")
    p.add_argument("--pdf", default=str(DEFAULT_PDF), help="Path to PDF to upload")
    args = p.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: sample PDF not found at {pdf_path}", file=sys.stderr)
        print("       Place a sample PDF there or pass --pdf <path>.", file=sys.stderr)
        return 2

    cases: List[Dict] = json.loads(TEST_CASES.read_text(encoding="utf-8"))["cases"]

    print(f"-> Resetting server state at {args.url}")
    try:
        post_json(f"{args.url}/api/reset", {})
    except Exception as exc:
        print(f"ERROR: reset failed: {exc}. Is the server running?", file=sys.stderr)
        return 2

    print(f"-> Uploading {pdf_path.name}")
    try:
        up = post_multipart(f"{args.url}/api/upload", pdf_path)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"ERROR: upload failed ({exc.code}): {body}", file=sys.stderr)
        return 2
    print(f"   uploaded: {up['pages']} pages, {up['chunks']} chunks\n")

    rows = []
    passed = 0
    for case in cases:
        try:
            resp = post_json(
                f"{args.url}/api/chat",
                {"message": case["question"], "history": []},
            )
        except Exception as exc:
            rows.append((case["id"], case["type"], "FAIL", f"request error: {exc}"))
            continue
        ok, reason = evaluate(case, resp)
        if ok:
            passed += 1
        rows.append((case["id"], case["type"], "PASS" if ok else "FAIL", reason))

    print(f"{'ID':<26} {'TYPE':<14} {'RESULT':<6} REASON")
    print("-" * 90)
    for row in rows:
        print(f"{row[0]:<26} {row[1]:<14} {row[2]:<6} {row[3]}")
    print("-" * 90)
    print(f"{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
