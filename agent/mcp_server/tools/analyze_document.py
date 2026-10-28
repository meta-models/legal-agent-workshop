"""analyze_document: read up to 4 inbox documents for one request.

Each document's text is extracted once (document_text) and every quote the model returns
is checked against it: an evidence record is verified only if its quote is on its page.
The documents are read in parallel; a document that fails comes back with no evidence and
the error in its note, and the others still return. A document flagged confidential
cannot be read. The documents read are remembered in the case record (the escalation
rule needs them).
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TYPE_CHECKING

import openai
from openai import OpenAI

from agent_kit import document_text
from agent_kit.document_text import DocumentError

if TYPE_CHECKING:
    from mcp_server.context import Context

MAX_DOCS_PER_CALL = 4

DEFINITION = {
    "type": "function",
    "name": "analyze_document",
    "description": "Read up to 4 inbox documents (PDF, scan, table, chart, or photo) for one request. Returns "
    "evidence records with page, exact quote, claim, interpretation, ambiguity, and verified (quote found on the page).",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "document_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": MAX_DOCS_PER_CALL,
            },
            "request": {"type": "string"},
        },
        "required": ["document_ids", "request"],
    },
}

PROMPT = (
    "You are reviewing case document {doc_id} for this request: {request}\n"
    "The verified page text is below. Every quote must be copied exactly from that text, "
    "on the page you name. Keep the quote (what the document says) separate from your "
    "interpretation (what it means for the request). If the document is irrelevant, return no evidence "
    "and say so in note. If text is illegible or ambiguous, say so in ambiguity rather than guessing.\n"
    'Return only JSON: {{"evidence": [{{"page": 1, "quote": "...", "claim": "...", '
    '"interpretation": "...", "ambiguity": ""}}], "note": "..."}}\n\nVERIFIED PAGE TEXT\n{text}'
)
MAX_ATTEMPTS = 2


def run(ctx: Context, args: dict) -> dict:
    ids = args.get("document_ids") or []
    ids = [ids] if isinstance(ids, str) else [str(d) for d in ids]
    flagged = [d for d in ids if ctx.case.flagged(d)]
    if flagged:
        return {"error": f"confidential documents cannot be read: {', '.join(flagged)}"}
    result = analyze(ctx.client, ctx.root, ids, str(args.get("request", "")))
    ctx.case.mark_read(ids)
    return result


def analyze(client: OpenAI, root: Path, document_ids: list, request: str) -> dict:
    """{"documents": [{"document_id", "evidence": [...], "note"}]}, in the order asked."""
    if not document_ids:
        raise DocumentError("document_ids is empty")
    if len(document_ids) > MAX_DOCS_PER_CALL:
        raise DocumentError(f"at most {MAX_DOCS_PER_CALL} documents per call")
    document_ids = list(dict.fromkeys(document_ids))
    for document_id in document_ids:
        document_text.get_document(
            root, document_id
        )  # an unknown id fails before any model call

    def read(document_id: str) -> dict:
        try:
            return _analyze_one(client, root, document_id, request)
        except (DocumentError, openai.APIError, OSError, ValueError) as error:
            return {
                "document_id": document_id,
                "evidence": [],
                "note": f"error: {error}",
            }

    with ThreadPoolExecutor(max_workers=len(document_ids)) as pool:
        return {"documents": list(pool.map(read, document_ids))}


def _analyze_one(client: OpenAI, root: Path, document_id: str, request: str) -> dict:
    """Extract (once) and analyze one document for one request."""
    document = document_text.get_document(root, document_id)
    text = document_text.extract_text(client, root, document_id)
    key = hashlib.sha256(f"{document['sha256']}|{request}".encode()).hexdigest()[:24]
    cached = document_text.cache(root) / "analysis" / f"{key}.json"
    if cached.is_file():
        return json.loads(cached.read_text())
    pages_text = "\n\n".join(f"[page {p['page']}]\n{p['text']}" for p in text["pages"])
    error, parsed = "", None
    for _attempt in range(MAX_ATTEMPTS):
        prompt = PROMPT.format(doc_id=document_id, request=request, text=pages_text)
        if error:
            prompt += f"\n\nYour previous output was invalid: {error}"
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        if text.get("file_id"):
            content.append({"type": "input_file", "file_id": text["file_id"]})
        output = document_text.ask(client, content)
        try:
            parsed = json.loads(output)
            if not isinstance(parsed.get("evidence", []), list):
                raise ValueError("evidence must be a list")
            break
        except (ValueError, AttributeError) as problem:
            error, parsed = str(problem), None
    if parsed is None:
        raise DocumentError(f"could not analyze {document_id}: {error}")
    evidence: list[dict[str, Any]] = []
    for item in parsed.get("evidence", []):
        try:
            page = int(item.get("page"))
        except (TypeError, ValueError):
            continue
        quote = str(item.get("quote", ""))
        evidence.append(
            {
                "document_id": document_id,
                "page": page,
                "quote": quote,
                "claim": str(item.get("claim", "")),
                "interpretation": str(item.get("interpretation", "")),
                "ambiguity": str(item.get("ambiguity", "")),
                "verified": document_text.quote_on_page(
                    quote, document_text.page_text(root, document_id, page) or ""
                ),
            }
        )
    result = {
        "document_id": document_id,
        "evidence": evidence,
        "note": str(parsed.get("note", "")),
    }
    cached.write_text(json.dumps(result, indent=1))
    return result
