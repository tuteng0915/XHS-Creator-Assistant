#!/usr/bin/env python3
"""Import a fixed local XHS fixture into the SqsAgent SQLite workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from xhs_mediacrawler_fixture import (  # noqa: E402
    XhsMediaCrawlerExport,
    build_account_profile_markdown,
    build_comments_markdown,
    build_historical_posts_markdown,
    build_xhs_creator_profile_payload,
    infer_creator_display_name,
    load_mediacrawler_export,
)

from app.main import create_app  # noqa: E402
from app.models import (  # noqa: E402
    MediaAssetType,
    MediaAssetUpdate,
    SourceMaterialType,
    SourceMaterialUpdate,
    TextSourceMaterialCreate,
    WorkspaceCreate,
)

DEFAULT_FIXTURE_ROOT = ROOT / "data" / "xhs-fixtures"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 data/xhs-fixtures/<code> 导入当前 SQLite workspace。"
    )
    parser.add_argument("code", choices=["_tt", "QSheep"], help="固定样本代号")
    parser.add_argument("--workspace-id", default="", help="导入到已有 workspace ID")
    parser.add_argument(
        "--workspace-name",
        default="",
        help="未提供 workspace ID 时，按名称查找或创建 workspace",
    )
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=DEFAULT_FIXTURE_ROOT,
        help="fixture 根目录，默认 data/xhs-fixtures",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="只导入文本内容资产，不导入封面图片资产",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture_dir = args.fixture_root / args.code
    export = load_mediacrawler_export(fixture_dir, code=args.code)
    app = create_app()
    workspace = resolve_workspace(
        app,
        workspace_id=args.workspace_id,
        workspace_name=args.workspace_name or f"XHS {args.code} 工作区",
        code=args.code,
    )
    display_name = infer_creator_display_name(export)
    media_ids_by_note = (
        {} if args.skip_images else upsert_cover_media_assets(app, workspace.id, export)
    )
    profile = upsert_text_asset(
        app,
        workspace.id,
        asset_type=SourceMaterialType.XHS_CREATOR_PROFILE,
        name=f"XHS {display_name} 创作者主页",
        legacy_names=[f"XHS {args.code} 创作者主页"],
        content=json.dumps(
            build_xhs_creator_profile_payload(
                export, media_asset_ids_by_note=media_ids_by_note
            ),
            ensure_ascii=False,
            indent=2,
        ),
    )
    legacy_profile = upsert_text_asset(
        app,
        workspace.id,
        asset_type=SourceMaterialType.ACCOUNT_PROFILE,
        name=f"XHS {display_name} 账号概况",
        legacy_names=[f"XHS {args.code} 账号概况"],
        content=build_account_profile_markdown(export),
    )
    historical = upsert_text_asset(
        app,
        workspace.id,
        asset_type=SourceMaterialType.HISTORICAL_POSTS,
        name=f"XHS {display_name} 历史笔记",
        legacy_names=[f"XHS {args.code} 历史笔记"],
        content=build_historical_posts_markdown(
            export, media_asset_ids_by_note=media_ids_by_note
        ),
    )
    comments = upsert_text_asset(
        app,
        workspace.id,
        asset_type=SourceMaterialType.COMMENTS,
        name=f"XHS {display_name} 评论样本",
        legacy_names=[f"XHS {args.code} 评论样本"],
        content=build_comments_markdown(export),
    )
    print(f"workspace: {workspace.id} {workspace.name}")
    print(f"xhs_creator_profile: {profile.id} {profile.name}")
    print(f"account_profile: {legacy_profile.id} {legacy_profile.name}")
    print(f"historical_posts: {historical.id} {historical.name}")
    print(f"comments: {comments.id} {comments.name}")
    print(f"cover_media_assets: {len(media_ids_by_note)}")
    return 0


def resolve_workspace(app, *, workspace_id: str, workspace_name: str, code: str):
    workspace_service = app.state.workspace_service
    if workspace_id:
        return workspace_service.get(workspace_id)
    for workspace in workspace_service.list():
        if workspace.name == workspace_name:
            return workspace
    return workspace_service.create(
        WorkspaceCreate(
            name=workspace_name,
            account_positioning=f"由小红书本地 fixture {code} 导入的创作者内容工作区。",
        )
    )


def upsert_text_asset(
    app,
    workspace_id: str,
    *,
    asset_type: SourceMaterialType,
    name: str,
    legacy_names: list[str] | None = None,
    content: str,
):
    service = app.state.input_asset_service
    target_names = [name, *(legacy_names or [])]
    for asset in service.list(workspace_id, asset_type):
        if asset.name in target_names:
            return service.update(
                asset.id,
                SourceMaterialUpdate(
                    name=name,
                    content=content,
                    expected_updated_at=asset.updated_at,
                ),
            )
    return service.create_text(
        workspace_id,
        TextSourceMaterialCreate(type=asset_type, name=name, content=content),
    )


def upsert_cover_media_assets(
    app, workspace_id: str, export: XhsMediaCrawlerExport
) -> dict[str, str]:
    service = app.state.media_asset_service
    existing = {
        asset.name: asset
        for asset in service.list(workspace_id, MediaAssetType.IMAGE)
    }
    media_ids_by_note: dict[str, str] = {}
    for note in export.notes:
        if note.cover_path is None:
            continue
        name = cover_media_asset_name(note.title)
        legacy_name = f"XHS {export.code} 封面 - {note.note_id}"
        caption = cover_media_asset_caption(note.desc, note.title)
        matched = existing.get(name) or existing.get(legacy_name)
        if matched:
            updated = service.update(
                matched.id,
                MediaAssetUpdate(
                    name=name,
                    purpose="小红书笔记封面",
                    metadata=cover_media_asset_metadata(
                        matched.metadata,
                        export=export,
                        note=note,
                        caption=caption,
                    ),
                    user_notes=caption,
                    expected_updated_at=matched.updated_at,
                ),
            )
            existing.pop(legacy_name, None)
            existing[name] = updated
            media_ids_by_note[note.note_id] = updated.id
            continue
        asset = service.create_upload(
            workspace_id,
            asset_type=MediaAssetType.IMAGE,
            name=name,
            purpose="小红书笔记封面",
            filename=note.cover_path.name,
            media_type="image/jpeg",
            content=note.cover_path.read_bytes(),
        )
        asset = service.update(
            asset.id,
            MediaAssetUpdate(
                expected_updated_at=asset.updated_at,
                metadata=cover_media_asset_metadata(
                    asset.metadata,
                    export=export,
                    note=note,
                    caption=caption,
                ),
                user_notes=caption,
            ),
        )
        media_ids_by_note[note.note_id] = asset.id
    return media_ids_by_note


def cover_media_asset_name(title: str) -> str:
    clean_title = " ".join((title or "未命名笔记").split())
    for token in ["/", "\\", "\n", "\r", "\t"]:
        clean_title = clean_title.replace(token, " ")
    clean_title = " ".join(clean_title.split()) or "未命名笔记"
    suffix = "_封面"
    return f"{clean_title[:160 - len(suffix)]}{suffix}"


def cover_media_asset_caption(desc: str, title: str) -> str:
    caption = (desc or "").strip() or (title or "").strip()
    return caption[:100_000]


def cover_media_asset_metadata(
    base_metadata: dict,
    *,
    export: XhsMediaCrawlerExport,
    note,
    caption: str,
) -> dict:
    return {
        **base_metadata,
        "source": "xhs_mediacrawler_fixture",
        "fixtureCode": export.code,
        "noteId": note.note_id,
        "noteUrl": note.note_url,
        "title": note.title,
        "caption": caption,
    }


if __name__ == "__main__":
    raise SystemExit(main())
