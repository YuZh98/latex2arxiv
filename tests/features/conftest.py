"""Fixtures for BDD scenarios under tests/features/.

Step module registration (pytest_plugins) lives in the top-level conftest.py
because pytest disallows pytest_plugins in non-top-level conftest files.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def project_dir(tmp_path):
    """Per-scenario working directory."""
    return tmp_path


@pytest.fixture
def tex_content():
    """Mutable container holding the current main.tex body for the scenario."""
    return {"body": ("\\documentclass{article}\n\\begin{document}\nHello arXiv.\n\\end{document}\n")}


@pytest.fixture
def result():
    """Mutable container that step functions populate with subprocess output."""
    return {}


_XFAIL_TAGS = {
    "xfail_preflight_gap": (
        "preflight code gap — scenario describes intended arXiv contract not yet "
        "enforced in code (psfig.sty/fontspec-00README/main-subdir/dot-file). "
        "Tracked in https://github.com/YuZh98/latex2arxiv/issues/174 — remove this "
        "xfail once the matching pipeline change lands."
    ),
}


def pytest_bdd_apply_tag(tag, function):
    """Translate Gherkin @<tag> markers into pytest marks for known gap-scenarios.

    strict=True so an accidental partial fix surfaces as XPASS (loud) rather
    than silently passing. Per global CLAUDE.md §7: bridge xfails must surface
    when the underlying gap closes.
    """
    reason = _XFAIL_TAGS.get(tag)
    if reason is None:
        return None
    pytest.mark.xfail(strict=True, reason=reason)(function)
    return True


# pytest_collection_modifyitems was used to xfail the dot-file row of the
# advisory-warnings outline. That gap is closed (#174) by the pre-prune scan
# in pipeline.preflight._check_archive_layout, so the per-row xfail is gone.
