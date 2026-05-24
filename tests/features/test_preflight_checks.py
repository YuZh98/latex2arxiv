"""BDD entrypoint: bind preflight_checks.feature scenarios to pytest-bdd."""

from pytest_bdd import scenarios

scenarios("preflight_checks.feature")
