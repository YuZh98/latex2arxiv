"""Pre-flight checks run by convert() before emitting the output zip.

Each check emits issues via the Issues collector; none raise. Imported by
converter.py and called inline from convert() at their original call sites
(call-site order is part of the public behavior contract — do not consolidate)."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pipeline.deps import find_bib_resources, is_ancillary, uses_biblatex
from pipeline.tex import _VERBATIM_ENVS
from pipeline.types import Issues

# Packages that require shell-escape, which arXiv compiles without.
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
_FILECONTENTS_RE = re.compile(r"\\begin\{filecontents\*?\}(?:\[[^\]]*\])?\{([^}]+)\}")
_BIBER_DATATYPES = {"bibtex", "biblatexml"}
_NON_BIBTEX_SUFFIXES = {".ris", ".rdf", ".xml", ".bltxml", ".json", ".yaml", ".yml"}


_README_NAMES = ("00README", "00README.XXX", "00README.json")
_PDFOUTPUT_SET_RE = re.compile(r"\\pdfoutput\s*=\s*(\d)")
_IFNUM_TAIL_RE = re.compile(r"\\ifnum\s*$")


def _has_latex_dvips_mode(root: Path) -> bool:
    """Return True if a 00README file at root specifies latex (dvips) or tex compiler."""
    for name in _README_NAMES:
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
    """Return True if a 00README at root opts into XeLaTeX.

    Mirrors :func:`_has_latex_dvips_mode`.
    """
    for name in _README_NAMES:
        readme = root / name
        if not readme.exists():
            continue
        try:
            content = readme.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if re.search(r'"?compiler"?\s*[:=]\s*"?xelatex', content):
            return True
        if name == "00README.XXX" and "xelatex" in content:
            return True
    return False


def _readme_requests_lualatex(root: Path) -> bool:
    for name in ("00README", "00README.json"):
        readme = root / name
        try:
            content = readme.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if re.search(r'"?compiler"?\s*[:=]\s*"?lualatex\b', content):
            return True
    return False


def _has_minted_cache(root: Path) -> bool:
    """True if root `_minted/` holds minted v3 cache files (`*.minted`), the format TeX Live 2025 reads."""
    cache = root / "_minted"
    return cache.is_dir() and any(cache.glob("*.minted"))


_LIVE_REF_RE = re.compile(r"\\(?:input|include|subfile|includegraphics)(?:\[[^\]]*\])?\{([^}]+)\}")


def _norm_ref(ref: str) -> str:
    return ref.strip().strip('"')


_BUILD_OUTPUT_EXTS = {".aux", ".toc", ".lof", ".lot", ".bbl", ".ind", ".gls", ".nls", ".out"}
_TEXLIVE_INPUTS = {"glyphtounicode", "epsf"}


def _kpsewhich(*args: str, cwd: str) -> str:
    kpsewhich = shutil.which("kpsewhich")
    if kpsewhich is None:
        return ""
    try:
        out = subprocess.run([kpsewhich, *args], capture_output=True, text=True, timeout=10, cwd=cwd)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def _provided_by_texlive(ref: str) -> bool:
    """True if `ref` ships with TeX Live itself; the user's own texmf trees and cwd don't count."""
    if ref in _TEXLIVE_INPUTS or ref.startswith("example-image"):
        return True
    with tempfile.TemporaryDirectory() as empty:
        dist = _kpsewhich("-var-value", "TEXMFDIST", cwd=empty)
        if not dist:
            return False
        dist_root = Path(dist).resolve()
        for hit in _kpsewhich(ref, ref + ".tex", cwd=empty).splitlines():
            if Path(hit).resolve().is_relative_to(dist_root):
                return True
    return False


def _report_missing_targets(
    missing_inputs: list[str], missing_images: set[str], all_sources: list[str], issues: Issues
) -> None:
    """Warn for \\input / \\includegraphics targets absent from the project, skipping generated and TeX Live files."""
    if not missing_inputs and not missing_images:
        return
    combined = _VERBATIM_ENVS.sub("", re.sub(r"(?<!\\)%[^\n]*", "", "\n".join(all_sources)))
    generated = set(_FILECONTENTS_RE.findall(combined))
    externalized = "\\tikzexternalize" in combined
    live_refs = {_norm_ref(m.group(1)) for m in _LIVE_REF_RE.finditer(combined)}

    def skip(ref: str) -> bool:
        ref = _norm_ref(ref)
        return (
            Path(ref).suffix.lower() in _BUILD_OUTPUT_EXTS
            or ref in generated
            or ref + ".tex" in generated
            or ref not in live_refs
            or _provided_by_texlive(ref)
        )

    for ref in missing_inputs:
        if not skip(ref):
            issues.warn(
                f"\\input/\\include/\\subfile target not found: {_norm_ref(ref)} — unless TeX Live provides it, "
                "arXiv's build stops with 'File not found'"
            )
    for ref in sorted(missing_images):
        if externalized or skip(ref):
            continue
        issues.warn(
            f"\\includegraphics target not found: {_norm_ref(ref)} — unless TeX Live provides it, "
            "arXiv's build stops with 'File not found'"
        )


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

    # Shell-escape packages; minted alone can build from a shipped v3 cache.
    # Iterate the comma-separated \usepackage argument so 'pst-pdf' isn't matched
    # as a substring of 'auto-pst-pdf'.
    flagged_shell: set[str] = set()
    for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", combined_nc):
        for raw in m.group(1).split(","):
            name = raw.strip()
            if name in _SHELL_ESCAPE_PKGS and name not in flagged_shell:
                flagged_shell.add(name)
                if name == "minted" and _has_minted_cache(root):
                    issues.warn(
                        "\\usepackage{minted} with a shipped _minted cache — arXiv compiles "
                        "without shell-escape, so every listing must already be in the cache; "
                        "build it with TeX Live 2025 (minted v3) and select TeX Live 2025 on arXiv"
                    )
                    continue
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

    # The submission form may still default to pdfLaTeX; only a 00README opt-in is verifiable here.
    xelatex_opted_in = _has_xelatex_mode(root)
    for pkg in ("fontspec", "unicode-math"):
        if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b" + pkg + r"\b[^}]*\}", combined_nc):
            if xelatex_opted_in:
                continue
            issues.error(
                f"\\usepackage{{{pkg}}} requires XeLaTeX — pdfLaTeX will fail; add a 00README.json "
                'containing {"process": {"compiler": "xelatex"}} or select xelatex when submitting '
                "(arXiv does not support LuaLaTeX)"
            )

    if _readme_requests_lualatex(root):
        issues.error(
            "00README requests lualatex — arXiv supports only tex, pdftex, latex, pdflatex and "
            "xelatex, and fails any other compiler; switch to xelatex"
        )
    for yaml_name in ("00README.yaml", "00README.yml"):
        if (root / yaml_name).is_file():
            issues.warn(
                f"{yaml_name} is not a format arXiv documents and is not read as a processor choice — "
                'use 00README.json (e.g. {"process": {"compiler": "xelatex"}}) or the legacy 00README.XXX'
            )
    pdfoutput_values = {
        m.group(1)
        for m in _PDFOUTPUT_SET_RE.finditer(combined_nc)
        if not _IFNUM_TAIL_RE.search(combined_nc[max(0, m.start() - 40) : m.start()])
    }
    latex_mode = _has_latex_dvips_mode(root)
    if pdfoutput_values and (xelatex_opted_in or latex_mode):
        issues.warn(
            "\\pdfoutput is set but 00README selects xelatex or latex — xelatex has no \\pdfoutput "
            "and latex+dvips needs DVI output; remove the \\pdfoutput line"
        )
    elif "0" in pdfoutput_values:
        issues.warn(
            "\\pdfoutput=0 makes pdflatex write DVI instead of PDF — remove it, or select latex "
            'with a 00README.json ({"process": {"compiler": "latex"}}) if you need dvips'
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
            f"main tex '{rel}' is not at the submission root — arXiv compiles from the root, "
            "so \\input, \\includegraphics and bibliography paths resolve from there, "
            f"not from {rel.parent.as_posix()}/"
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

    # A shipped .bbl must match arXiv's bbl format or the build hard-errors
    # ("bbl version mismatch"). Without one, arXiv runs Biber on the .bib.
    is_biblatex = uses_biblatex([combined_nc])
    bbl = root / f"{main_stem}.bbl"
    if is_biblatex:
        if bbl.exists():
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

    # arXiv blocks a submission when a needed .bib and the .bbl are both absent.
    # Its docs don't cover a .bib written by filecontents during the build, so
    # that case stays a warning.
    if kept_files is not None and not bbl.exists():
        kept_names = {p.name for p in kept_files}
        generated = {Path(name.strip()).name for name in _FILECONTENTS_RE.findall(combined_nc)}
        missing = sorted(
            b for b in used_bib_files or () if b not in kept_names and b not in generated and "\\" not in b
        )
        for name in sorted(set(used_bib_files or ()) & generated - kept_names):
            issues.warn(
                f"{name} is generated by filecontents and no {main_stem}.bbl is shipped — "
                "arXiv may block a submission without the .bib; ship it as a separate file"
            )
        for opts, arg in dict.fromkeys(find_bib_resources(all_sources, main_stem)):
            name = Path(arg).name
            datatype = re.search(r"datatype\s*=\s*\{?\s*(\w+)", opts)
            datatype = datatype.group(1).lower() if datatype else "bibtex"
            if "://" in arg:
                issues.warn(
                    f"\\addbibresource downloads {arg} during the build and no {main_stem}.bbl is shipped — "
                    "arXiv's build may have no network access; ship the file or the .bbl"
                )
            elif name in kept_names and (
                datatype not in _BIBER_DATATYPES
                or (datatype == "bibtex" and Path(name).suffix.lower() in _NON_BIBTEX_SUFFIXES)
            ):
                issues.error(
                    f"{name} is not BibTeX data and no {main_stem}.bbl is shipped — "
                    "Biber reads only BibTeX and biblatexml, so its entries will be missing; "
                    "convert it to .bib or ship the .bbl"
                )
            elif name in missing and name + ".bib" in kept_names:
                missing.remove(name)
                issues.error(
                    f"\\addbibresource{{{arg}}} needs the full file name — Biber does not add .bib; "
                    f"use \\addbibresource{{{arg}.bib}}"
                )
        if missing:
            command = "\\addbibresource" if is_biblatex else "\\bibliography"
            issues.error(
                f"{command} references {', '.join(missing)} but "
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

        if path.suffix.lower() == ".tex" and is_ancillary(rel.as_posix()):
            issues.warn(f"{rel.as_posix()} is a .tex file in anc/ — arXiv says TeX files do not belong in anc/")

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
