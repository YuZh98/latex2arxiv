Feature: VS Code extension surfaces validation and cleaning inside the editor
  As a paper author working in VS Code with a LaTeX workspace
  I want validate/clean commands and on-save hooks built into the editor
  So that I can catch arXiv issues without leaving the IDE

  # Extension ID: YuZh98.latex2arxiv. Activation: workspaceContains:**/*.tex.

  Background:
    Given the `latex2arxiv` VS Code extension is installed
    And a workspace folder is opened that contains at least one `.tex` file
    And the `latex2arxiv` CLI is available at the configured `latex2arxiv.executablePath`

  Scenario: Activation triggers on any .tex file in the workspace
    When VS Code opens the workspace
    Then the extension is activated automatically

  Scenario: Validate command runs latex2arxiv against the workspace
    When I invoke the command `latex2arxiv: Validate` from the Command Palette
    Then the configured executable is run on the workspace root with `--dry-run`
    And any pre-flight errors and warnings are surfaced in the editor (e.g. via diagnostics, output channel, or notification)

  Scenario: Clean command produces an arXiv-ready zip
    When I invoke the command `latex2arxiv: Clean for arXiv` from the Command Palette
    Then the configured executable is run on the workspace root without `--dry-run`
    And the resulting `_arxiv.zip` location is reported back to the user

  Scenario: validateOnSave runs validation when a .tex file is saved
    Given the setting `latex2arxiv.validateOnSave` is `true`
    When I save any `.tex` file in the workspace
    Then validation runs automatically in the background
    And results are surfaced without blocking the editor

  Scenario: validateOnSave off — saving a .tex file does nothing
    Given the setting `latex2arxiv.validateOnSave` is `false`
    When I save any `.tex` file in the workspace
    Then no validation is triggered

  Scenario: mainFile setting overrides auto-detection
    Given the setting `latex2arxiv.mainFile` is "src/JASA_main.tex"
    When I invoke `latex2arxiv: Validate`
    Then the CLI is invoked with `--main src/JASA_main.tex`

  Scenario: Missing CLI executable surfaces a clear error
    Given `latex2arxiv` is not on PATH and `latex2arxiv.executablePath` points to a missing binary
    When I invoke `latex2arxiv: Validate`
    Then a notification explains that the CLI was not found
    And the notification links to or describes the install instructions
