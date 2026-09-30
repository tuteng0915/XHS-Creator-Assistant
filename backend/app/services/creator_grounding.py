"""Evidence boundaries for creator edits, not an automatic truth detector."""

from pydantic import BaseModel, ConfigDict, Field

from app.errors import ValidationError


class SupportedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    sourceId: str = Field(min_length=1)
    sourceQuote: str = Field(min_length=1)


class FactCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    safeToApply: bool
    supportedClaims: list[SupportedClaim]


class CreatorEdit(BaseModel):
    title: str = Field(min_length=1)
    body: str


class CreatorEditResult(BaseModel):
    reply: str = Field(min_length=1)
    update: CreatorEdit | None
    pendingSuggestions: list[str]
    factCheck: FactCheck


def validate_creator_edit(output: dict, sources: list[dict]) -> dict:
    result = CreatorEditResult.model_validate(output)
    if result.update is None:
        return result.model_dump()
    if not result.update.title.strip() or not result.factCheck.safeToApply:
        raise ValidationError("新增事实尚未确认，未更新正文")
    text = result.update.title + "\n" + result.update.body
    evidence = {source["id"]: source["text"] for source in sources}
    for claim in result.factCheck.supportedClaims:
        if (
            not claim.text.strip() or claim.text not in text
            or not claim.sourceQuote.strip()
            or claim.sourceQuote not in evidence.get(claim.sourceId, "")
        ):
            raise ValidationError("新增事实的引用与原始材料不符，未更新正文")
    for suggestion in result.pendingSuggestions:
        if suggestion.strip() and suggestion in text:
            raise ValidationError("待确认建议混入了正文，未更新正文")
    return result.model_dump()
