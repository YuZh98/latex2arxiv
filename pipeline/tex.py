import re


# Environments where % is not a comment
_VERBATIM_ENVS = re.compile(
    r'\\begin\{(verbatim|lstlisting|minted|Verbatim)\}.*?\\end\{\1\}',
    re.DOTALL
)

# Inline \verb|...|, \verb*|...|, \lstinline|...|, \mintinline{lang}|...| (any delimiter)
_VERB_INLINE = re.compile(
    r'\\(?:verb\*?|lstinline\*?(?:\[[^\]]*\])?|mintinline\*?(?:\[[^\]]*\])?\{[^}]*\})'
    r'([^a-zA-Z\s]).*?\1'
)


def _protect_verbatim(source: str):
    """Replace verbatim environments and \\verb|...| with placeholders.
    Returns (protected_source, placeholders_dict).
    """
    placeholders = {}

    def protect(m):
        key = f"\x00VERBATIM{len(placeholders)}\x00"
        placeholders[key] = m.group(0)
        return key

    source = _VERBATIM_ENVS.sub(protect, source)
    source = _VERB_INLINE.sub(protect, source)
    return source, placeholders


def _restore_verbatim(source: str, placeholders: dict) -> str:
    """Restore placeholders back to original content."""
    for key, val in placeholders.items():
        source = source.replace(key, val)
    return source


def strip_comments(source: str) -> str:
    """Remove LaTeX comments (% ...) while preserving \\% and verbatim blocks."""
    protected, placeholders = _protect_verbatim(source)

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
    return _restore_verbatim(stripped, placeholders)


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


# Best-effort skip-list for command-rule transformations: when our pattern
# matches inside one of these definition contexts, we leave the match alone
# instead of mangling the definition. Covers the common forms; xparse-style
# \NewDocumentCommand is intentionally not listed (rare; users should use
# package-defined commands when possible).
_DEF_PREFIX_RE = re.compile(
    r'(?:'
    r'\\(?:new|renew|provide)command\*?\s*\{'    # \newcommand{\foo}, \renewcommand{\foo}, \providecommand{\foo}
    r'|\\DeclareRobustCommand\*?\s*'             # \DeclareRobustCommand\foo or \DeclareRobustCommand{\foo}
    r'|(?:\\protected\s*)?\\(?:e|x|g)?def\s*'    # \def\foo, \edef\foo, \xdef\foo, \gdef\foo, \protected\def\foo
    r'|\\let\s*'                                 # \let\foo\bar
    r')$'
)


def _in_definition_context(source: str, match_start: int) -> bool:
    """True if the match is preceded by a recognised TeX definition prefix.

    The window of 40 chars is a heuristic — long enough to span any common
    prefix (\\protected\\def is 14 chars), short enough that unrelated
    earlier text rarely produces false positives. Comments are stripped
    before this runs, so commented-out '\\newcommand' lines do not bite.
    """
    look = source[max(0, match_start - 40):match_start]
    return _DEF_PREFIX_RE.search(look) is not None


def remove_cmd(source: str, pattern: re.Pattern) -> str:
    """Remove all occurrences of a command with a brace-balanced argument.

    For each regex match, deletes the match plus the immediately-following
    {...} group (handling nested braces). If no '{' follows the match, the
    match itself is left untouched. Matches that sit inside a definition
    context (\\newcommand{\\foo}, \\def\\foo, etc.) are left alone so the
    definition is not mangled.
    """
    result = []
    pos = 0
    for m in pattern.finditer(source):
        result.append(source[pos:m.start()])
        if _in_definition_context(source, m.start()):
            result.append(m.group(0))
            pos = m.end()
            continue
        brace_start = source.find('{', m.end())
        if brace_start == -1 or brace_start > m.end() + 1:
            result.append(m.group(0))
            pos = m.end()
            continue
        end = find_balanced(source, brace_start)
        pos = end if end != -1 else m.end()
    result.append(source[pos:])
    return ''.join(result)


def remove_bare_cmd(source: str, pattern: re.Pattern) -> str:
    """Strip bare occurrences of a command (no brace-balanced arg expected).

    Used by ``apply_config`` as a follow-up after ``remove_cmd`` to clear any
    \\cmd text that wasn't followed by a {...}. Like ``remove_cmd``, leaves
    matches inside a definition context untouched.
    """
    def _replace(m):
        if _in_definition_context(source, m.start()):
            return m.group(0)
        return ''
    return pattern.sub(_replace, source)


def unwrap_cmd(source: str, pattern: re.Pattern) -> str:
    """Replace `\\cmd{inner}` with `inner`, using a brace-balanced matcher.

    For each regex match, looks for an immediately-following '{'. If found,
    substitutes the match plus its balanced group with the group's contents.
    If no '{' follows (a switch like `\\color{red}` written literally as the
    pattern), the match is removed entirely. Matches inside a definition
    context (\\newcommand{\\foo}, \\def\\foo, etc.) are left alone.
    """
    result = []
    pos = 0
    for m in pattern.finditer(source):
        result.append(source[pos:m.start()])
        if _in_definition_context(source, m.start()):
            result.append(m.group(0))
            pos = m.end()
            continue
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
    Protects \\verb|...| content from being mangled.
    """
    source, placeholders = _protect_verbatim(source)
    source = remove_cmd(source, re.compile(r'\\todo(?:\[[^\]]*\])?(?=\{)'))
    for cmd in ('hl', 'note', 'fixme'):
        source = remove_cmd(source, re.compile(r'\\' + cmd + r'(?=\{)'))
    return _restore_verbatim(source, placeholders)


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
    """Ensure \\pdfoutput=1 is the only \\pdfoutput declaration.

    arXiv requires PDF output. A user-set \\pdfoutput=0 (or any non-1 value)
    forces DVI mode and contradicts the PDFLaTeX submission path, so we
    strip any existing \\pdfoutput=N and prepend \\pdfoutput=1.
    """
    stripped = re.sub(r'\\pdfoutput\s*=\s*\d+\s*\n?', '', source)
    return r'\pdfoutput=1' + '\n' + stripped
