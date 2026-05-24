"""BDD entrypoint: bind mcp_server.feature scenarios to pytest-bdd."""

from pytest_bdd import scenarios

scenarios("mcp_server.feature")
