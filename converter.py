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
from importlib import resources

from pipeline.tex import strip_comments, remove_draft_annotations, remove_draft_packages, remove_comment_environments, ensure_pdfoutput
from pipeline.bibtex import normalize_bibtex
from pipeline.deps import find_included_tex, find_used_images, find_used_bib_files, find_used_style_files, find_cited_keys
from pipeline.config import load_config, apply_config
from pipeline.images import resize_image, DEFAULT_MAX_PX

IMAGE_EXTS = {'.pdf', '.png', '.jpg', '.jpeg', '.eps', '.svg', '.tikz'}

# Output zip size threshold for advisory warning (MB).
SIZE_WARN_MB = 50

# Packages that require shell-escape; arXiv compiles without it, so these fail.
_SHELL_ESCAPE_PKGS = ('minted', 'pythontex', 'shellesc')


class Issues:
    """Collect [warn] and [error] events; print as they happen."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def warn(self, msg: str) -> None:
        print(f"  [warn] {msg}")
        self.warnings.append(msg)

    def error(self, msg: str) -> None:
        print(f"  [error] {msg}")
        self.errors.append(msg)


def find_main_tex(root: Path) -> Path | None:
    """Heuristic: find the .tex file containing \\documentclass.

    When multiple candidates exist, prefer files whose name suggests they are
    the main document (contains 'main' or 'arxiv') over response letters,
    supplements, or backups. Warns if the choice is ambiguous.
    """
    candidates = [p for p in root.rglob('*.tex')
                  if not any(part.startswith('__MACOSX') for part in p.parts)]
    with_docclass = []
    for p in candidates:
        try:
            if r'\documentclass' in p.read_text(encoding='utf-8', errors='replace'):
                with_docclass.append(p)
        except Exception:
            continue

    if not with_docclass:
        return candidates[0] if candidates else None
    if len(with_docclass) == 1:
        return with_docclass[0]

    # Multiple candidates: rank by name preference
    _ARXIV = re.compile(r'arxiv', re.IGNORECASE)
    _MAIN = re.compile(r'(^|[_\-])main([_\-]|\.tex$)', re.IGNORECASE)
    _DEPRIORITIZED = re.compile(r'(response|reply|cover|supplement|backup|bak|old|svm)', re.IGNORECASE)

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


def _check_compliance(main_tex: Path, all_sources: list[str], root: Path,
                      tex_files: list[Path] | None,
                      main_stem: str,
                      issues: Issues) -> None:
    """Compliance checks against arXiv requirements. Records [warn] and [error]."""
    combined = '\n'.join(all_sources)
    # Comment-stripped source for package detection (don't flag commented-out usepackage lines).
    combined_nc = re.sub(r'(?<!\\)%[^\n]*', '', combined)

    # Double-spacing / referee mode
    if re.search(r'\\documentclass\[[^\]]*\b(referee|doublespace|doubleblind)\b', combined):
        issues.warn("'referee' or 'doublespace' option detected in \\documentclass — "
                    "arXiv requires single-spaced submissions")
    if re.search(r'\\(doublespacing|setstretch\s*\{[2-9])', combined):
        issues.warn("double-spacing command detected — arXiv requires single-spaced submissions")

    # Custom style/class files included
    for path in root.rglob('*'):
        if path.suffix.lower() in {'.cls', '.sty'}:
            issues.warn(f"custom style file kept: {path.relative_to(root)} — "
                        "verify this is not already provided by TeX Live")

    # \today in \date
    if re.search(r'\\date\s*\{[^}]*\\today', combined):
        issues.warn("\\today used in \\date — arXiv may rebuild the PDF and the date will change")

    # .eps images (not supported by pdflatex)
    for path in root.rglob('*.eps'):
        issues.warn(f".eps image found: {path.relative_to(root)} — "
                    "pdflatex does not support .eps; convert to .pdf or .png")

    # \subfile'd documents that contain \bibliographystyle (likely standalone supplements)
    if tex_files:
        main_src = main_tex.read_text(encoding='utf-8', errors='replace')
        subfiles = re.findall(r'\\subfile\{([^}]+)\}', re.sub(r'(?<!\\)%[^\n]*', '', main_src))
        for sf in subfiles:
            sf_path = (main_tex.parent / (sf if sf.endswith('.tex') else sf + '.tex')).resolve()
            for tf in tex_files:
                if tf.resolve() == sf_path:
                    sf_src = tf.read_text(encoding='utf-8', errors='replace')
                    if re.search(r'\\bibliographystyle\{', sf_src):
                        issues.warn(f"{tf.relative_to(root.resolve())} (via \\subfile) contains \\bibliographystyle — "
                                    "if this is a standalone supplement, remove the \\subfile line before arXiv submission "
                                    "to avoid duplicate bibliography commands")

    # Shell-escape packages (arXiv compiles without --shell-escape, so these fail).
    for pkg in _SHELL_ESCAPE_PKGS:
        if re.search(r'\\usepackage(?:\[[^\]]*\])?\{[^}]*\b' + pkg + r'\b[^}]*\}', combined_nc):
            issues.error(f"\\usepackage{{{pkg}}} requires shell-escape — arXiv compiles without it; "
                         "this submission will fail to build")

    # psfig is no longer supported by arXiv.
    if re.search(r'\\usepackage(?:\[[^\]]*\])?\{[^}]*\bpsfig\b[^}]*\}', combined_nc):
        issues.error("\\usepackage{psfig} — arXiv no longer supports the psfig package; "
                     "convert figure inclusions to \\includegraphics from graphicx")

    # fontspec / unicode-math require XeLaTeX or LuaLaTeX; arXiv defaults to pdfLaTeX.
    for pkg in ('fontspec', 'unicode-math'):
        if re.search(r'\\usepackage(?:\[[^\]]*\])?\{[^}]*\b' + pkg + r'\b[^}]*\}', combined_nc):
            issues.error(f"\\usepackage{{{pkg}}} requires XeLaTeX or LuaLaTeX — "
                         "arXiv defaults to pdfLaTeX and this submission will fail to build")

    # xr / xr-hyper break because file paths/locations differ on arXiv's servers.
    # Longer alternative listed first so the captured group prefers xr-hyper over xr.
    m = re.search(r'\\usepackage(?:\[[^\]]*\])?\{[^}]*\b(xr-hyper|xr)\b[^}]*\}', combined_nc)
    if m:
        issues.warn(f"\\usepackage{{{m.group(1)}}} detected — file paths/locations differ "
                    "on arXiv and external-document references will likely break; "
                    "see https://info.arxiv.org/help/submit_tex.html for the recommended workaround")

    # arXiv compiles from the submission root; main.tex in a subdirectory will not be found.
    if main_tex.parent != root:
        rel = main_tex.relative_to(root)
        issues.warn(f"main tex '{rel}' is not at the submission root — "
                    "arXiv compiles from root and will not find it; move it up "
                    "or repackage from inside the directory that contains it")

    # arXiv does not run makeindex / glossary processors — pre-built files must ship.
    # Without them, the printed section silently disappears.
    if re.search(r'\\printindex\b', combined_nc) and not any(root.glob('*.ind')):
        issues.warn("\\printindex used but no .ind file at root — arXiv does not run "
                    "makeindex; build locally and re-run latex2arxiv (the .ind will be "
                    "included automatically)")
    if re.search(r'\\printglossar(?:y|ies)\b', combined_nc) and not any(root.glob('*.gls')):
        issues.warn("\\printglossary used but no .gls file at root — arXiv does not run "
                    "the glossaries processor; build locally and re-run latex2arxiv (the "
                    ".gls will be included automatically)")
    if re.search(r'\\printnomenclature\b', combined_nc) and not any(root.glob('*.nls')):
        issues.warn("\\printnomenclature used but no .nls file at root — arXiv does not "
                    "run makeindex for nomencl; build locally and re-run latex2arxiv (the "
                    ".nls will be included automatically)")

    # biblatex detected: recommend shipping .bbl as a defensive measure.
    if re.search(r'\\usepackage(?:\[[^\]]*\])?\{[^}]*\bbiblatex\b[^}]*\}', combined_nc) \
            or re.search(r'\\addbibresource\{', combined_nc):
        bbl = root / f"{main_stem}.bbl"
        if not bbl.exists():
            issues.warn(f"biblatex detected but no {main_stem}.bbl shipped — "
                        "if arXiv cannot resolve any .bib file, it will block your submission; "
                        "include the .bbl as a fallback")


def _check_files(root: Path, kept_files: set[Path], issues: Issues) -> None:
    """Filesystem checks over kept files: problematic filenames."""
    for path in sorted(kept_files):
        rel = path.relative_to(root)
        name = path.name

        # Spaces in filenames cause problems with \input{} resolution.
        if ' ' in name:
            issues.warn(f"filename contains spaces: {rel} — rename to avoid \\input/\\includegraphics issues")

        # Non-ASCII filenames are best avoided in TeX submissions.
        try:
            name.encode('ascii')
        except UnicodeEncodeError:
            issues.warn(f"filename contains non-ASCII characters: {rel} — "
                        "rename using ASCII to avoid portability issues")


def _check_output_size(output_zip: Path, issues: Issues) -> None:
    """Warn if the output zip exceeds the advisory size threshold."""
    size_mb = output_zip.stat().st_size / (1024 * 1024)
    if size_mb > SIZE_WARN_MB:
        issues.warn(f"output is {size_mb:.1f} MB (> {SIZE_WARN_MB} MB) — "
                    "consider --resize to shrink images, or split supplementary materials")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _print_summary(removed: int, kept: int, issues: Issues,
                   input_zip: Path, output_zip: Path | None) -> None:
    """One-line conversion summary. Skips size segment in dry-run (no output_zip)."""
    parts = [f"Summary: {removed} removed, {kept} kept"]
    if output_zip is not None:
        in_mb = input_zip.stat().st_size / (1024 * 1024)
        out_mb = output_zip.stat().st_size / (1024 * 1024)
        parts.append(f"{in_mb:.1f} MB → {out_mb:.1f} MB")
    parts.append(f"{_plural(len(issues.errors), 'error')}, {_plural(len(issues.warnings), 'warning')}")
    print(' | '.join(parts))


def convert(input_zip: Path, output_zip: Path, main_hint: str | None = None,
            compile_pdf: bool = False, resize: int | None = None,
            config_path: Path | None = None, dry_run: bool = False) -> Issues:
    issues = Issues()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # 1. Extract — validate member paths first (zip-slip protection).
        # Aborts before any disk write if a member would escape the temp root
        # via .. or absolute-style paths.
        with zipfile.ZipFile(input_zip) as zf:
            root_abs = root.resolve()
            for name in zf.namelist():
                target = (root / name).resolve()
                try:
                    target.relative_to(root_abs)
                except ValueError:
                    print(f"ERROR: refusing to extract — zip contains a path that "
                          f"escapes the extraction root: {name!r}")
                    sys.exit(1)
            zf.extractall(root)

        # Unwrap single top-level directory if present.
        # Ignore macOS zip noise (__MACOSX/ metadata sibling, .DS_Store file)
        # so a zip created via the macOS Finder still unwraps cleanly.
        entries = [p for p in root.iterdir()
                   if p.name != '__MACOSX' and p.name != '.DS_Store']
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

        # Encoding warn: errors='replace' silently inserts U+FFFD for non-UTF-8 bytes.
        # Surface it per-file so users know which source needs re-saving.
        # Resolve both sides — tex_files_list contains a mix of resolved (from
        # find_included_tex) and unresolved (main_tex) paths, and on macOS
        # /var/folders is a symlink to /private/var/folders, breaking a naive
        # relative_to.
        _root_abs = root.resolve()
        for tf, src in zip(tex_files_list, all_sources):
            if '�' in src:
                issues.warn(f"{tf.resolve().relative_to(_root_abs)} contains non-UTF-8 "
                            "bytes — decoded with replacement characters; re-save as "
                            "UTF-8 to avoid corrupted accented/special characters in "
                            "the output")

        used_image_paths, used_image_refs = find_used_images(all_sources, tex_dirs, root)
        used_bib_files = find_used_bib_files(all_sources)
        used_style_files = find_used_style_files(all_sources)
        cited_keys = find_cited_keys(all_sources)

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
            elif at_root and (path.name == '00README' or path.name.startswith('00README.')):
                # arXiv reads 00README / 00README.XXX at root for processor hints,
                # encoding declarations, and aux file lists.
                whitelist.add(path.resolve())

        user_config = load_config(config_path) if config_path else {}
        kept_files: set[Path] = set()
        removed_count = 0

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
                        removed_count += 1
                        if not dry_run:
                            path.unlink()
                        continue
                else:
                    print(f"  remove: {rel}")
                    removed_count += 1
                    if not dry_run:
                        path.unlink()
                    continue

            kept_files.add(path)

            # Resize images if requested
            if resize and path.suffix.lower() in IMAGE_EXTS:
                if dry_run:
                    print(f"  would resize: {rel}")
                elif resize_image(path, max_px=resize):
                    print(f"  resized: {rel}")

            # Process .tex files
            if path.suffix == '.tex' and path.resolve() in {p.resolve() for p in all_tex_files}:
                if dry_run:
                    print(f"  would process (tex): {rel}")
                else:
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
                if dry_run:
                    print(f"  would process (bib): {rel}")
                else:
                    src = path.read_text(encoding='utf-8', errors='replace')
                    src = normalize_bibtex(src, cited_keys=cited_keys)
                    path.write_text(src, encoding='utf-8')

        # 3b. Compliance + pre-flight checks
        _check_compliance(main_tex, all_sources, root,
                          tex_files=tex_files_list, main_stem=main_stem, issues=issues)
        _check_files(root, kept_files, issues)

        # 4. Repack
        if dry_run:
            print(f"\n[dry-run] No output written. Would have created: {output_zip}")
            _print_summary(removed_count, len(kept_files), issues, input_zip, None)
            return issues

        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob('*')):
                if path.is_file():
                    zf.write(path, path.relative_to(root))

        _check_output_size(output_zip, issues)
        print(f"\nDone → {output_zip}")
        _print_summary(removed_count, len(kept_files), issues, input_zip, output_zip)
        if issues.errors:
            print(f"  {len(issues.errors)} pre-flight error(s) — fix before submitting to arXiv")

    if compile_pdf:
        _compile(output_zip, main_hint)
    return issues


def _open_file(path: Path) -> None:
    """Open a file with the OS default viewer, cross-platform."""
    if sys.platform == 'win32':
        subprocess.run(['start', str(path)], shell=True)
    elif sys.platform == 'darwin':
        subprocess.run(['open', str(path)])
    else:
        subprocess.run(['xdg-open', str(path)])


def _format_pdflatex_errors(stdout: str, max_errors: int = 5) -> str:
    """Pair each ``! ...`` error in pdflatex stdout with its file/line context.

    Per error, returns a 3-line block: the ``!`` line, the ``l.NN <prefix>``
    line marker, and the source-line suffix pdflatex prints below it. The
    lookahead from a ``!`` line stops at the next ``!``, the ``l.NN`` line,
    or 6 lines, whichever comes first — so cascading errors with no marker
    yield just their ``!`` line rather than borrowing the next error's marker.
    Capped at ``max_errors`` blocks; blocks are joined by a blank line.
    """
    lines = stdout.splitlines()
    blocks: list[str] = []
    for i, line in enumerate(lines):
        if not line.startswith('!'):
            continue
        block = [line]
        for j in range(i + 1, min(i + 7, len(lines))):
            if lines[j].startswith('!'):
                break
            if lines[j].startswith('l.'):
                block.append(lines[j])
                if j + 1 < len(lines):
                    block.append(lines[j + 1])
                break
        blocks.append('\n'.join(block))
        if len(blocks) >= max_errors:
            break
    return '\n\n'.join(blocks)


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

        def run_pdflatex(final=False):
            try:
                result = subprocess.run(
                    ['pdflatex', '-interaction=nonstopmode', tex_name],
                    cwd=run_dir, capture_output=True
                )
            except FileNotFoundError:
                print("  [compile] pdflatex not found — install TeX Live "
                      "(https://tug.org/texlive/) or MacTeX to use --compile.")
                return False
            stdout = result.stdout.decode('utf-8', errors='replace')
            if final and ('! Fatal error' in stdout or ('! ' in stdout and 'Output written' not in stdout)):
                print("  [compile] pdflatex errors:")
                print(_format_pdflatex_errors(stdout))
                return False
            return True

        if not run_pdflatex():
            # pdflatex not installed — abort early; subsequent calls would print the
            # same error twice more.
            return

        # Run biber for biblatex projects, else bibtex.
        bib_files = list(run_dir.rglob('*.bib'))
        if bib_files:
            main_nc = re.sub(r'(?<!\\)%[^\n]*', '',
                             main_tex.read_text(encoding='utf-8', errors='replace'))
            uses_biblatex = bool(
                re.search(r'\\usepackage(?:\[[^\]]*\])?\{[^}]*\bbiblatex\b[^}]*\}', main_nc)
                or re.search(r'\\addbibresource\{', main_nc)
            )
            cmd = 'biber' if uses_biblatex else 'bibtex'
            print(f"  Running {cmd} ...")
            try:
                result = subprocess.run([cmd, bib_stem], cwd=run_dir, capture_output=True)
            except FileNotFoundError:
                print(f"  [compile] {cmd} not found — install it (part of TeX Live) "
                      f"or pre-compile your .bbl and ship it. Continuing without "
                      f"bibliography processing; citations will be unresolved.")
                result = None
            if result is not None and result.returncode != 0:
                # biber emits to stderr; bibtex emits to stdout — pick whichever has content.
                err = result.stderr.decode('utf-8', errors='replace').strip()
                out = result.stdout.decode('utf-8', errors='replace').strip()
                msg = err or out
                if msg:
                    tail = '\n'.join(msg.splitlines()[-10:])
                    print(f"  [compile] {cmd} failed (exit {result.returncode}):")
                    print(tail)

        # Second and third pass to resolve references
        run_pdflatex()
        if not run_pdflatex(final=True):
            return

        pdf = main_tex.with_suffix('.pdf')
        if pdf.exists():
            out_pdf = output_zip.with_suffix('.pdf')
            shutil.copy(pdf, out_pdf)
            print(f"  PDF → {out_pdf}")
            _open_file(out_pdf)
        else:
            print("  [compile] PDF not produced")


def _is_git_url(s: str) -> bool:
    """Return True if s looks like a git remote URL."""
    return s.startswith(('https://', 'http://', 'git://', 'git@', 'ssh://'))


# Directories and files to exclude when zipping a directory input.
_ZIP_EXCLUDE_DIRS = {'.git', '__pycache__', '__MACOSX', '.DS_Store'}
_ZIP_EXCLUDE_SUFFIXES = {'.pyc', '.pyo'}
_ZIP_EXCLUDE_NAMES = {'.DS_Store', 'Thumbs.db'}


def _zip_directory(directory: Path, tmp_list: list[str]) -> Path:
    """Zip a directory into a temp file and return the zip Path."""
    tmp = tempfile.mkdtemp()
    tmp_list.append(tmp)
    zip_path = Path(tmp) / (directory.name + '.zip')
    root_resolved = directory.resolve()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(directory.rglob('*')):
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
                ['git', 'clone', '--depth', '1', inp_raw, clone_dir],
                check=True, capture_output=True, timeout=300,
            )
        except FileNotFoundError:
            print("ERROR: git not found — install git to use URL input")
            sys.exit(1)
        except subprocess.TimeoutExpired:
            print("ERROR: git clone timed out after 5 minutes")
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(f"ERROR: git clone failed:\n{e.stderr.decode('utf-8', errors='replace').strip()}")
            sys.exit(1)
        return _zip_directory(Path(clone_dir), tmp_list)

    inp = Path(inp_raw)
    if inp.is_dir():
        return _zip_directory(inp, tmp_list)

    if not inp.exists():
        print(f"ERROR: {inp} not found")
        sys.exit(1)
    return inp


def main():
    parser = argparse.ArgumentParser(description='Convert LaTeX zip to arXiv-ready zip')
    parser.add_argument('input', nargs='?', help='Input .zip file, directory, or git URL')
    parser.add_argument('output', nargs='?', help='Output .zip file (default: input_arxiv.zip)')
    parser.add_argument('--main', help='Filename of the main .tex file (e.g. JASA_main.tex)')
    parser.add_argument('--compile', action='store_true', help='Compile output with pdflatex and open PDF')
    parser.add_argument('--resize', type=int, metavar='PX',
                        help=f'Resize images so longest side <= PX pixels (default: {DEFAULT_MAX_PX} if flag given)')
    parser.add_argument('--config', metavar='FILE',
                        help='YAML config for custom removal rules (see arxiv_config.yaml)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview what would be removed/processed without writing any output')
    parser.add_argument('--demo', action='store_true',
                        help='Run the built-in demo project (no input file needed)')
    args = parser.parse_args()

    if args.demo:
        try:
            import pipeline as _pipeline_mod
            ref = resources.files(_pipeline_mod).joinpath('demo_project.zip')
            demo_zip = Path(str(ref))
        except Exception:
            # Fallback: look next to this file
            demo_zip = Path(__file__).parent / 'demo_project.zip'
        if not demo_zip.exists():
            print("ERROR: demo_project.zip not found in package")
            sys.exit(1)
        out = Path('demo_project_arxiv.zip')
        print(f"Running demo: {demo_zip} → {out}\n")

        # If the demo zip ships an arxiv_config.yaml, auto-apply it so --demo
        # exercises the --config code path without requiring user flags.
        with tempfile.TemporaryDirectory() as cfg_tmp:
            demo_config: Path | None = None
            with zipfile.ZipFile(demo_zip) as zf:
                cfg_name = next(
                    (n for n in zf.namelist() if Path(n).name == 'arxiv_config.yaml'),
                    None,
                )
                if cfg_name is not None:
                    demo_config = Path(cfg_tmp) / 'arxiv_config.yaml'
                    demo_config.write_bytes(zf.read(cfg_name))

            issues = convert(demo_zip, out, compile_pdf=args.compile,
                             config_path=demo_config, dry_run=args.dry_run)
        if issues.errors:
            sys.exit(1)
        return

    if not args.input:
        parser.error("the following arguments are required: input")

    inp_raw = args.input
    _cleanup_tmp: list[str] = []  # temp dirs to clean up at exit

    try:
        inp = _resolve_input(inp_raw, _cleanup_tmp)
        if args.output:
            out = Path(args.output)
        elif _is_git_url(inp_raw):
            # Derive name from the repo URL (handles both https and git@host:user/repo)
            name_part = inp_raw.rstrip('/').rsplit('/', 1)[-1]
            if ':' in name_part:
                name_part = name_part.rsplit(':', 1)[-1].rsplit('/', 1)[-1]
            repo_name = name_part.removesuffix('.git')
            out = Path(f"{repo_name}_arxiv.zip")
        elif Path(inp_raw).is_dir():
            out = Path(f"{Path(inp_raw).name}_arxiv.zip")
        else:
            out = inp.with_stem(inp.stem + '_arxiv')
        config_path = Path(args.config) if args.config else None
        print(f"Converting {inp_raw} → {out}\n")
        issues = convert(inp, out, main_hint=args.main, compile_pdf=args.compile,
                         resize=args.resize, config_path=config_path, dry_run=args.dry_run)
        if issues.errors:
            sys.exit(1)
    finally:
        for d in _cleanup_tmp:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    main()
