"""BDD entrypoint: bind github_action.feature scenarios to pytest-bdd."""

from pytest_bdd import scenarios

scenarios("github_action.feature")
