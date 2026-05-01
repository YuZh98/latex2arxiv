import re
import os


# Environments where % is not a comment
_VERBATIM_ENVS = re.compile(
    r'\\begin\{(verbatim|lstlisting|minted|Verbatim)\}.*?\\end\{\1\}',
    re.DOTALL
)


def strip_comments(source: str) -> str:
    """Remove LaTeX comments (% ...) while preserving \\% and verbatim blocks."""
    # Protect verbatim environments by replacing them with placeholders
    placeholders = {}
    def protect(m):
        key = f"\x00VERBATIM{len(placeholders)}\x00"
        placeholders[key] = m.group(0)
        return key
    protected = _VERBATIM_ENVS.sub(protect, source)

    # Strip comments: % not preceded by backslash, to end of line
    stripped = re.sub(r'(?<!\\)%[^\n]*', '', protected)

    # Restore verbatim blocks
    for key, val in placeholders.items():
        stripped = stripped.replace(key, val)

    return stripped


def remove_draft_annotations(source: str) -> str:
    """Remove common draft-only commands: \\todo, \\hl, \\note, \\fixme."""
    # Remove \todo[...]{...} and \todo{...}
    source = re.sub(r'\\todo(?:\[[^\]]*\])?\{[^}]*\}', '', source)
    # Remove \hl{...}, \note{...}, \fixme{...}
    source = re.sub(r'\\(hl|note|fixme)\{[^}]*\}', r'', source)
    return source


def remove_draft_packages(source: str) -> str:
    """Remove usepackage lines for draft-only packages."""
    draft_pkgs = {'todonotes', 'changes', 'trackchanges', 'easy-todo'}
    lines = source.splitlines(keepends=True)
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(r'\usepackage'):
            pkg = re.search(r'\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}', stripped)
            if pkg and pkg.group(1).strip() in draft_pkgs:
                continue
        result.append(line)
    return ''.join(result)


def ensure_pdfoutput(source: str) -> str:
    """Ensure \\pdfoutput=1 appears before \\documentclass."""
    if r'\pdfoutput=1' in source:
        return source
    return r'\pdfoutput=1' + '\n' + source
