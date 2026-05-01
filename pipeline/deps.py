import re
from pathlib import Path


def find_included_tex(source: str, base: Path, visited: set) -> set:
    """Recursively find all .tex files reachable via \\input / \\include."""
    found = set()
    for cmd in re.findall(r'\\(?:input|include)\{([^}]+)\}', source):
        p = Path(cmd) if cmd.endswith('.tex') else Path(cmd + '.tex')
        full = base / p
        if full in visited:
            continue
        visited.add(full)
        found.add(full)
        if full.exists():
            child_source = full.read_text(encoding='utf-8', errors='replace')
            found |= find_included_tex(child_source, full.parent, visited)
    return found


def find_used_images(tex_sources: list[str]) -> set:
    """Return set of image basenames referenced by \\includegraphics."""
    used = set()
    for src in tex_sources:
        for m in re.finditer(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', src):
            used.add(m.group(1))  # may or may not have extension
    return used


def find_used_bib_files(tex_sources: list[str]) -> set:
    """Return set of .bib filenames referenced by \\bibliography or \\addbibresource."""
    used = set()
    for src in tex_sources:
        for m in re.finditer(r'\\bibliography\{([^}]+)\}', src):
            for name in m.group(1).split(','):
                name = name.strip()
                used.add(name if name.endswith('.bib') else name + '.bib')
        for m in re.finditer(r'\\addbibresource\{([^}]+)\}', src):
            name = m.group(1).strip()
            used.add(name if name.endswith('.bib') else name + '.bib')
    return used
