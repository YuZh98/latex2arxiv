"""Shared Background steps + small helpers used by every surface."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from pytest_bdd import given, parsers

CONVERTER = Path(__file__).resolve().parent.parent.parent.parent / "converter.py"


def build_paper_zip(project_dir: Path, body: str, zip_name: str = "paper.zip") -> Path:
    """Write a single-file LaTeX project to a zip inside project_dir."""
    src = project_dir / "src"
    src.mkdir(exist_ok=True)
    main = src / "main.tex"
    main.write_text(body)
    zip_path = project_dir / zip_name
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(main, arcname="main.tex")
    return zip_path


def build_multifile_zip(project_dir: Path, files: dict, zip_name: str = "paper.zip") -> Path:
    """Write a multi-file LaTeX project to a zip inside project_dir.

    `files` maps zip-relative paths (e.g. "main.tex", "sec/intro.tex") to
    file contents (str for text, bytes for binary).
    """
    src = project_dir / "src"
    src.mkdir(exist_ok=True)
    zip_path = project_dir / zip_name
    with zipfile.ZipFile(zip_path, "w") as zf:
        for arc, content in files.items():
            on_disk = src / arc
            on_disk.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                on_disk.write_bytes(content)
            else:
                on_disk.write_text(content)
            zf.write(on_disk, arcname=arc)
    return zip_path


def parse_json(stdout: str) -> dict:
    return json.loads(stdout)


def lookup_field(obj: dict, dotted: str):
    cur = obj
    for part in dotted.split("."):
        cur = cur[part]
    return cur


def coerce_literal(token: str):
    if token == "true":
        return True
    if token == "false":
        return False
    if token == "null":
        return None
    try:
        return int(token)
    except ValueError:
        return token


@given("the `latex2arxiv` CLI is installed")
def _cli_present():
    assert CONVERTER.exists(), f"converter.py not found at {CONVERTER}"


@given(parsers.parse('a LaTeX project zip "{name}"'))
def _project_zip(project_dir, tex_content, name):
    build_paper_zip(project_dir, tex_content["body"], zip_name=name)
