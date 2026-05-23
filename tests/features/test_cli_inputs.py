"""BDD entrypoint: bind cli_inputs.feature scenarios to pytest-bdd."""

from pytest_bdd import scenarios

scenarios("cli_inputs.feature")
