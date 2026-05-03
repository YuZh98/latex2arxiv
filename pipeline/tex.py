import re


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


def find_balanced(s: str, start: int) -> int:
    """Return the index after the closing brace matching the '{' at s[start].
    Returns -1 if not found.
    """
    depth = 0
    i = start
    while i < len(s):
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def remove_cmd(source: str, pattern: re.Pattern) -> str:
    """Remove all occurrences of a command with a brace-balanced argument.

    For each regex match, deletes the match plus the immediately-following
    {...} group (handling nested braces). If no '{' follows the match, the
    match itself is left untouched.
    """
    result = []
    pos = 0
    for m in pattern.finditer(source):
        result.append(source[pos:m.start()])
        brace_start = source.find('{', m.end())
        if brace_start == -1 or brace_start > m.end() + 1:
            result.append(m.group(0))
            pos = m.end()
            continue
        end = find_balanced(source, brace_start)
        pos = end if end != -1 else m.end()
    result.append(source[pos:])
    return ''.join(result)


def unwrap_cmd(source: str, pattern: re.Pattern) -> str:
    """Replace `\\cmd{inner}` with `inner`, using a brace-balanced matcher.

    For each regex match, looks for an immediately-following '{'. If found,
    substitutes the match plus its balanced group with the group's contents.
    If no '{' follows (a switch like `\\color{red}` written literally as the
    pattern), the match is removed entirely.
    """
    result = []
    pos = 0
    for m in pattern.finditer(source):
        result.append(source[pos:m.start()])
        brace_start = source.find('{', m.end())
        if brace_start == -1 or brace_start > m.end() + 1:
            # No following arg group: treat as switch, remove the match.
            pos = m.end()
            continue
        end = find_balanced(source, brace_start)
        if end == -1:
            result.append(m.group(0))
            pos = m.end()
            continue
        result.append(source[brace_start + 1:end - 1])
        pos = end
    result.append(source[pos:])
    return ''.join(result)


def remove_draft_annotations(source: str) -> str:
    """Remove common draft-only commands: \\todo, \\hl, \\note, \\fixme.
    Uses a brace-balanced matcher to handle nested braces correctly.
    """
    source = remove_cmd(source, re.compile(r'\\todo(?:\[[^\]]*\])?(?=\{)'))
    for cmd in ('hl', 'note', 'fixme'):
        source = remove_cmd(source, re.compile(r'\\' + cmd + r'(?=\{)'))
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
