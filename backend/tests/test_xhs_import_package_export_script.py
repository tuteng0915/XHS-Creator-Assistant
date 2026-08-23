from __future__ import annotations

import json
import subprocess
from pathlib import Path

from test_xhs_mediacrawler_fixture import write_jsonl


def test_generic_xhs_import_package_export_script(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    xhs_dir = tmp_path / "mediacrawler" / "data" / "sample" / "xhs"
    write_jsonl(
        xhs_dir / "jsonl" / "creator_contents_2026-08-22.jsonl",
        [
            {
                "note_id": "n1",
                "nickname": "样例账号",
                "type": "normal",
                "title": "第一条笔记",
                "desc": "正文",
                "liked_count": "10",
            }
        ],
    )
    write_jsonl(
        xhs_dir / "jsonl" / "creator_comments_2026-08-22.jsonl",
        [{"comment_id": "c1", "note_id": "n1", "content": "评论"}],
    )
    cover = xhs_dir / "images" / "n1" / "0.jpg"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b"jpg")
    output_dir = tmp_path / "package"

    completed = subprocess.run(
        [
            str(root / "backend" / ".venv" / "bin" / "python"),
            str(root / "scripts" / "export_xhs_import_package.py"),
            "--input",
            str(xhs_dir),
            "--output",
            str(output_dir),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "display_name: 样例账号" in completed.stdout
    assert "notes: 1" in completed.stdout
    assert "covers: 1" in completed.stdout
    payload = json.loads((output_dir / "xhs_creator_profile.json").read_text())
    assert payload["creator"]["displayName"] == "样例账号"
    assert (output_dir / "images" / "n1" / "0.jpg").read_bytes() == b"jpg"
