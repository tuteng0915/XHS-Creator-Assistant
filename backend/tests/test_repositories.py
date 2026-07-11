from app.db.database import SQLiteDatabase
from app.errors import ConflictError
from app.repositories import SourceMaterialRepository, WorkspaceRepository


def test_workspace_repository_preserves_chinese_and_versions(settings) -> None:
    database = SQLiteDatabase(settings.database_path)
    database.migrate()
    repository = WorkspaceRepository()

    with database.transaction() as connection:
        created = repository.create(
            connection,
            name="留学创作者",
            account_positioning="真实反思 + 决策方法，不贩卖焦虑。",
            now="2026-07-11T10:00:00.000000+00:00",
        )

    with database.transaction() as connection:
        updated = repository.update(
            connection,
            workspace_id=created["id"],
            name="留学创作者工作区",
            account_positioning="帮助文科生做留学决策。",
            expected_updated_at=created["updated_at"],
            now="2026-07-11T10:01:00.000000+00:00",
        )

    assert updated["name"] == "留学创作者工作区"
    assert updated["account_positioning"] == "帮助文科生做留学决策。"
    assert updated["positioning_version"] == 2

    with database.read() as connection:
        versions = connection.execute(
            """
            SELECT positioning_text FROM positioning_versions
            WHERE workspace_id = ? ORDER BY version_number
            """,
            (created["id"],),
        ).fetchall()
    assert [row["positioning_text"] for row in versions] == [
        "真实反思 + 决策方法，不贩卖焦虑。",
        "帮助文科生做留学决策。",
    ]


def test_source_repository_requires_current_update_token(settings) -> None:
    database = SQLiteDatabase(settings.database_path)
    database.migrate()
    workspace_repository = WorkspaceRepository()
    material_repository = SourceMaterialRepository()

    with database.transaction() as connection:
        workspace = workspace_repository.create(
            connection,
            name="测试",
            account_positioning="定位",
            now="2026-07-11T10:00:00.000000+00:00",
        )
        material = material_repository.create_text(
            connection,
            workspace_id=workspace["id"],
            material_type="comments",
            name="评论样本",
            content="第一条评论",
            now="2026-07-11T10:00:00.000000+00:00",
        )

    with database.transaction() as connection:
        material_repository.update(
            connection,
            material_id=material["id"],
            name=None,
            content="已更新评论",
            keyword=None,
            expected_updated_at=material["updated_at"],
            now="2026-07-11T10:01:00.000000+00:00",
        )

    try:
        with database.transaction() as connection:
            material_repository.update(
                connection,
                material_id=material["id"],
                name=None,
                content="过期覆盖",
                keyword=None,
                expected_updated_at=material["updated_at"],
                now="2026-07-11T10:02:00.000000+00:00",
            )
    except ConflictError:
        pass
    else:
        raise AssertionError("A stale update must be rejected")

