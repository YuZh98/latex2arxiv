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
    "xfail_preflight_gap": "scenario describes intended behavior not yet implemented in preflight (psfig.sty/fontspec-00README/main-subdir/dot-file gaps); leave as canonical contract until backlog PR lands",
}


def pytest_bdd_apply_tag(tag, function):
    """Translate Gherkin @<tag> markers into pytest marks for known gap-scenarios."""
    reason = _XFAIL_TAGS.get(tag)
    if reason is None:
        return None
    pytest.mark.xfail(strict=False, reason=reason)(function)
    return True


def pytest_collection_modifyitems(config, items):
    """Mark the dot-file row of the advisory-warnings outline as xfail.

    Per-row tagging is not expressible in Gherkin; we identify the row by node-id
    substring instead. Same backlog gap as the @xfail_preflight_gap scenarios.
    """
    for item in items:
        if "test_additional_advisory_warnings" in item.nodeid and "dot-file" in item.nodeid:
            item.add_marker(
                pytest.mark.xfail(
                    strict=False,
                    reason=_XFAIL_TAGS["xfail_preflight_gap"],
                )
            )
