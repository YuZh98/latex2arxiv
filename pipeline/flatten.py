"""Inline \\input, \\include, and \\subfile references in a LaTeX project.

`flatten_tex(main_tex, root, issues)` returns the flattened source of
`main_tex` plus the set of fragment files that were inlined. The caller
writes the flattened source back to `main_tex` and removes the inlined
fragments from the output zip's whitelist.

Design notes:
- `\\input` and `\\include` paths resolve relative to the project root
  (the main `.tex` file's directory). `\\subfile` paths resolve relative
  to the *including* file's own directory.
- `\\include{x}` carries implicit `\\clearpage` before and after; we emit
  literal `\\clearpage` lines around the inlined body so page-break
  semantics survive the flatten.
- `\\subfile{x}` files have their own `\\documentclass{subfiles}` plus
  `\\begin{document}` / `\\end{document}` wrapper; we keep only the body.
- If `\\input{x}` (or `\\include{x}`) targets a file with its own
  `\\documentclass`, inlining would duplicate the document preamble and
  break the build — emit an error and leave the command in place.
- Cycle detection via a `visited` set: re-entering an already-flattened
  file emits a warning and leaves the command as-is.
- Comments are respected: a `% \\input{x}` line is not inlined, but its
  text is preserved verbatim in the output.
- `\\input{foo.bib}` and other non-`.tex` extensions are left alone.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from converter import Issues


_CMD_RE = re.compile(r'\\(input|include|subfile)\{([^}]+)\}')


def _line_without_comment(line: str) -> str:
    """Return `line` with its trailing LaTeX comment (`%...`) stripped.
    Handles `\\%` escapes."""
    i = 0
    while i < len(line):
        c = line[i]
        if c == "%" and (i == 0 or line[i - 1] != "\\"):
            return line[:i]
        i += 1
    return line


def _strip_subfile_wrapper(raw: str) -> str:
    """Given a subfile source, return only the body between
    `\\begin{document}` and the last `\\end{document}`. If either marker
    is missing, return the original (caller emits a warning)."""
    m_begin = re.search(r'\\begin\{document\}', raw)
    end_idx = raw.rfind(r'\end{document}')
    if m_begin is None or end_idx == -1:
        return raw
    return raw[m_begin.end():end_idx]


def _inline(tex_file: Path, root: Path, in_progress: set[Path],
            inlined: list[Path], issues: "Issues", *, is_subfile: bool) -> str:
    """Recursively inline includes in `tex_file`. `in_progress` is the
    current recursion stack — used purely for cycle detection. A file
    legitimately referenced more than once (e.g., `\\input{macros}` in
    multiple sections) is re-inlined each time; only true cycles
    (file references itself, directly or transitively up the current
    call stack) are reported as cycles and skipped."""
    in_progress.add(tex_file)
    try:
        raw = tex_file.read_text(encoding="utf-8", errors="replace")

        if is_subfile:
            body = _strip_subfile_wrapper(raw)
            if body is raw:
                issues.warn(
                    f"flatten: subfile {tex_file.name} missing "
                    f"\\begin/\\end{{document}}; inlining raw content"
                )
            raw = body

        out_lines: list[str] = []
        for line in raw.splitlines(keepends=True):
            new_line = _process_line(
                line, tex_file, root, in_progress, inlined, issues,
            )
            out_lines.append(new_line)

        return "".join(out_lines)
    finally:
        in_progress.discard(tex_file)


def _process_line(line: str, tex_file: Path, root: Path,
                  in_progress: set[Path], inlined: list[Path],
                  issues: "Issues") -> str:
    """Process every \\input / \\include / \\subfile match on a single
    line (in reverse order so character offsets stay valid). Returns
    the rewritten line."""
    effective = _line_without_comment(line)
    matches = list(_CMD_RE.finditer(effective))
    if not matches:
        return line

    # Walk matches right-to-left so each substitution doesn't shift the
    # offsets of unprocessed matches earlier in the line.
    out = line
    for m in reversed(matches):
        cmd = m.group(1)
        target = m.group(2).strip()

        # Skip non-.tex inputs (e.g., \input{refs.bib}).
        suffix = Path(target).suffix.lower()
        if suffix and suffix != ".tex":
            continue

        if cmd == "subfile":
            base = tex_file.parent
        else:
            base = root
        target_name = target if target.endswith(".tex") else target + ".tex"
        target_path = (base / target_name).resolve()

        if not target_path.exists():
            issues.warn(f"flatten: referenced file not found: {target_name}")
            continue

        if target_path in in_progress:
            issues.warn(
                f"flatten: cycle detected, leaving \\{cmd}{{{target}}} in place"
            )
            continue

        target_raw = target_path.read_text(encoding="utf-8", errors="replace")
        has_docclass = re.search(r'^\s*\\documentclass', target_raw, re.M)
        if has_docclass and cmd != "subfile":
            issues.error(
                f"flatten: \\{cmd}{{{target}}} where {target_name} has its own "
                f"\\documentclass — refusing to flatten; use \\subfile or remove "
                f"the preamble from {target_name}"
            )
            continue

        body = _inline(
            target_path, root, in_progress, inlined, issues,
            is_subfile=(cmd == "subfile"),
        )
        inlined.append(target_path)

        if cmd == "include":
            body = "\n\\clearpage\n" + body + "\n\\clearpage\n"

        out = out[:m.start()] + body + out[m.end():]

    return out


def flatten_tex(main_tex: Path, root: Path,
                issues: "Issues") -> tuple[str, list[Path]]:
    """Inline every \\input / \\include / \\subfile reference reachable
    from `main_tex`. Returns (flattened_source, list_of_inlined_files).

    `issues` collects warnings (missing files, cycles, subfile-without-
    wrapper) and errors (\\input of a file with its own \\documentclass).
    The function never raises on a malformed reference — it warns and
    leaves the command in place so the caller can still produce output.
    """
    in_progress: set[Path] = set()
    inlined: list[Path] = []
    src = _inline(
        main_tex, root, in_progress, inlined, issues, is_subfile=False,
    )
    return src, inlined
