#!/usr/bin/env python3
"""
latex_arxiv_converter — convert a LaTeX .zip to an arXiv-ready .zip

Usage:
    python3 converter.py input.zip [output.zip] [--main MAIN_TEX]
"""

import re
import sys
import argparse
import zipfile
import tempfile
import shutil
import subprocess
from pathlib import Path

from pipeline.tex import strip_comments, remove_draft_annotations, remove_draft_packages, ensure_pdfoutput
from pipeline.bibtex import normalize_bibtex
from pipeline.deps import find_included_tex, find_used_images, find_used_bib_files

IMAGE_EXTS = {'.pdf', '.png', '.jpg', '.jpeg', '.eps', '.svg', '.tikz'}

# Non-tex support files arXiv may need
SUPPORT_EXTS = {'.cls', '.sty', '.bst', '.ind', '.gls', '.nls', '.bbl'}


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


def convert(input_zip: Path, output_zip: Path, main_hint: str | None = None, compile_pdf: bool = False):
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
        if main_hint:
            main_tex = next((p for p in root.rglob('*.tex') if p.name == main_hint), None)
            if main_tex is None:
                print(f"ERROR: --main '{main_hint}' not found in archive")
                sys.exit(1)
        else:
            main_tex = find_main_tex(root)
        if main_tex is None:
            print("ERROR: no .tex file found in archive")
            sys.exit(1)
        print(f"  main tex: {main_tex.relative_to(root)}")

        all_tex_files = {main_tex}
        main_source = main_tex.read_text(encoding='utf-8', errors='replace')
        all_tex_files |= find_included_tex(main_source, main_tex.parent, root, {main_tex})

        # Collect sources + their directories for image resolution
        tex_files_list = [p for p in all_tex_files if p.exists()]
        all_sources = [p.read_text(encoding='utf-8', errors='replace') for p in tex_files_list]
        tex_dirs = [p.parent for p in tex_files_list]

        used_image_paths, used_image_refs = find_used_images(all_sources, tex_dirs, root)
        used_bib_files = find_used_bib_files(all_sources)

        # Build whitelist of resolved absolute paths to keep
        whitelist = {p.resolve() for p in all_tex_files if p.exists()}
        whitelist |= used_image_paths
        # Add .bib files
        for path in root.rglob('*.bib'):
            if path.name in used_bib_files:
                whitelist.add(path.resolve())
        # Add support files (.cls, .sty, .bst, .ind, .gls, .nls, .bbl)
        for path in root.rglob('*'):
            if path.is_file() and path.suffix.lower() in SUPPORT_EXTS:
                whitelist.add(path.resolve())

        # 3. Process each file
        for path in list(root.rglob('*')):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            resolved = path.resolve()

            # Keep only whitelisted files; delete everything else
            if resolved not in whitelist:
                # Second chance for images: match by stem/name in case path resolution failed
                if path.suffix.lower() in IMAGE_EXTS:
                    name, stem = path.name, path.stem
                    if name in used_image_refs or stem in used_image_refs:
                        pass  # keep it
                    else:
                        print(f"  remove: {rel}")
                        path.unlink()
                        continue
                else:
                    print(f"  remove: {rel}")
                    path.unlink()
                    continue

            # Process .tex files
            if path.suffix == '.tex' and path.resolve() in {p.resolve() for p in all_tex_files}:
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

    if compile_pdf:
        _compile(output_zip, main_hint)


def _compile(output_zip: Path, main_hint: str | None):
    """Extract output zip, run pdflatex twice, and open the resulting PDF."""
    with tempfile.TemporaryDirectory() as tmpdir:
        compile_dir = Path(tmpdir)
        with zipfile.ZipFile(output_zip) as zf:
            zf.extractall(compile_dir)

        # Find main tex
        if main_hint:
            main_tex = next((p for p in compile_dir.rglob('*.tex') if p.name == main_hint), None)
        else:
            main_tex = next(
                (p for p in compile_dir.rglob('*.tex')
                 if r'\documentclass' in p.read_text(encoding='utf-8', errors='replace')),
                None
            )
        if main_tex is None:
            print("  [compile] ERROR: could not find main .tex in output zip")
            return

        print(f"\nCompiling {main_tex.name} ...")
        run_dir = main_tex.parent
        tex_name = main_tex.name
        bib_stem = main_tex.stem

        def run_pdflatex():
            result = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', tex_name],
                cwd=run_dir, capture_output=True, text=True
            )
            if '! Fatal error' in result.stdout or ('! ' in result.stdout and 'Output written' not in result.stdout):
                errors = [l for l in result.stdout.splitlines() if l.startswith('!')]
                print("  [compile] pdflatex errors:")
                print('\n'.join(errors[:10]))
                return False
            return True

        if not run_pdflatex():
            return

        # Run bibtex if a .bib file is present
        bib_files = list(run_dir.glob('*.bib'))
        if bib_files:
            subprocess.run(['bibtex', bib_stem], cwd=run_dir, capture_output=True)

        # Second and third pass to resolve references
        run_pdflatex()
        run_pdflatex()

        pdf = main_tex.with_suffix('.pdf')
        if pdf.exists():
            out_pdf = output_zip.with_suffix('.pdf')
            shutil.copy(pdf, out_pdf)
            print(f"  PDF → {out_pdf}")
            subprocess.run(['open', str(out_pdf)])  # macOS
        else:
            print("  [compile] PDF not produced")


def main():
    parser = argparse.ArgumentParser(description='Convert LaTeX zip to arXiv-ready zip')
    parser.add_argument('input', help='Input .zip file')
    parser.add_argument('output', nargs='?', help='Output .zip file (default: input_arxiv.zip)')
    parser.add_argument('--main', help='Filename of the main .tex file (e.g. JASA_main.tex)')
    parser.add_argument('--compile', action='store_true', help='Compile output with pdflatex and open PDF')
    args = parser.parse_args()

    inp = Path(args.input)
    out = Path(args.output) if args.output else inp.with_stem(inp.stem + '_arxiv')
    print(f"Converting {inp} → {out}\n")
    convert(inp, out, main_hint=args.main, compile_pdf=args.compile)


if __name__ == '__main__':
    main()
