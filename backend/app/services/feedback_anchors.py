"""Bounded source-only choices for locating panel feedback in frozen text."""

import hashlib
import re

MAX_ANCHORS = 64
MAX_QUOTE_LENGTH = 600


def feedback_anchor_catalog(topic: dict) -> dict:
    items = []
    # Draft outlines do not have a canonical editable title/body range yet.
    if topic.get("previewLevel") == "outline":
        return {"version": "text-anchors/v1", "items": [], "complete": True}
    for field in ("title", "body"):
        text = topic.get(field)
        if not isinstance(text, str):
            continue
        fingerprint = hashlib.sha256(text.encode()).hexdigest()[:16]
        for match in re.finditer(r".+?(?:[。！？\n]|$)", text, flags=re.DOTALL):
            for start in range(match.start(), match.end(), MAX_QUOTE_LENGTH):
                end = min(start + MAX_QUOTE_LENGTH, match.end())
                quote = text[start:end]
                if not quote.strip():
                    continue
                if len(items) == MAX_ANCHORS:
                    return {"version": "text-anchors/v1", "items": items, "complete": False}
                items.append({
                    "id": f"{field}:{start}:{fingerprint}", "field": field, "quote": quote,
                    "start": start, "end": end,
                })
    return {"version": "text-anchors/v1", "items": items, "complete": True}


def feedback_anchor_prompt_context(topic: dict) -> dict:
    catalog = feedback_anchor_catalog(topic)
    return {**catalog, "items": [
        {key: item[key] for key in ("id", "field", "quote")} for item in catalog["items"]
    ]}
