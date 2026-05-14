"""Sentinel test: fail loudly if mcp package is not installed.

Kept separate from test_mcp_server.py to avoid being silently skipped
by that module's pytest.importorskip("mcp") guard.
"""
import pytest


def test_mcp_package_is_installed():
    """In CI, fail loudly if mcp is not installed (prevents silent skips).
    Skips locally where mcp may intentionally be absent from the test env.
    """
    import os
    if not os.environ.get("CI"):
        pytest.skip("skipping mcp sentinel outside CI")
    try:
        import mcp  # noqa: F401
    except ImportError:
        pytest.fail(
            "mcp package not installed in CI; all MCP tests are silently skipping. "
            "Add 'mcp fastmcp' to the pip install line in test.yml."
        )
