import os
import re
from pathlib import Path


def _strip_comments(source: str) -> str:
    """Remove LaTeX line comments (% ...) while preserving \\%."""
    return re.sub(r"(?<!\\)%[^\n]*", "", source)


def _is_static_ref(ref: str) -> bool:
    return not any(ch in ref for ch in "\\#|")


def find_included_tex(
    source: str,
    base: Path,
    root: Path,
    visited: set,
    compile_base: Path | None = None,
    missing: list[str] | None = None,
) -> set:
    """Recursively find all files reachable via \\input, \\include, \\subfile.
    Comments are stripped first so commented-out includes are not followed.

    Targets resolve against the archive root (where arXiv compiles), then
    `compile_base` (defaulting to the top-level `base`), then the including
    file's own directory. Unresolvable static targets are appended to `missing`.
    Non-.tex targets (e.g. \\input{fig.pgf}) are collected but not recursed into.
    """
    if compile_base is None:
        compile_base = base
    found = set()
    root_resolved = root.resolve()
    for cmd in re.findall(r"\\(?:input|include|subfile)\{([^}]+)\}", _strip_comments(source)):
        names = [cmd] if cmd.endswith(".tex") else [cmd + ".tex", cmd]
        candidates: list[Path] = []
        for name in names:
            for b in dict.fromkeys((root, compile_base, base)):
                full = (b / name).resolve()
                try:
                    full.relative_to(root_resolved)
                except ValueError:
                    continue
                if full not in candidates:
                    candidates.append(full)
        if not candidates:
            continue
        full = next((c for c in candidates if c.is_file()), candidates[0])
        if not full.is_file() and missing is not None and _is_static_ref(cmd) and cmd not in missing:
            missing.append(cmd)
        if full in visited:
            continue
        visited.add(full)
        found.add(full)
        if full.is_file() and full.suffix in ("", ".tex"):
            child_source = full.read_text(encoding="utf-8", errors="replace")
            found |= find_included_tex(child_source, full.parent, root, visited, compile_base, missing)
    return found


def find_used_images(
    tex_sources: list[str], tex_dirs: list[Path], root_dir: Path, missing: set[str] | None = None
) -> tuple[set[Path], set[str]]:
    """Return set of absolute paths for images referenced by \\includegraphics or \\begin{overpic}.

    LaTeX resolves image paths relative to the compilation root (main file's directory),
    except in \\subfile documents which have their own root. We try both the file's own
    directory and the project root to handle both cases.

    Also respects \\graphicspath{{dir1/}{dir2/}} declarations.
    """
    _IMAGE_RE = re.compile(
        r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}"
        r"|\\begin\{overpic\}(?:\[[^\]]*\])?\{([^}]+)\}"
    )

    graphic_dirs: list[Path] = []
    for src in tex_sources:
        for m in re.finditer(r"\\graphicspath\{((?:\{[^}]*\})+)\}", _strip_comments(src)):
            for d in re.findall(r"\{([^}]+)\}", m.group(1)):
                for base in [root_dir] + tex_dirs:
                    full = (base / d).resolve()
                    try:
                        full.relative_to(root_dir.resolve())
                    except ValueError:
                        continue
                    if full.is_dir() and full not in graphic_dirs:
                        graphic_dirs.append(full)

    used_paths = set()
    used_refs = set()
    for src, tex_dir in zip(tex_sources, tex_dirs):
        for m in _IMAGE_RE.finditer(_strip_comments(src)):
            ref = (m.group(1) or m.group(2)).strip().strip('"')
            used_refs.add(ref)
            candidates = [Path(ref)] + [Path(ref + ext) for ext in (".pdf", ".png", ".jpg", ".jpeg", ".eps")]
            # Try root dir first, then graphicspath dirs, then tex_dir (for \subfile)
            search_dirs = [root_dir] + graphic_dirs
            if tex_dir != root_dir:
                search_dirs.append(tex_dir)
            for c in candidates:
                for base in search_dirs:
                    full = (base / c).resolve()
                    try:
                        full.relative_to(root_dir.resolve())
                    except ValueError:
                        continue
                    if _exists_exact_case(full, root_dir):
                        used_paths.add(full)
                        break
                else:
                    continue
                break
            else:
                case_match = _find_case_variant(ref, search_dirs, root_dir)
                if case_match is not None:
                    used_paths.add(case_match)
                elif missing is not None and _is_static_ref(ref):
                    missing.add(ref)
    return used_paths, used_refs


_GRAPHICS_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".eps")
_GRAPHICS_EXTS_UPPER = (".PDF", ".PNG", ".JPG", ".JPEG")


def _find_case_variant(ref: str, search_dirs: list[Path], root_dir: Path) -> Path | None:
    """Find `ref` with an all-uppercase extension (fig.PNG), which graphicx also tries."""
    ref_path = Path(ref)
    for base in search_dirs:
        parent = (base / ref_path).parent
        if not parent.is_dir():
            continue
        for f in parent.iterdir():
            if not f.is_file():
                continue
            if f.stem == ref_path.name and f.suffix in _GRAPHICS_EXTS + _GRAPHICS_EXTS_UPPER:
                full = f.resolve()
                try:
                    full.relative_to(root_dir.resolve())
                except ValueError:
                    continue
                return full
    return None


def _exists_exact_case(path: Path, root: Path) -> bool:
    """`path.exists()` that also matches letter case of every component below `root`, as on arXiv."""
    if not path.exists():
        return False
    current = root.resolve()
    try:
        parts = path.relative_to(current).parts
    except ValueError:
        return True
    for part in parts:
        try:
            if part not in os.listdir(current):
                return False
        except OSError:
            return True
        current = current / part
    return True


def find_used_style_files(tex_sources: list[str]) -> set:
    """Return set of .sty/.cls basenames referenced by \\usepackage or \\documentclass.
    Both extensions are tried since some packages (e.g. imsart) use .sty as a document class.
    """
    used = set()
    for src in tex_sources:
        src = _strip_comments(src)
        for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", src):
            for name in m.group(1).split(","):
                name = name.strip()
                used.add(name + ".sty")
                used.add(name + ".cls")
        for m in re.finditer(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", src):
            name = m.group(1).strip()
            used.add(name + ".cls")
            used.add(name + ".sty")
    return used


BIBLATEX_PACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\bbiblatex\b[^}]*\}")
ADDBIBRESOURCE_RE = re.compile(r"\\addbibresource(?:\[([^\]]*)\])?\{([^}]+)\}")


def uses_biblatex(tex_sources: list[str]) -> bool:
    """True if any source loads the biblatex package or declares a bib resource."""
    return any(
        BIBLATEX_PACKAGE_RE.search(src) or ADDBIBRESOURCE_RE.search(src)
        for src in (_strip_comments(s) for s in tex_sources)
    )


_CITE_PREFIX = r"(?:no|auto|paren|text|smart|super|full|foot(?:full)?)?"
# Singular cite commands take exactly one key group; commands like \citefield
# and \citename carry a second mandatory arg that is NOT a key, so only the
# first brace group is captured. Bracket args are skipped, never scanned.
# \citestyle takes a natbib style name, not a key, so it is excluded.
_CITE_SINGLE_RE = re.compile(
    r"\\" + _CITE_PREFIX + r"cite(?!style)[a-z]*\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}",
    re.IGNORECASE,
)
# Multicite family (\cites, \autocites, ...) chains {key} groups, each with
# optional pre/post notes; global affixes come in parentheses.
_CITE_MULTI_RE = re.compile(
    r"\\" + _CITE_PREFIX + r"cites\*?"
    r"(?:\([^)]*\)){0,2}"
    r"(?P<args>(?:\s*(?:\[[^\]]*\]\s*){0,2}\{[^}]*\})+)",
    re.IGNORECASE,
)
_CITE_MULTI_GROUP_RE = re.compile(r"\{([^}]*)\}")
_CITE_BRACKET_RE = re.compile(r"\[[^\]]*\]")


def _add_keys(raw: str, keys: set) -> None:
    for key in raw.split(","):
        key = key.strip()
        # '*' is \nocite{*}; backslash/space/brace means a matcher swallowed
        # an adjacent brace group, not a citation key — drop it.
        if key and key != "*" and not re.search(r"[\\\s{]", key):
            keys.add(key)


def find_cited_keys(tex_sources: list[str]) -> set:
    """Return set of citation keys from natbib and biblatex cite commands.

    Covers \\cite/\\citep/\\citet..., biblatex \\autocite/\\parencite/\\textcite/
    \\footcite/\\smartcite/\\supercite/\\fullcite/\\nocite (any capitalization,
    starred, pre/post notes, multicite forms). '*' from \\nocite{*} is dropped.
    Not handled: the \\volcite family, whose FIRST mandatory arg is a volume,
    not a key — supporting it would need per-command argument dispatch.
    """
    keys: set = set()
    for src in tex_sources:
        src = _strip_comments(src)
        for m in _CITE_SINGLE_RE.finditer(src):
            _add_keys(m.group(1), keys)
        for m in _CITE_MULTI_RE.finditer(src):
            args = _CITE_BRACKET_RE.sub("", m.group("args"))
            for group in _CITE_MULTI_GROUP_RE.finditer(args):
                _add_keys(group.group(1), keys)
    return keys


def find_bib_resources(tex_sources: list[str], main_stem: str | None = None) -> list[tuple[str, str]]:
    """Return (options, argument) for each \\addbibresource, with \\jobname resolved."""
    resources = []
    for src in tex_sources:
        for m in ADDBIBRESOURCE_RE.finditer(_strip_comments(src)):
            arg = m.group(2).strip()
            if main_stem:
                arg = arg.replace("\\jobname", main_stem)
            resources.append((m.group(1) or "", arg))
    return resources


def find_used_bib_files(tex_sources: list[str], main_stem: str | None = None) -> set:
    """Return set of data file basenames referenced by \\bibliography or \\addbibresource.

    \\bibliography appends .bib like BibTeX; \\addbibresource names are taken
    literally, as Biber does. Directory components are stripped — converter.py
    matches against ``path.name`` when scanning for data files.
    """
    used = set()
    for src in tex_sources:
        src = _strip_comments(src)
        for m in re.finditer(r"\\bibliography\{([^}]+)\}", src):
            for name in m.group(1).split(","):
                name = name.strip()
                if main_stem:
                    name = name.replace("\\jobname", main_stem)
                name = Path(name).name
                used.add(name if name.endswith(".bib") else name + ".bib")
    for _, arg in find_bib_resources(tex_sources, main_stem):
        if "://" not in arg:
            used.add(Path(arg).name)
    return used


def _top_dir(rel: str) -> str | None:
    head, sep, _ = rel.partition("/")
    return head if sep else None


_BUILD_JUNK_SUFFIXES = (".aux", ".log", ".synctex.gz", ".synctex", ".fls", ".fdb_latexmk", ".bak", "~")


def _is_shippable(rel: str) -> bool:
    return not any(part.startswith(".") for part in rel.split("/")) and not rel.endswith(_BUILD_JUNK_SUFFIXES)


def is_ancillary(rel: str) -> bool:
    """True for shippable files under the root `anc/` directory, which arXiv publishes as ancillary files."""
    return _top_dir(rel) == "anc" and _is_shippable(rel)


def is_minted_cache(rel: str) -> bool:
    """True for shippable files under a root `_minted` / `_minted-<jobname>` cache directory."""
    top = _top_dir(rel)
    return top is not None and (top == "_minted" or top.startswith("_minted-")) and _is_shippable(rel)
