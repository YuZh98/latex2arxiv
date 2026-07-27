"""Pre-flight checks run by convert() before emitting the output zip.

Each check emits issues via the Issues collector; none raise. Imported by
converter.py and called inline from convert() at their original call sites
(call-site order is part of the public behavior contract — do not consolidate)."""

import re
from pathlib import Path

from pipeline.deps import uses_biblatex
from pipeline.types import Issues

# Packages that require shell-escape; arXiv compiles without it, so these fail.
# Matched by exact name against comma-split \usepackage arguments, not as a regex
# substring — otherwise 'pst-pdf' would falsely match inside 'auto-pst-pdf'.
_SHELL_ESCAPE_PKGS = frozenset({"minted", "pythontex", "shellesc", "auto-pst-pdf", "pst-pdf"})

# Output zip size advisory threshold (MB). Re-exported by converter.py for
# backward-compatible reads; tests monkeypatch this attribute directly.
SIZE_WARN_MB = 50

# arXiv warns for PNG images exceeding this pixel count (since Feb 2026).
# 34 megapixels ≈ full A4 at 600 dpi.
_MAX_PNG_PIXELS = 34_000_000

# arXiv TeX Live ladder (July 2026): TL2025 default → biblatex 3.20, bbl 3.3;
# TL2023 selectable → bbl 3.2, slated for removal when TL2026 lands.
_ARXIV_BBL_FORMAT_CURRENT = "3.3"
_ARXIV_BBL_FORMAT_TL2023 = "3.2"
_BBL_VERSION_RE = re.compile(r"\$\s*biblatex bbl format version\s+([0-9.]+)\s*\$")


def _has_latex_dvips_mode(root: Path) -> bool:
    """Return True if a 00README file at root specifies latex (dvips) or tex compiler."""
    for name in ("00README", "00README.XXX", "00README.json", "00README.yaml", "00README.yml"):
        readme = root / name
        if not readme.exists():
            continue
        try:
            content = readme.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        # JSON/YAML: "compiler": "latex" or compiler: latex
        if re.search(r'"?compiler"?\s*[:=]\s*"?(latex|tex|latex\+dvips)', content):
            return True
        # Legacy XXX format: nohypertex line or latex directive.
        # Use a word-aware match so "xelatex" / "lualatex" / "pdflatex" don't
        # false-positive here (they are other engines, not latex+dvips).
        if name == "00README.XXX" and re.search(r"(?<!xe)(?<!lua)(?<!pdf)latex", content):
            return True
    return False


def _has_xelatex_mode(root: Path) -> bool:
    """Return True if a 00README at root opts into XeLaTeX or LuaLaTeX.

    Mirrors :func:`_has_latex_dvips_mode`. Matches either the modern
    ``compiler: xelatex`` / ``compiler: lualatex`` directive in 00README /
    00README.json / 00README.yaml, or the legacy ``nohypertex,xelatex`` form
    used in 00README.XXX.
    """
    for name in ("00README", "00README.XXX", "00README.json", "00README.yaml", "00README.yml"):
        readme = root / name
        if not readme.exists():
            continue
        try:
            content = readme.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        # Modern: "compiler": "xelatex" / compiler: lualatex.
        if re.search(r'"?compiler"?\s*[:=]\s*"?(xelatex|lualatex)', content):
            return True
        # Legacy XXX format: a nohypertex line that also mentions xelatex/lualatex.
        if name == "00README.XXX" and re.search(r"(xelatex|lualatex)", content):
            return True
    return False


def _check_compliance(
    main_tex: Path,
    all_sources: list[str],
    root: Path,
    tex_files: list[Path] | None,
    main_stem: str,
    issues: Issues,
    used_bib_files: set[str] | None = None,
    kept_files: set[Path] | None = None,
) -> None:
    """Compliance checks against arXiv requirements. Records [warn] and [error]."""
    combined = "\n".join(all_sources)
    # Comment-stripped source for package detection (don't flag commented-out usepackage lines).
    combined_nc = re.sub(r"(?<!\\)%[^\n]*", "", combined)

    # Double-spacing / referee mode. ('doubleblind' is an anonymization flag in
    # classes like acmart, not a spacing flag — do not match it here.)
    if re.search(r"\\documentclass\[[^\]]*\b(referee|doublespace)\b", combined_nc):
        issues.warn(
            "'referee' or 'doublespace' option detected in \\documentclass — arXiv requires single-spaced submissions"
        )
    if re.search(r"\\(doublespacing|setstretch\s*\{[2-9])", combined_nc):
        issues.warn("double-spacing command detected — arXiv requires single-spaced submissions")

    # \today in \date
    if re.search(r"\\date\s*\{[^}]*\\today", combined_nc):
        issues.warn("\\today used in \\date — arXiv may rebuild the PDF and the date will change")

    # \includeonly restricts which chapters are compiled — almost always a mistake in submissions.
    if re.search(r"\\includeonly\s*\{", combined_nc):
        issues.warn(
            "\\includeonly detected — arXiv will only compile the listed files; "
            "remove \\includeonly so the full paper appears in the output"
        )

    # .eps images — only problematic for pdflatex; valid for latex+dvips mode.
    if not _has_latex_dvips_mode(root):
        for path in root.rglob("*.eps"):
            issues.warn(
                f".eps image found: {path.relative_to(root)} — pdflatex does not support .eps; "
                "convert to .pdf or .png, or use latex+dvips via 00README"
            )

    # \subfile'd documents that contain \bibliographystyle (likely standalone supplements)
    if tex_files:
        main_src = main_tex.read_text(encoding="utf-8", errors="replace")
        subfiles = re.findall(r"\\subfile\{([^}]+)\}", re.sub(r"(?<!\\)%[^\n]*", "", main_src))
        for sf in subfiles:
            sf_path = (main_tex.parent / (sf if sf.endswith(".tex") else sf + ".tex")).resolve()
            for tf in tex_files:
                if tf.resolve() == sf_path:
                    sf_src = tf.read_text(encoding="utf-8", errors="replace")
                    if re.search(r"\\bibliographystyle\{", sf_src):
                        issues.warn(
                            f"{tf.relative_to(root.resolve())} (via \\subfile) contains \\bibliographystyle — "
                            "if this is a standalone supplement, remove the \\subfile line before arXiv submission "
                            "to avoid duplicate bibliography commands"
                        )

    # Shell-escape packages (arXiv compiles without --shell-escape, so these fail).
    # Iterate the comma-separated \usepackage argument so 'pst-pdf' isn't matched
    # as a substring of 'auto-pst-pdf'.
    flagged_shell: set[str] = set()
    for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", combined_nc):
        for raw in m.group(1).split(","):
            name = raw.strip()
            if name in _SHELL_ESCAPE_PKGS and name not in flagged_shell:
                flagged_shell.add(name)
                issues.error(
                    f"\\usepackage{{{name}}} requires shell-escape — arXiv "
                    "compiles without it; this submission will fail to build"
                )

    # svg package shells out to Inkscape, which arXiv does not provide.
    if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\bsvg\b[^}]*\}", combined_nc):
        issues.error(
            "\\usepackage{svg} requires Inkscape via shell-escape — arXiv does not "
            "provide it; convert .svg figures to .pdf or .png and use "
            "\\includegraphics from graphicx"
        )

    # psfig is no longer supported by arXiv.
    if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\bpsfig\b[^}]*\}", combined_nc):
        issues.error(
            "\\usepackage{psfig} — arXiv no longer supports the psfig package; "
            "convert figure inclusions to \\includegraphics from graphicx"
        )

    # fontspec / unicode-math require XeLaTeX or LuaLaTeX; arXiv defaults to pdfLaTeX.
    # XeLaTeX is available via a 00README directive (compiler: xelatex);
    # without that directive the build will fail. With the directive present,
    # the error is suppressed — the user has explicitly opted into XeLaTeX.
    xelatex_opted_in = _has_xelatex_mode(root)
    for pkg in ("fontspec", "unicode-math"):
        if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b" + pkg + r"\b[^}]*\}", combined_nc):
            if xelatex_opted_in:
                continue
            issues.error(
                f"\\usepackage{{{pkg}}} requires XeLaTeX or LuaLaTeX — "
                "arXiv defaults to pdfLaTeX; ship a 00README with "
                "'compiler: xelatex' (or legacy 00README.XXX with "
                "'nohypertex,xelatex') to opt into XeLaTeX, otherwise "
                "this submission will fail to build"
            )

    # xr / xr-hyper break because file paths/locations differ on arXiv's servers.
    # Longer alternative listed first so the captured group prefers xr-hyper over xr.
    m = re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b(xr-hyper|xr)\b[^}]*\}", combined_nc)
    if m:
        issues.warn(
            f"\\usepackage{{{m.group(1)}}} detected — file paths/locations differ "
            "on arXiv and external-document references will likely break; "
            "see https://info.arxiv.org/help/submit_tex.html for the recommended workaround"
        )

    # arXiv compiles from the submission root; main.tex in a subdirectory will not be found.
    if main_tex.parent != root:
        rel = main_tex.relative_to(root)
        issues.warn(
            f"main tex '{rel}' is not at the submission root — "
            "arXiv compiles from root and will not find it; move it up "
            "or repackage from inside the directory that contains it"
        )

    # arXiv does not run makeindex / glossary processors — pre-built files must ship.
    # Without them, the printed section silently disappears.
    if re.search(r"\\printindex\b", combined_nc) and not any(root.glob("*.ind")):
        issues.warn(
            "\\printindex used but no .ind file at root — arXiv does not run "
            "makeindex; build locally and re-run latex2arxiv (the .ind will be "
            "included automatically)"
        )
    if re.search(r"\\printglossar(?:y|ies)\b", combined_nc) and not any(root.glob("*.gls")):
        issues.warn(
            "\\printglossary used but no .gls file at root — arXiv does not run "
            "the glossaries processor; build locally and re-run latex2arxiv (the "
            ".gls will be included automatically)"
        )
    if re.search(r"\\printnomenclature\b", combined_nc) and not any(root.glob("*.nls")):
        issues.warn(
            "\\printnomenclature used but no .nls file at root — arXiv does not "
            "run makeindex for nomencl; build locally and re-run latex2arxiv (the "
            ".nls will be included automatically)"
        )

    # biblatex: arXiv can run Biber natively (since late 2025), but a shipped
    # .bbl must match arXiv's bbl format or AutoTeX hard-errors ("bbl version
    # mismatch"). No .bbl at all is a soft risk (version drift between the
    # author's biber and arXiv's).
    is_biblatex = uses_biblatex([combined_nc])
    if is_biblatex:
        bbl = root / f"{main_stem}.bbl"
        if not bbl.exists():
            issues.warn(
                f"biblatex detected but no {main_stem}.bbl shipped — "
                "arXiv can run Biber natively, but version mismatches between "
                "your TeX Live and arXiv's (currently TL2025, bbl format "
                f"{_ARXIV_BBL_FORMAT_CURRENT}) may break the bibliography; "
                "consider shipping the .bbl as a fallback"
            )
        else:
            try:
                bbl_content = bbl.read_text(encoding="utf-8", errors="replace")
            except OSError:
                bbl_content = ""
            # biber writes the format header on line 2; bounding the scan keeps
            # a version-like string deep in entry text from false-matching.
            m = _BBL_VERSION_RE.search(bbl_content[:2048])
            if m:
                ver = m.group(1)
                if ver == _ARXIV_BBL_FORMAT_TL2023:
                    issues.warn(
                        f"{bbl.name} is bbl format {ver} — accepted only if you "
                        "select TeX Live 2023 (TL2023) at submission, which arXiv "
                        "plans to retire; regenerate with biblatex ≥ 3.20 "
                        f"(bbl format {_ARXIV_BBL_FORMAT_CURRENT}) to be safe"
                    )
                elif ver != _ARXIV_BBL_FORMAT_CURRENT:
                    issues.warn(
                        f"{bbl.name} is bbl format {ver} but arXiv expects "
                        f"{_ARXIV_BBL_FORMAT_CURRENT} — regenerate the .bbl under "
                        "a current TeX Live or let arXiv run Biber from the .bib"
                    )
            elif r"\bibitem" in bbl_content:
                issues.warn(
                    f"{bbl.name} is a BibTeX-format .bbl but the document uses "
                    "biblatex — backend and .bbl must match; regenerate with "
                    "Biber (or the biblatex bibtex backend)"
                )
        if kept_files and any(p.name == "biblatex.sty" for p in kept_files):
            issues.warn(
                "bundled biblatex.sty shipped — arXiv provides its own biblatex, "
                "and outdated bundled copies break compilation "
                '("Patching \\MakeUppercase failed"); remove it from the upload'
            )

    # Non-biblatex BibTeX: if \bibliography{foo} is used but neither foo.bib nor
    # main.bbl is shipped, arXiv will block the submission.
    if used_bib_files is not None and kept_files is not None:
        if not is_biblatex and used_bib_files:
            bbl = root / f"{main_stem}.bbl"
            has_bbl = bbl.exists()
            if not has_bbl:
                kept_names = {p.name for p in kept_files}
                missing = sorted(b for b in used_bib_files if b not in kept_names)
                if missing:
                    issues.error(
                        f"\\bibliography references {', '.join(missing)} but "
                        f"{'it is' if len(missing) == 1 else 'they are'} not in the output "
                        f"and no {main_stem}.bbl is shipped — arXiv will block this submission"
                    )

    # TikZ externalization needs shell-escape to (re)build figures; arXiv won't run it.
    # If the project ships pre-built ``*-figure*.pdf`` files at any depth, the
    # externalization driver will reuse them and the build succeeds.
    if re.search(r"\\tikzexternalize\b", combined_nc):
        prebuilt = list(root.rglob("*-figure*.pdf"))
        if not prebuilt:
            issues.error(
                "\\tikzexternalize used but no pre-externalized '*-figure*.pdf' "
                "files shipped — arXiv compiles without shell-escape and cannot "
                "rebuild externalized figures; build locally and re-run latex2arxiv "
                "(or disable externalization for the arXiv submission)"
            )

    # Absolute paths in \input / \include / \includegraphics will not resolve on
    # arXiv's build servers. Detect Unix (``/``) and Windows-drive (``C:\`` or ``C:/``) forms.
    for m in re.finditer(r"\\(?:input|include|includegraphics)(?:\[[^\]]*\])?\s*\{([^}]+)\}", combined_nc):
        arg = m.group(1).strip()
        if arg.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", arg):
            issues.warn(
                f"absolute path in \\input/\\includegraphics: {arg!r} — arXiv's "
                "build servers will not resolve it; use a path relative to the "
                "submission root"
            )

    # -eps-converted-to.pdf artifacts indicate reliance on on-the-fly eps→pdf
    # conversion that arXiv does not perform. Check the source tree (not kept_files)
    # because these artifacts are typically pruned but their presence signals a problem.
    for path in root.rglob("*-eps-converted-to.pdf"):
        issues.warn(
            f"{path.relative_to(root)} — arXiv does not perform on-the-fly eps→pdf conversion; "
            "convert .eps figures to .pdf yourself and update \\includegraphics paths"
        )


def _check_archive_layout(root: Path, issues: Issues) -> None:
    """Pre-prune scan over EVERY extracted file (not just kept_files).

    Two checks belong here rather than in :func:`_check_files`:

    * shipped ``psfig.sty`` — arXiv hard-rejects this regardless of whether the
      user ``\\usepackage{psfig}``-d it. Without the pre-prune scan, an
      unreferenced ``psfig.sty`` is silently dropped before the error can fire.
    * hidden / dot-files — arXiv deletes files starting with ``.`` upon
      announcement. Same kept-files limitation: ``.arxivignore`` etc. would
      never reach :func:`_check_files`.

    Both checks ignore macOS ``__MACOSX/`` metadata noise and ``.DS_Store`` —
    the extractor strips those before we reach this point, so they would not
    appear in the kept-files set anyway.
    """
    flagged_hidden: set[str] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)

        # Skip macOS metadata noise.
        if any(part == "__MACOSX" or part == ".DS_Store" for part in rel.parts):
            continue

        # Hidden files / dot-directories.
        if any(part.startswith(".") for part in rel.parts):
            # Dedup at the dot-component level so a deep .dir/foo/bar tree
            # only warns once.
            dot_anchor = next(part for part in rel.parts if part.startswith("."))
            if dot_anchor in flagged_hidden:
                continue
            flagged_hidden.add(dot_anchor)
            issues.warn(
                f"hidden file or directory: {rel} — arXiv deletes paths starting with "
                "'.' upon announcement; if your build depends on this, rename it"
            )

        # Shipped psfig.sty at any depth (case-insensitive — Mac/Windows
        # filesystems are case-preserving, so PSFIG.STY / Psfig.sty must
        # still be rejected: arXiv's case-sensitive Linux builder would also
        # fail to resolve them).
        if path.name.lower() == "psfig.sty":
            issues.error(
                f"shipped psfig.sty ({rel}) — arXiv forbids user-supplied psfig.sty "
                "and will fail to build; remove it and migrate to \\includegraphics"
            )


def _check_files(root: Path, kept_files: set[Path], issues: Issues) -> None:
    """Filesystem checks over kept files: problematic filenames, directory names,
    and -eps-converted-to.pdf artifacts.

    Directory components are deduped so a single bad directory containing many
    files only emits one warning per category.

    Note: hidden-file and shipped-psfig.sty checks moved to
    :func:`_check_archive_layout` so they fire BEFORE the keep/prune step
    silently drops the offending file (#174).
    """
    flagged_dir_spaces: set[Path] = set()
    flagged_dir_ascii: set[Path] = set()
    for path in sorted(kept_files):
        rel = path.relative_to(root)

        # Walk directory components: rel.parents includes Path('.') as the last
        # element, which we skip.
        for parent in rel.parents:
            if parent == Path("."):
                continue
            dirname = parent.name
            if " " in dirname and parent not in flagged_dir_spaces:
                flagged_dir_spaces.add(parent)
                issues.warn(
                    f"directory name contains spaces: {parent}/ — rename to avoid \\input/\\includegraphics issues"
                )
            try:
                dirname.encode("ascii")
            except UnicodeEncodeError:
                if parent not in flagged_dir_ascii:
                    flagged_dir_ascii.add(parent)
                    issues.warn(
                        f"directory name contains non-ASCII characters: {parent}/ — "
                        "rename using ASCII to avoid portability issues"
                    )

        name = path.name

        # Spaces in filenames cause problems with \input{} resolution.
        if " " in name:
            issues.warn(f"filename contains spaces: {rel} — rename to avoid \\input/\\includegraphics issues")

        # Non-ASCII filenames are best avoided in TeX submissions.
        try:
            name.encode("ascii")
        except UnicodeEncodeError:
            issues.warn(
                f"filename contains non-ASCII characters: {rel} — rename using ASCII to avoid portability issues"
            )


def _check_oversized_images(kept_files: set[Path], issues: Issues) -> None:
    """Warn if any PNG image exceeds arXiv's 34-megapixel threshold.

    Uses Pillow to read image dimensions without loading pixel data. Images so
    large that Pillow refuses to open them are reported too; other unreadable
    files (corrupt, not actually PNG, etc.) are skipped silently.
    """
    try:
        from PIL import Image
    except ImportError:
        return  # Pillow not available; skip this check silently

    for path in sorted(kept_files):
        if path.suffix.lower() != ".png":
            continue
        try:
            with Image.open(path) as img:
                w, h = img.size
        except Image.DecompressionBombError:
            issues.warn(
                f"oversized PNG '{path.name}': dimensions exceed Pillow's decompression-bomb "
                "guard (~179 megapixels) — far above arXiv's 34-megapixel limit; downsample it"
            )
            continue
        except Exception:
            continue
        pixels = w * h
        if pixels > _MAX_PNG_PIXELS:
            mp = pixels / 1_000_000
            issues.warn(
                f"{path.name} is {mp:.0f} megapixels (>{_MAX_PNG_PIXELS // 1_000_000} MP) — "
                "arXiv flags oversized PNGs; consider downscaling with --resize"
            )


def _check_output_size(output_zip: Path, issues: Issues) -> None:
    """Warn if the output zip exceeds the advisory size threshold."""
    size_mb = output_zip.stat().st_size / (1024 * 1024)
    if size_mb > SIZE_WARN_MB:
        issues.warn(
            f"output is {size_mb:.1f} MB (> {SIZE_WARN_MB} MB) — "
            "consider --resize to shrink images, or split supplementary materials"
        )


def _check_uncompressed_size(kept_files: set[Path], issues: Issues) -> None:
    """Warn if the uncompressed total of kept files exceeds the soft limit.

    Compressed output may slip under the threshold thanks to DEFLATE on text and
    PDFs; the uncompressed total is what arXiv displays in the submission UI.
    """
    total = sum(p.stat().st_size for p in kept_files if p.is_file())
    size_mb = total / (1024 * 1024)
    if size_mb > SIZE_WARN_MB:
        issues.warn(
            f"uncompressed project size is {size_mb:.1f} MB (> {SIZE_WARN_MB} MB) — "
            "arXiv soft limit; consider --resize or splitting supplementary materials"
        )
