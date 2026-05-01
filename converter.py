#!/usr/bin/env python3
"""
latex_arxiv_converter — convert a LaTeX .zip to an arXiv-ready .zip

Usage:
    python converter.py input.zip [output.zip]
"""

import re
import sys
import zipfile
import tempfile
import shutil
from pathlib import Path

from pipeline.tex import strip_comments, remove_draft_annotations, remove_draft_packages, ensure_pdfoutput
from pipeline.bibtex import normalize_bibtex
from pipeline.deps import find_included_tex, find_used_images, find_used_bib_files

# Files/dirs to always remove
_JUNK_PATTERNS = {
    '.DS_Store', 'Thumbs.db',
    '.aux', '.log', '.out', '.toc', '.lof', '.lot', '.bbl', '.blg',
    '.synctex.gz', '.fls', '.fdb_latexmk', '.nav', '.snm', '.vrb',
}
_JUNK_DIRS = {'.vscode', '.idea', '__pycache__', '.git'}

IMAGE_EXTS = {'.pdf', '.png', '.jpg', '.jpeg', '.eps', '.svg', '.tikz'}


def is_junk(path: Path) -> bool:
    if path.name in _JUNK_PATTERNS:
        return True
    if path.suffix in _JUNK_PATTERNS:
        return True
    if any(part in _JUNK_DIRS for part in path.parts):
        return True
    return False


def find_main_tex(root: Path) -> Path | None:
    """Heuristic: find the .tex file containing \\documentclass."""
    candidates = list(root.rglob('*.tex'))
    for p in candidates:
        try:
            if r'\documentclass' in p.read_text(encoding='utf-8', errors='replace'):
                return p
        except Exception:
            continue
    return candidates[0] if candidates else None


def convert(input_zip: Path, output_zip: Path):
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # 1. Extract
        with zipfile.ZipFile(input_zip) as zf:
            zf.extractall(root)

        # Unwrap single top-level directory if present
        entries = [p for p in root.iterdir()]
        if len(entries) == 1 and entries[0].is_dir():
            root = entries[0]

        # 2. Find main .tex and all included .tex files
        main_tex = find_main_tex(root)
        if main_tex is None:
            print("ERROR: no .tex file found in archive")
            sys.exit(1)
        print(f"  main tex: {main_tex.relative_to(root)}")

        all_tex_files = {main_tex}
        main_source = main_tex.read_text(encoding='utf-8', errors='replace')
        all_tex_files |= find_included_tex(main_source, main_tex.parent, {main_tex})

        # Collect all tex sources for dependency analysis
        all_sources = []
        for p in all_tex_files:
            if p.exists():
                all_sources.append(p.read_text(encoding='utf-8', errors='replace'))

        used_images = find_used_images(all_sources)
        used_bib_files = find_used_bib_files(all_sources)

        # 3. Process each file
        for path in list(root.rglob('*')):
            if not path.is_file():
                continue
            rel = path.relative_to(root)

            # Remove junk files
            if is_junk(rel):
                print(f"  remove junk: {rel}")
                path.unlink()
                continue

            # Remove unused .tex files
            if path.suffix == '.tex' and path not in all_tex_files:
                print(f"  remove unused tex: {rel}")
                path.unlink()
                continue

            # Remove unused .bib files
            if path.suffix == '.bib' and path.name not in used_bib_files:
                print(f"  remove unused bib: {rel}")
                path.unlink()
                continue

            # Remove unused images
            if path.suffix.lower() in IMAGE_EXTS:
                stem = path.stem
                name = path.name
                # Match by full name or stem (\\includegraphics may omit extension)
                if name not in used_images and stem not in used_images:
                    print(f"  remove unused image: {rel}")
                    path.unlink()
                    continue

            # Process .tex files
            if path.suffix == '.tex' and path in all_tex_files:
                src = path.read_text(encoding='utf-8', errors='replace')
                src = strip_comments(src)
                src = remove_draft_annotations(src)
                src = remove_draft_packages(src)
                if path == main_tex:
                    src = ensure_pdfoutput(src)
                path.write_text(src, encoding='utf-8')

            # Process .bib files
            if path.suffix == '.bib' and path.name in used_bib_files:
                src = path.read_text(encoding='utf-8', errors='replace')
                src = normalize_bibtex(src)
                path.write_text(src, encoding='utf-8')

        # 4. Repack
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob('*')):
                if path.is_file():
                    zf.write(path, path.relative_to(root))

        print(f"\nDone → {output_zip}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_stem(inp.stem + '_arxiv')
    print(f"Converting {inp} → {out}\n")
    convert(inp, out)
