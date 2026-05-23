"""BDD entrypoint: bind clean_prune.feature scenarios to pytest-bdd."""

from pytest_bdd import scenarios

scenarios("clean_prune.feature")
