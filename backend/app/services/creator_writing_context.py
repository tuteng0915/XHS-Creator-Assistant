"""Lossless model-facing references; durable snapshots remain unchanged."""

from copy import deepcopy


def compact_writing_packet(packet: dict) -> dict:
    result = deepcopy(packet)
    target = result.get("creativeBrief", {}).get("target", {})
    body = target.get("body", "")
    focus = result.get("writingFocus")
    if isinstance(focus, dict):
        if focus.get("baseBody") == body and focus.get("baseTitle") == target.get("title"):
            focus.pop("baseBody", None)
            focus.pop("baseTitle", None)
            focus["baseManuscriptRef"] = "creativeBrief.target"
        reader = focus.get("readerMessage", {})
        source = reader.get("sourceTarget") if isinstance(reader, dict) else None
        if (isinstance(source, dict) and source.get("body") == body
                and source.get("title") == target.get("title")):
            source.pop("body", None)
            source["bodyRef"] = "creativeBrief.target.body"
        result["roleTask"]["writingFocusRules"] = [
            rule.replace("baseBody/baseTitle", "creativeBrief.target 的正文／标题")
            for rule in result.get("roleTask", {}).get("writingFocusRules", [])
        ]
    for source in result.get("evidence", {}).get("allowedSources", []):
        reference = None
        if source.get("id") == "target:topic":
            reference = "creativeBrief.target"
        elif source.get("id") == "writing:reader_opinion" and isinstance(focus, dict):
            reference = "writingFocus.readerMessage"
        elif (source.get("id") == "writing:selected_text" and isinstance(focus, dict)
              and isinstance(focus.get("selection"), dict)):
            reference = "writingFocus.selection.text"
        if reference:
            source.pop("text", None)
            source["contentRef"] = reference
    if isinstance(body, str) and body.strip():
        for item in result.get("conversation", []):
            if item.get("role") == "assistant":
                # Only collapse identical text. Different unadopted suggestions
                # and old reader versions retain their actual contents.
                item["content"] = item["content"].replace(
                    body, "（这份正文与当前稿相同，见 creativeBrief.target.body）",
                )
    return result
