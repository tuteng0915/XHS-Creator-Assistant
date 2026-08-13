from __future__ import annotations

from app.services.source_materials import SourceMaterialService


class InputAssetService(SourceMaterialService):
    """Product-facing compatibility layer for creator input assets.

    The implementation still uses the legacy source_materials table and
    repository. New API/router code should depend on InputAssetService so the
    product model can move away from SourceMaterial terminology incrementally.
    """
