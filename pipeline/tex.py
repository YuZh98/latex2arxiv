import re
import os


# Environments where % is not a comment
_VERBATIM_ENVS = re.compile(
    r'\\begin\{(verbatim|lstlisting|minted|Verbatim)\}.*?\\end\{\1\}',
    re.DOTALL
)


def strip_comments(source: str) -> str:
    """Remove LaTeX comments (% ...) while preserving \\% and verbatim blocks."""
    placeholders = {}
    def protect(m):
        key = f"\x00VERBATIM{len(placeholders)}\x00"
        placeholders[key] = m.group(0)
        return key
    protected = _VERBATIM_ENVS.sub(protect, source)

    result_lines = []
    for line in protected.splitlines(keepends=True):
        # Find first unescaped %
        stripped = re.sub(r'(?<!\\)%.*', '', line)
        # If the line was entirely a comment (only whitespace remains), drop it
        # to avoid introducing spurious paragraph breaks
        if stripped.strip() == '' and '%' in line and not line.strip().startswith('\x00'):
            continue
        result_lines.append(stripped)

    stripped = ''.join(result_lines)

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
    draft_pkgs = {'todonotes', 'changes', 'trackchanges', 'easy-todo', 'comment'}
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


def remove_comment_environments(source: str) -> str:
    """Remove \\begin{comment}...\\end{comment} blocks and \\iffalse...\\fi blocks."""
    source = re.sub(r'\\begin\{comment\}.*?\\end\{comment\}', '', source, flags=re.DOTALL)
    source = re.sub(r'\\iffalse\b.*?\\fi\b', '', source, flags=re.DOTALL)
    return source


def ensure_pdfoutput(source: str) -> str:
    """Ensure \\pdfoutput=1 appears before \\documentclass."""
    if r'\pdfoutput=1' in source:
        return source
    return r'\pdfoutput=1' + '\n' + source
