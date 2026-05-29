"""Unit tests for pipeline.resolve.normalize_main_hint.

The rule is shared between every front-end (CLI, MCP, browser, library users)
so the test surface deliberately enumerates each input shape that a real user
might type: bare stem, stem with extension, non-.tex extension, trailing dot,
whitespace, separators, idempotence.
"""

import pytest

from pipeline.resolve import normalize_main_hint
from pipeline.types import ConverterError


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Empty / blank / dot-only → None (no hint).
        (None, None),
        ("", None),
        ("   ", None),
        (".", None),
        ("...", None),
        # Bare stem auto-appends .tex.
        ("main_bj", "main_bj.tex"),
        ("paper", "paper.tex"),
        # Already has the right extension → unchanged.
        ("main.tex", "main.tex"),
        # Non-.tex extension is respected (user knows what they typed).
        ("main.tex.bak", "main.tex.bak"),
        ("backup.zip", "backup.zip"),
        # Whitespace is stripped before the extension check, so the result is
        # the same as the non-whitespace input.
        ("main ", "main.tex"),
        ("  main_bj  ", "main_bj.tex"),
        ("\tmain.tex\n", "main.tex"),
        # Trailing dots are stripped, so 'a.' is treated as 'a' (bare stem).
        ("a.", "a.tex"),
        ("a..", "a.tex"),
        # Names containing dots in the middle keep their extension.
        ("my.paper.tex", "my.paper.tex"),
    ],
)
def test_normalize_main_hint_accepts(value, expected):
    assert normalize_main_hint(value) == expected


@pytest.mark.parametrize("value", ["src/main.tex", "src\\main.tex", "/main.tex", "main/", "a/b"])
def test_normalize_main_hint_rejects_path_separators(value):
    """Path separators are a user error: the hint is a filename, not a path.

    Tested against both POSIX and Windows separators; the pipeline matches
    `p.name`, so any directory component would be unreachable downstream.
    """
    with pytest.raises(ConverterError, match="must be a filename only, not a path"):
        normalize_main_hint(value)


def test_normalize_main_hint_is_idempotent():
    """normalize(normalize(x)) == normalize(x) — required so the helper can
    safely run at every layer that chooses to defend itself."""
    for value in [None, "", "main_bj", "main.tex", "main.tex.bak", "a.", "  paper  "]:
        once = normalize_main_hint(value)
        twice = normalize_main_hint(once)
        assert once == twice, f"non-idempotent for input {value!r}: {once!r} → {twice!r}"
