"""Top-level pytest configuration.

Registers BDD step modules under tests/features/steps/ as pytest plugins so
their @given/@when/@then decorators are available to scenarios under
tests/features/. Fixtures used by step functions live in
tests/features/conftest.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_STEPS = Path(__file__).parent / "tests" / "features" / "steps"
sys.path.insert(0, str(_STEPS))

pytest_plugins = ["common", "cli", "mcp_steps"]
