"""BDD entrypoint: bind dry_run.feature scenarios to pytest-bdd."""

from pytest_bdd import scenarios

scenarios("dry_run.feature")
