from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
from uuid import uuid4

from app.config import Settings
from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import (
    SourceMaterialResponse,
    SourceMaterialType,
    SourceMaterialUpdate,
    TextSourceMaterialCreate,
    TextSourceMaterialResponse,
    TrendCsvSourceMaterialResponse,
)
from app.repositories.source_materials import SourceMaterialRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now


class SourceMaterialService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: SourceMaterialRepository,
        workspace_repository: WorkspaceRepository,
        settings: Settings,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.settings = settings

    def create_text(
        self, workspace_id: str, payload: TextSourceMaterialCreate
    ) -> TextSourceMaterialResponse:
        name = payload.name.strip()
        if not name:
            raise ValidationError("Source material name cannot be blank")
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            row = self.repository.create_text(
                connection,
                workspace_id=workspace_id,
                material_type=payload.type.value,
                name=name,
                content=payload.content,
                now=utc_now(),
            )
        return TextSourceMaterialResponse.model_validate(
            {**row, "content": row["text_content"]}
        )

    def create_csv(
        self,
        workspace_id: str,
        *,
        name: str,
        keyword: str,
        filename: str,
        content: bytes,
    ) -> TrendCsvSourceMaterialResponse:
        clean_name = name.strip()
        clean_keyword = keyword.strip()
        if not clean_name:
            raise ValidationError("Source material name cannot be blank")
        if not clean_keyword:
            raise ValidationError("Trend keyword cannot be blank")
        if not content:
            raise ValidationError("CSV file cannot be empty")
        if len(content) > self.settings.max_upload_bytes:
            raise ValidationError("CSV file exceeds the upload size limit")

        safe_filename = PurePosixPath(filename.replace("\\", "/")).name
        extension = Path(safe_filename).suffix.lower()
        if extension not in {".csv", ".tsv"}:
            raise ValidationError("Only .csv and .tsv files are supported")
        delimiter = "\t" if extension == ".tsv" else ","
        media_type = (
            "text/tab-separated-values" if extension == ".tsv" else "text/csv"
        )
        preview, row_count = self._parse_csv(content, delimiter)

        material_id = str(uuid4())
        stored_name = "source.tsv" if extension == ".tsv" else "source.csv"
        stored_key = f"{workspace_id}/{material_id}/{stored_name}"
        final_path = self.settings.upload_directory / stored_key
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = final_path.with_suffix(final_path.suffix + ".tmp")
        temporary_path.write_bytes(content)
        temporary_path.replace(final_path)

        try:
            with self.database.transaction() as connection:
                self.workspace_repository.get(connection, workspace_id)
                row = self.repository.create_csv(
                    connection,
                    material_id=material_id,
                    workspace_id=workspace_id,
                    name=clean_name,
                    keyword=clean_keyword,
                    original_filename=safe_filename,
                    stored_key=stored_key,
                    media_type=media_type,
                    byte_size=len(content),
                    sha256=hashlib.sha256(content).hexdigest(),
                    row_count=row_count,
                    preview_json=json.dumps(preview, ensure_ascii=False),
                    now=utc_now(),
                )
        except Exception:
            final_path.unlink(missing_ok=True)
            raise
        return self._to_response(row)

    def list(
        self, workspace_id: str, material_type: SourceMaterialType | None
    ) -> list[SourceMaterialResponse]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(
                connection,
                workspace_id,
                material_type.value if material_type is not None else None,
            )
        return [self._to_response(row) for row in rows]

    def get(self, material_id: str) -> SourceMaterialResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, material_id)
        return self._to_response(row)

    def update(
        self, material_id: str, payload: SourceMaterialUpdate
    ) -> SourceMaterialResponse:
        if payload.name is None and payload.content is None and payload.keyword is None:
            raise ValidationError("At least one editable field is required")
        name = payload.name.strip() if payload.name is not None else None
        if name == "":
            raise ValidationError("Source material name cannot be blank")
        keyword = payload.keyword.strip() if payload.keyword is not None else None
        if keyword == "":
            raise ValidationError("Trend keyword cannot be blank")
        with self.database.transaction() as connection:
            row = self.repository.update(
                connection,
                material_id=material_id,
                name=name,
                content=payload.content,
                keyword=keyword,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    def _parse_csv(
        self, content: bytes, delimiter: str
    ) -> tuple[list[dict[str, str]], int]:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValidationError("CSV file must use UTF-8 encoding") from error
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
        try:
            raw_fieldnames = next(reader)
        except StopIteration as error:
            raise ValidationError("CSV file must contain a header row") from error
        if not raw_fieldnames or not any(name.strip() for name in raw_fieldnames):
            raise ValidationError("CSV file must contain a header row")
        fieldnames = [name.strip() for name in raw_fieldnames]
        preview: list[dict[str, str]] = []
        row_count = 0
        for values in reader:
            row = {
                fieldnames[index]: value
                for index, value in enumerate(values[: len(fieldnames)])
                if fieldnames[index]
            }
            if not any(value.strip() for value in row.values()):
                continue
            row_count += 1
            if len(preview) < self.settings.csv_preview_rows:
                preview.append(row)
        return preview, row_count

    @staticmethod
    def _to_response(row: dict) -> SourceMaterialResponse:
        if row["type"] == SourceMaterialType.TREND_CSV.value:
            return TrendCsvSourceMaterialResponse.model_validate(
                {
                    **row,
                    "preview": json.loads(row["preview_json"]),
                }
            )
        return TextSourceMaterialResponse.model_validate(
            {**row, "content": row["text_content"]}
        )
