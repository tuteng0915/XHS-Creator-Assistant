"""Small, product-owned contracts for auditable model context.

The contract deliberately describes *what was selected* for a model call rather
than trying to replace the payload each product workflow already understands.
It can therefore travel beside an analysis pack, reader-selection input, or
simulation snapshot without making those workflow-specific schemas generic.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import Field

from app.models import APIModel

CONTEXT_ENVELOPE_VERSION = "context-envelope/v1"
WORKSPACE_PACK_SNAPSHOT_VERSION = "workspace-pack/v1"


class ContextAssetRef(APIModel):
    """Stable identity for one product asset used as model evidence."""

    workspace_id: str | None = None
    asset_type: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    asset_sub_type: str | None = None


class ContextEvidenceSource(APIModel):
    """One selected evidence item, including its selection rule and version."""

    asset_ref: ContextAssetRef
    selector: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    source_version: str | int | None = None


class ContextSnapshotMetadata(APIModel):
    """Metadata that lets a later run identify the exact frozen context."""

    version: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    source_refs: list[ContextAssetRef]


class ContextOmission(APIModel):
    """One explicit piece of material intentionally absent from model context."""

    reason: str = Field(min_length=1)
    asset_ref: ContextAssetRef | None = None
    omitted_chars: int | None = Field(default=None, ge=0)


class ContextEnvelope(APIModel):
    """An additive description of why and from where a context was assembled."""

    contract_version: Literal[CONTEXT_ENVELOPE_VERSION] = CONTEXT_ENVELOPE_VERSION
    operation: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    evidence_sources: list[ContextEvidenceSource]
    omissions: list[ContextOmission] = Field(default_factory=list)
    snapshot: ContextSnapshotMetadata


def build_context_envelope(
    *,
    operation: str,
    purpose: str,
    workspace_id: str,
    items: Sequence[Mapping[str, Any]],
    snapshot: Mapping[str, Any],
    omissions: Sequence[Mapping[str, Any]] = (),
) -> ContextEnvelope:
    """Describe an existing frozen context without altering its payload.

    ``items`` use the workspace-pack shape (``assetRef``, ``selector``, and
    ``contentHash``). Keeping the adapter here means each workflow does not
    need to reinvent evidence/source-version bookkeeping.
    """
    evidence_sources = [
        ContextEvidenceSource(
            asset_ref=ContextAssetRef.model_validate(item["assetRef"]),
            selector=str(item["selector"]),
            content_hash=str(item["contentHash"]),
            source_version=_source_version(item),
        )
        for item in items
    ]
    source_refs = [source.asset_ref for source in evidence_sources]
    return ContextEnvelope(
        operation=operation,
        purpose=purpose,
        workspace_id=workspace_id,
        evidence_sources=evidence_sources,
        omissions=[_omission(item) for item in omissions],
        snapshot=ContextSnapshotMetadata(
            version=str(snapshot.get("version") or WORKSPACE_PACK_SNAPSHOT_VERSION),
            created_at=str(snapshot["createdAt"]),
            content_hash=str(snapshot["contentHash"]),
            source_refs=source_refs,
        ),
    )


def _omission(item: Mapping[str, Any]) -> ContextOmission:
    """Normalize the pack's camelCase omission record into the typed contract."""
    asset_ref = item.get("assetRef")
    omitted_chars = item.get("omittedChars")
    return ContextOmission(
        reason=str(item["reason"]),
        asset_ref=(
            ContextAssetRef.model_validate(asset_ref)
            if isinstance(asset_ref, Mapping)
            else None
        ),
        omitted_chars=omitted_chars if isinstance(omitted_chars, int) else None,
    )


def _source_version(item: Mapping[str, Any]) -> str | int | None:
    """Use an explicit asset version where the selected item has one."""
    data = item.get("data")
    if not isinstance(data, Mapping):
        return None
    for key in ("updatedAt", "positioningVersion", "version"):
        value = data.get(key)
        if isinstance(value, (str, int)):
            return value
    return None
