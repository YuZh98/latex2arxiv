import re
from pathlib import Path


def _strip_comments(source: str) -> str:
    """Remove LaTeX line comments (% ...) while preserving \\%."""
    return re.sub(r'(?<!\\)%[^\n]*', '', source)


def find_included_tex(source: str, base: Path, root: Path, visited: set) -> set:
    """Recursively find all .tex files reachable via \\input, \\include, \\subfile.
    Comments are stripped first so commented-out includes are not followed.
    """
    found = set()
    for cmd in re.findall(r'\\(?:input|include|subfile)\{([^}]+)\}', _strip_comments(source)):
        p = Path(cmd) if cmd.endswith('.tex') else Path(cmd + '.tex')
        # subfile paths are relative to the including file's directory
        full = (base / p).resolve()
        if full in visited:
            continue
        visited.add(full)
        found.add(full)
        if full.exists():
            child_source = full.read_text(encoding='utf-8', errors='replace')
            found |= find_included_tex(child_source, full.parent, root, visited)
    return found


def find_used_images(tex_sources: list[str], tex_dirs: list[Path], root_dir: Path) -> set:
    """Return set of absolute paths for images referenced by \\includegraphics or \\begin{overpic}.

    LaTeX resolves image paths relative to the compilation root (main file's directory),
    except in \\subfile documents which have their own root. We try both the file's own
    directory and the project root to handle both cases.

    Also respects \\graphicspath{{dir1/}{dir2/}} declarations.
    """
    _IMAGE_RE = re.compile(
        r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}'
        r'|\\begin\{overpic\}(?:\[[^\]]*\])?\{([^}]+)\}'
    )

    # Extract all \graphicspath directories from all sources
    graphic_dirs: list[Path] = []
    for src in tex_sources:
        for m in re.finditer(r'\\graphicspath\{((?:\{[^}]*\})+)\}', _strip_comments(src)):
            for d in re.findall(r'\{([^}]+)\}', m.group(1)):
                for base in [root_dir] + tex_dirs:
                    full = (base / d).resolve()
                    if full.is_dir() and full not in graphic_dirs:
                        graphic_dirs.append(full)

    used_paths = set()
    used_refs = set()
    for src, tex_dir in zip(tex_sources, tex_dirs):
        for m in _IMAGE_RE.finditer(_strip_comments(src)):
            ref = (m.group(1) or m.group(2)).strip()
            used_refs.add(ref)
            candidates = [Path(ref)] + [Path(ref + ext) for ext in ('.pdf', '.png', '.jpg', '.jpeg', '.eps')]
            # Try root dir first, then graphicspath dirs, then tex_dir (for \subfile)
            search_dirs = [root_dir] + graphic_dirs
            if tex_dir != root_dir:
                search_dirs.append(tex_dir)
            for c in candidates:
                for base in search_dirs:
                    full = (base / c).resolve()
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
        for m in re.finditer(r'\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}', src):
            for name in m.group(1).split(','):
                name = name.strip()
                used.add(name + '.sty')
                used.add(name + '.cls')
        for m in re.finditer(r'\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}', src):
            name = m.group(1).strip()
            used.add(name + '.cls')
            used.add(name + '.sty')
    return used


def find_cited_keys(tex_sources: list[str]) -> set:
    """Return set of all citation keys used in \\cite, \\citep, \\citet, etc."""
    keys = set()
    for src in tex_sources:
        src = _strip_comments(src)
        for m in re.finditer(r'\\cite[a-z]*\*?\{([^}]+)\}', src):
            for key in m.group(1).split(','):
                keys.add(key.strip())
    return keys


def find_used_bib_files(tex_sources: list[str]) -> set:
    """Return set of .bib filenames referenced by \\bibliography or \\addbibresource."""
    used = set()
    for src in tex_sources:
        src = _strip_comments(src)
        for m in re.finditer(r'\\bibliography\{([^}]+)\}', src):
            for name in m.group(1).split(','):
                name = name.strip()
                used.add(name if name.endswith('.bib') else name + '.bib')
        for m in re.finditer(r'\\addbibresource\{([^}]+)\}', src):
            name = m.group(1).strip()
            used.add(name if name.endswith('.bib') else name + '.bib')
    return used
