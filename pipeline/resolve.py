"""Input resolution: find the main .tex, recognize git URLs, zip a
directory into the temp archive, resolve --demo / file / directory / URL
inputs to a zip path that convert() can consume."""

import re
import zipfile
import subprocess
import tempfile
from pathlib import Path

from pipeline.types import ConverterError


def find_main_tex(root: Path) -> Path | None:
    """Heuristic: find the .tex file containing \\documentclass.

    When multiple candidates exist, prefer files whose name suggests they are
    the main document (contains 'main' or 'arxiv') over response letters,
    supplements, or backups. Warns if the choice is ambiguous.
    """
    candidates = [p for p in root.rglob("*.tex") if not any(part.startswith("__MACOSX") for part in p.parts)]
    with_docclass = []
    for p in candidates:
        try:
            if r"\documentclass" in p.read_text(encoding="utf-8", errors="replace"):
                with_docclass.append(p)
        except Exception:
            continue

    if not with_docclass:
        return candidates[0] if candidates else None
    if len(with_docclass) == 1:
        return with_docclass[0]

    # Multiple candidates: rank by name preference
    _ARXIV = re.compile(r"arxiv", re.IGNORECASE)
    _MAIN = re.compile(r"(^|[_\-])main([_\-]|\.tex$)", re.IGNORECASE)
    _DEPRIORITIZED = re.compile(r"(response|reply|cover|supplement|backup|bak|old|svm)", re.IGNORECASE)

    def rank(p: Path) -> tuple:
        name = p.name
        if _DEPRIORITIZED.search(name):
            return (2, len(name))
        if _ARXIV.search(name):
            return (0, len(name))
        if _MAIN.search(name):
            return (1, len(name))
        return (2, len(name))

    ranked = sorted(with_docclass, key=rank)
    chosen = ranked[0]

    if rank(ranked[0])[0] == rank(ranked[1])[0] or rank(ranked[0])[0] != 0:
        print(f"  [warn] multiple \\documentclass files found; using '{chosen.relative_to(root)}'")
        print("         use --main to specify the correct file if this is wrong")

    return chosen


def _is_git_url(s: str) -> bool:
    """Return True if s looks like a git remote URL."""
    return s.startswith(("https://", "http://", "git://", "git@", "ssh://"))


# Directories and files to exclude when zipping a directory input.
_ZIP_EXCLUDE_DIRS = {".git", "__pycache__", "__MACOSX", ".DS_Store"}
_ZIP_EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
_ZIP_EXCLUDE_NAMES = {".DS_Store", "Thumbs.db"}


def _zip_directory(directory: Path, tmp_list: list[str]) -> Path:
    """Zip a directory into a temp file and return the zip Path."""
    tmp = tempfile.mkdtemp()
    tmp_list.append(tmp)
    zip_path = Path(tmp) / (directory.name + ".zip")
    root_resolved = directory.resolve()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(directory.rglob("*")):
            if not file.is_file():
                continue
            # Skip symlinks that point outside the project
            if file.is_symlink():
                try:
                    file.resolve().relative_to(root_resolved)
                except ValueError:
                    continue
            # Skip junk directories and files
            if _ZIP_EXCLUDE_DIRS & set(file.parts):
                continue
            if file.suffix in _ZIP_EXCLUDE_SUFFIXES:
                continue
            if file.name in _ZIP_EXCLUDE_NAMES:
                continue
            zf.write(file, file.relative_to(directory))
    return zip_path


def _resolve_input(inp_raw: str, tmp_list: list[str]) -> Path:
    """Normalize input (zip path, directory, or git URL) to a zip Path."""
    if _is_git_url(inp_raw):
        print(f"  Cloning {inp_raw} ...")
        clone_dir = tempfile.mkdtemp()
        tmp_list.append(clone_dir)
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", inp_raw, clone_dir],
                check=True,
                capture_output=True,
                timeout=300,
            )
        except FileNotFoundError:
            raise ConverterError("git not found — install git to use URL input")
        except subprocess.TimeoutExpired:
            raise ConverterError("git clone timed out after 5 minutes")
        except subprocess.CalledProcessError as e:
            raise ConverterError("git clone failed:\n" + e.stderr.decode("utf-8", errors="replace").strip())
        return _zip_directory(Path(clone_dir), tmp_list)

    inp = Path(inp_raw)
    if inp.is_dir():
        return _zip_directory(inp, tmp_list)

    if not inp.exists():
        raise ConverterError(f"{inp} not found")
    return inp
