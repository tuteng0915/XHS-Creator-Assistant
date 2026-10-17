"""Read-only source views for writing, without summarizing or inventing facts.

The durable reference stays intact. Only its model-facing view is separated:
editorial observations do not share one evidence envelope with commenters'
personal circumstances. Known report statistics are not writing material.
Unknown/legacy shapes are preserved rather than guessed or discarded.
"""

from typing import Any


def account_writing_views(content: Any) -> tuple[Any, list[dict[str, Any]]]:
    if not isinstance(content, dict):
        return content, []
    editorial = dict(content)
    profile = editorial.get("profile")
    if (isinstance(profile, dict) and isinstance(profile.get("profile"), dict)
            and set(profile) <= {"profile", "observations"}):
        # The sibling observations are computed metric/range tables; retain
        # the actual report, including its evidence, wording and suggestions.
        editorial["profile"] = profile["profile"]
    feedback = editorial.get("pain_points")
    if not isinstance(feedback, dict) or not isinstance(feedback.get("painPoints"), list):
        return editorial, []
    items = feedback["painPoints"]
    if not all(isinstance(item, dict) and isinstance(item.get("evidence"), list)
               and all(isinstance(quote, str) for quote in item["evidence"]) for item in items):
        return editorial, []
    # Preserve any unfamiliar sibling fields from older reports.
    remainder = {key: value for key, value in feedback.items() if key != "painPoints"}
    if remainder:
        editorial["pain_points"] = remainder
    else:
        editorial.pop("pain_points")
    return editorial, [
        {
            "analysis": {key: value for key, value in item.items() if key != "evidence"},
            "historicalComments": [
                {"speaker": "历史评论者，身份未核实", "text": quote}
                for quote in item["evidence"]
            ],
            "currentReaderCircumstances": "未知；不是本次读者或作者的事实",
        }
        for item in items
    ]
