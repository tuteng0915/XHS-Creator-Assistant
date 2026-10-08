"""Shared saved-reader contract for simulation execution and fixed-panel retests."""

from typing import Literal

from pydantic import BaseModel, Field, model_serializer, model_validator

from app.services.audience_evidence import AudienceEvidence, InterestLabel, ObservedEpisode


class PersonaDefinition(BaseModel):
    id: str
    name: str
    profile: str
    interests: list[InterestLabel] = Field(default_factory=list, max_length=6)
    coreConcern: str = ""
    contentPreference: str = ""
    expressionStyle: str = ""
    fanAssetId: str | None = None
    sourceAnalysisId: str | None = None
    sourceGroupId: str | None = None
    updatedAt: str | None = None
    userAdjusted: bool = False
    archetype: str = ""
    background: str = ""
    personality: str = ""
    concerns: str = ""
    color: str = ""
    evidence: list[str] = Field(default_factory=list)
    evidenceRefs: list[AudienceEvidence] = Field(default_factory=list)
    evidenceBasis: Literal["comment_observed", "content_inferred", "mixed"] | None = None
    evidenceStatus: Literal["verified", "legacy_unverified", "hypothesis"] = "hypothesis"
    limitations: str = ""
    unknowns: list[str] = Field(default_factory=list)
    observedEpisodes: list[ObservedEpisode] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def preserve_optional_origin_shape(self, serialize):
        result = serialize(self)
        # This metadata was added after fixed-panel snapshots existed.  Keep an
        # old omission absent, while preserving an explicit null or group ID.
        # All other defaults still participate in the strict snapshot check.
        if "sourceGroupId" not in self.model_fields_set:
            result.pop("sourceGroupId", None)
        return result


class PersonaDefinitionsResult(BaseModel):
    personas: list[PersonaDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_personas(self):
        if len({p.id for p in self.personas}) != len(self.personas):
            raise ValueError("模拟角色 ID 不可重复")
        return self
