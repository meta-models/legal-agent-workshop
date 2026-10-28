"""check_signatures (verification on): is the signature on one page consistent with a
genuine reference signature of the same person on another page?

The agent names both pages: the page to check, and a page the signer genuinely signed.
The verdict is one of VERDICTS. Anything other than "consistent" becomes a signature
flag the attorney reviews at sign-off, and the memo rules refuse a finding marked proven
on that signature.

PLACEHOLDER: reports every signature as consistent, so the end-to-end flow can be tested.
The real check (to be written): find the signature on each page image with SAM 3.1
(segment, below), then show Muse Spark both pages with the boxes and ask whether the
signatures are consistent (letter shapes, loops, slant, rhythm). It is a consistency
check, not forgery detection.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import cast, TYPE_CHECKING

from openai import OpenAI
from openai.types.responses import Response

from agent_kit import document_text
from agent_kit.settings import sam_model

if TYPE_CHECKING:
    from mcp_server.context import Context

VERDICTS = ("consistent", "inconsistent", "unclear", "unsigned")

DEFINITION = {
    "type": "function",
    "name": "check_signatures",
    "description": "Check whether the signature presented as the signer's on one page is consistent with a "
    "genuine signature of the same person on another page (the reference: a page you know they signed). "
    "Returns consistent, inconsistent, unclear, or unsigned. Check a signature before relying on it for a "
    "checklist item.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "document_id": {
                "type": "string",
                "description": "the document whose signature you are checking",
            },
            "page": {"type": "integer"},
            "signer": {
                "type": "string",
                "description": "the person the signature is presented as",
            },
            "reference_document_id": {
                "type": "string",
                "description": "a document the signer genuinely signed",
            },
            "reference_page": {"type": "integer"},
        },
        "required": [
            "document_id",
            "page",
            "signer",
            "reference_document_id",
            "reference_page",
        ],
    },
}


def run(ctx: Context, args: dict) -> dict:
    document_id, page = str(args.get("document_id", "")), int(args.get("page") or 1)
    reference_id, reference_page = (
        str(args.get("reference_document_id", "")),
        int(args.get("reference_page") or 1),
    )
    signer = str(args.get("signer", ""))
    if (reference_id, reference_page) == (document_id, page):
        return {
            "error": "the reference must be a different page, one the signer genuinely signed"
        }
    document_text.page_image(ctx.root, document_id, page)  # both pages must exist
    document_text.page_image(ctx.root, reference_id, reference_page)
    verdict, reason = (
        "consistent",
        "placeholder: every signature is reported as consistent",
    )
    ctx.case.add_signature_check(
        {
            "document_id": document_id,
            "page": page,
            "signer": signer,
            "verdict": verdict,
            "reason": reason,
            "boxes": [],
            "reference": {
                "document_id": reference_id,
                "page": reference_page,
                "boxes": [],
            },
        }
    )
    return {
        "document_id": document_id,
        "page": page,
        "signer": signer,
        "verdict": verdict,
        "reason": reason,
    }


# ---- SAM 3.1, for the real check (unused while the placeholder is in place) ----------
#
# SAM returns special-token text in output_text:
#     <0f>0<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;...|>,1<|box;...|>...
# Only the boxes are needed. SAM 3.1 does not match "signature" on a scanned page;
# "ink scribble" finds handwritten signatures.

SIGNATURE_PROMPT = "ink scribble"
BOX = re.compile(r"(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)\|>")


def parse_boxes(output_text: str) -> list:
    """Every box in SAM's output, in order. Empty output means zero matches."""
    boxes = []
    for match in BOX.finditer(output_text or ""):
        ordinal, x1, y1, x2, y2, w, h = (int(v) for v in match.groups())
        boxes.append(
            {
                "ordinal": ordinal,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": w,
                "height": h,
            }
        )
    return boxes


def data_url(image: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode()


def segment(client: OpenAI, image: Path, prompt: str = SIGNATURE_PROMPT) -> list:
    """One SAM call on one page image: the boxes it found."""
    response = client.responses.create(
        model=sam_model(),
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url(image)},
                ],
            }
        ],
    )
    return parse_boxes(cast(Response, response).output_text)
