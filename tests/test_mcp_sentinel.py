"""Sentinel test: fail loudly if mcp package is not installed.

Kept separate from test_mcp_server.py to avoid being silently skipped
by that module's pytest.importorskip("mcp") guard.
"""
import pytest


def test_mcp_package_is_installed():
    """Fail loudly if mcp is not installed — prevents silent CI skips."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        pytest.fail(
            "mcp package not installed; all MCP tests are silently skipping. "
            "Install with: pip install mcp fastmcp"
        )
