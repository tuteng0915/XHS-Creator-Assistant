"""Positioned excerpts for one isolated reading; never an account-wide catalog."""

from app.services.account_report_sources import build_report_sources


def reading_fragments(title: str, body: str) -> dict[str, dict]:
    catalog = build_report_sources({"xhsCreatorProfile": {"notes": [
        {"noteId": "reading", "title": title, "desc": body},
    ]}})["reading"]
    result = {}
    offset = 0
    for excerpt_id, text in catalog.items():
        is_title = excerpt_id == "t"
        start = 0 if is_title else offset
        result[excerpt_id] = {
            "excerptId": excerpt_id, "source": "title" if is_title else "body",
            "quote": text, "start": start, "end": start + len(text),
        }
        if not is_title:
            offset += len(text)
    return result
