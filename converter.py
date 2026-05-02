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

from pipeline.tex import strip_comments, remove_draft_annotations, remove_draft_packages, remove_comment_environments, ensure_pdfoutput
from pipeline.bibtex import normalize_bibtex
from pipeline.deps import find_included_tex, find_used_images, find_used_bib_files, find_used_style_files
from pipeline.config import load_config, apply_config
from pipeline.images import resize_image, DEFAULT_MAX_PX

IMAGE_EXTS = {'.pdf', '.png', '.jpg', '.jpeg', '.eps', '.svg', '.tikz'}


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


def _warn_compliance(main_tex: Path, all_sources: list[str], root: Path):
    """Print warnings for common arXiv compliance issues."""
    combined = '\n'.join(all_sources)

    # Double-spacing / referee mode
    if re.search(r'\\documentclass\[[^\]]*\b(referee|doublespace|doubleblind)\b', combined):
        print("  [warn] 'referee' or 'doublespace' option detected in \\documentclass — "
              "arXiv requires single-spaced submissions")
    if re.search(r'\\(doublespacing|setstretch\s*\{[2-9])', combined):
        print("  [warn] double-spacing command detected — arXiv requires single-spaced submissions")

    # Custom style/class files included
    for path in root.rglob('*'):
        if path.suffix.lower() in {'.cls', '.sty'}:
            print(f"  [warn] custom style file kept: {path.relative_to(root)} — "
                  "verify this is not already provided by TeX Live")

    # \today in \date
    if re.search(r'\\date\s*\{[^}]*\\today', combined):
        print("  [warn] \\today used in \\date — arXiv may rebuild the PDF and the date will change")

    # .eps images (not supported by pdflatex)
    for path in root.rglob('*.eps'):
        print(f"  [warn] .eps image found: {path.relative_to(root)} — "
              "pdflatex does not support .eps; convert to .pdf or .png")


def convert(input_zip: Path, output_zip: Path, main_hint: str | None = None,
            compile_pdf: bool = False, resize: int | None = None,
            config_path: Path | None = None):
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
        used_style_files = find_used_style_files(all_sources)

        # Build whitelist of resolved absolute paths to keep
        whitelist = {p.resolve() for p in all_tex_files if p.exists()}
        whitelist |= used_image_paths
        # Add .bib files
        for path in root.rglob('*.bib'):
            if path.name in used_bib_files:
                whitelist.add(path.resolve())
        # Add used support files (.cls, .sty) and always-keep types (.bst, .ind, .gls, .nls, .bbl)
        main_stem = main_tex.stem
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            at_root = path.parent == root
            if ext in {'.cls', '.sty'} and path.name in used_style_files and at_root:
                whitelist.add(path.resolve())
            elif ext == '.bst' and at_root:
                whitelist.add(path.resolve())
            elif ext == '.bbl' and path.stem == main_stem and at_root:
                whitelist.add(path.resolve())
            elif ext in {'.ind', '.gls', '.nls'} and at_root:
                whitelist.add(path.resolve())

        user_config = load_config(config_path) if config_path else {}

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

            # Resize images if requested
            if resize and path.suffix.lower() in IMAGE_EXTS:
                if resize_image(path, max_px=resize):
                    print(f"  resized: {rel}")

            # Process .tex files
            if path.suffix == '.tex' and path.resolve() in {p.resolve() for p in all_tex_files}:
                src = path.read_text(encoding='utf-8', errors='replace')
                src = strip_comments(src)
                src = remove_comment_environments(src)
                src = remove_draft_annotations(src)
                src = remove_draft_packages(src)
                if user_config:
                    src = apply_config(src, user_config)
                if path == main_tex:
                    src = ensure_pdfoutput(src)
                path.write_text(src, encoding='utf-8')

            # Process .bib files
            if path.suffix == '.bib' and path.name in used_bib_files:
                src = path.read_text(encoding='utf-8', errors='replace')
                src = normalize_bibtex(src)
                path.write_text(src, encoding='utf-8')

        # 3b. Compliance warnings
        _warn_compliance(main_tex, all_sources, root)

        # 4. Repack
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob('*')):
                if path.is_file():
                    zf.write(path, path.relative_to(root))

        print(f"\nDone → {output_zip}")

    if compile_pdf:
        _compile(output_zip, main_hint)


def _open_file(path: Path) -> None:
    """Open a file with the OS default viewer, cross-platform."""
    if sys.platform == 'win32':
        subprocess.run(['start', str(path)], shell=True)
    elif sys.platform == 'darwin':
        subprocess.run(['open', str(path)])
    else:
        subprocess.run(['xdg-open', str(path)])


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
                cwd=run_dir, capture_output=True
            )
            stdout = result.stdout.decode('utf-8', errors='replace')
            if '! Fatal error' in stdout or ('! ' in stdout and 'Output written' not in stdout):
                errors = [line for line in stdout.splitlines() if line.startswith('!')]
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
            _open_file(out_pdf)
        else:
            print("  [compile] PDF not produced")


def main():
    parser = argparse.ArgumentParser(description='Convert LaTeX zip to arXiv-ready zip')
    parser.add_argument('input', help='Input .zip file')
    parser.add_argument('output', nargs='?', help='Output .zip file (default: input_arxiv.zip)')
    parser.add_argument('--main', help='Filename of the main .tex file (e.g. JASA_main.tex)')
    parser.add_argument('--compile', action='store_true', help='Compile output with pdflatex and open PDF')
    parser.add_argument('--resize', type=int, metavar='PX',
                        help=f'Resize images so longest side <= PX pixels (default: {DEFAULT_MAX_PX} if flag given)')
    parser.add_argument('--config', metavar='FILE',
                        help='YAML config for custom removal rules (see arxiv_config.yaml)')
    args = parser.parse_args()

    inp = Path(args.input)
    out = Path(args.output) if args.output else inp.with_stem(inp.stem + '_arxiv')
    config_path = Path(args.config) if args.config else None
    print(f"Converting {inp} → {out}\n")
    convert(inp, out, main_hint=args.main, compile_pdf=args.compile,
            resize=args.resize, config_path=config_path)


if __name__ == '__main__':
    main()
