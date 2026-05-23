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
