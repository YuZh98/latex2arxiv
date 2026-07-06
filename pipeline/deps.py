import re
from pathlib import Path


def _strip_comments(source: str) -> str:
    """Remove LaTeX line comments (% ...) while preserving \\%."""
    return re.sub(r"(?<!\\)%[^\n]*", "", source)


def find_included_tex(source: str, base: Path, root: Path, visited: set) -> set:
    """Recursively find all .tex files reachable via \\input, \\include, \\subfile.
    Comments are stripped first so commented-out includes are not followed.
    """
    found = set()
    for cmd in re.findall(r"\\(?:input|include|subfile)\{([^}]+)\}", _strip_comments(source)):
        p = Path(cmd) if cmd.endswith(".tex") else Path(cmd + ".tex")
        # subfile paths are relative to the including file's directory
        full = (base / p).resolve()
        try:
            full.relative_to(root.resolve())
        except ValueError:
            continue
        if full in visited:
            continue
        visited.add(full)
        found.add(full)
        if full.exists():
            child_source = full.read_text(encoding="utf-8", errors="replace")
            found |= find_included_tex(child_source, full.parent, root, visited)
    return found


def find_used_images(tex_sources: list[str], tex_dirs: list[Path], root_dir: Path) -> tuple[set[Path], set[str]]:
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

    # Extract all \graphicspath directories from all sources
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
            ref = (m.group(1) or m.group(2)).strip()
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
                    if full.exists():
                        used_paths.add(full)
                        break
                else:
                    continue
                break
    return used_paths, used_refs


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
ADDBIBRESOURCE_RE = re.compile(r"\\addbibresource(?:\[[^\]]*\])?\{([^}]+)\}")


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
_CITE_SINGLE_RE = re.compile(
    r"\\" + _CITE_PREFIX + r"cite[a-z]*\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}",
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


def find_used_bib_files(tex_sources: list[str]) -> set:
    """Return set of .bib basenames referenced by \\bibliography or \\addbibresource.

    Directory components in the argument (e.g. \\addbibresource{bib/refs.bib}) are
    stripped — converter.py matches against ``path.name`` when scanning for .bib files.
    """
    used = set()
    for src in tex_sources:
        src = _strip_comments(src)
        for m in re.finditer(r"\\bibliography\{([^}]+)\}", src):
            for name in m.group(1).split(","):
                name = Path(name.strip()).name
                used.add(name if name.endswith(".bib") else name + ".bib")
        for m in ADDBIBRESOURCE_RE.finditer(src):
            name = Path(m.group(1).strip()).name
            used.add(name if name.endswith(".bib") else name + ".bib")
    return used
