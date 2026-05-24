"""BDD entrypoint: bind vscode_extension.feature scenarios to pytest-bdd."""

from pytest_bdd import scenarios

scenarios("vscode_extension.feature")
