from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now


class WorkspaceService:
    def __init__(self, database: SQLiteDatabase, repository: WorkspaceRepository) -> None:
        self.database = database
        self.repository = repository

    def create(self, payload: WorkspaceCreate) -> WorkspaceResponse:
        name = payload.name.strip()
        if not name:
            raise ValidationError("Workspace name cannot be blank")
        with self.database.transaction() as connection:
            row = self.repository.create(
                connection,
                name=name,
                account_positioning=payload.account_positioning,
                now=utc_now(),
            )
        return WorkspaceResponse.model_validate(row)

    def list(self) -> list[WorkspaceResponse]:
        with self.database.read() as connection:
            rows = self.repository.list(connection)
        return [WorkspaceResponse.model_validate(row) for row in rows]

    def get(self, workspace_id: str) -> WorkspaceResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, workspace_id)
        return WorkspaceResponse.model_validate(row)

    def update(self, workspace_id: str, payload: WorkspaceUpdate) -> WorkspaceResponse:
        if payload.name is None and payload.account_positioning is None:
            raise ValidationError("At least one editable field is required")
        name = payload.name.strip() if payload.name is not None else None
        if name == "":
            raise ValidationError("Workspace name cannot be blank")
        with self.database.transaction() as connection:
            row = self.repository.update(
                connection,
                workspace_id=workspace_id,
                name=name,
                account_positioning=payload.account_positioning,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return WorkspaceResponse.model_validate(row)

