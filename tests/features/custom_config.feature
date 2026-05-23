Feature: Custom removal rules via YAML config
  As a paper author with project-specific commands or packages to strip
  I want to point latex2arxiv at a YAML config
  So that I can extend cleaning behavior without touching the source code

  # Reference shape: arxiv_config.yaml in the repo root.

  Background:
    Given the `latex2arxiv` CLI is installed
    And a LaTeX project zip "paper.zip"
    And a YAML file "my_rules.yaml" with custom removal rules

  Scenario: --config applies custom command removal
    Given "my_rules.yaml" declares a removable command "mynote"
    And the main .tex contains `\mynote{ignore me}`
    When I run `latex2arxiv paper.zip --config my_rules.yaml`
    Then the `\mynote{ignore me}` block is removed from the cleaned main .tex

  Scenario: --config applies environment removal
    Given "my_rules.yaml" lists "draftbox" under `environments_to_delete`
    And the main .tex contains `\begin{draftbox}...\end{draftbox}`
    When I run `latex2arxiv paper.zip --config my_rules.yaml`
    Then the entire `draftbox` environment (including its body) is removed

  Scenario: --config applies regex replacements
    Given "my_rules.yaml" lists a `replacements` rule mapping `FIXME:` to ``
    And the main .tex contains the literal text "FIXME: revise this"
    When I run `latex2arxiv paper.zip --config my_rules.yaml`
    Then the substring "FIXME:" is removed from the cleaned main .tex

  Scenario: Unknown YAML keys produce a clear warning
    Given "my_rules.yaml" contains a misspelled top-level key like `command_to_delete`
    When I run `latex2arxiv paper.zip --config my_rules.yaml`
    Then a "[warn]" lists the unknown key and the four accepted keys (`commands_to_delete`, `commands_to_unwrap`, `environments_to_delete`, `replacements`)
    And the process exits with code 0 if no other errors are present

  Scenario: arxiv_config.yaml at project root is auto-detected
    Given the project root contains an "arxiv_config.yaml" file
    And no `--config` flag is passed
    When I run `latex2arxiv paper.zip`
    Then the auto-detected config is loaded and applied
    And stderr notes which config file was used

  Scenario: Missing config file fails fast with a clear error
    When I run `latex2arxiv paper.zip --config does_not_exist.yaml`
    Then the process exits non-zero
    And stderr explains that the config file was not found

  Scenario: Malformed YAML produces a parse-error message
    Given "my_rules.yaml" contains malformed YAML
    When I run `latex2arxiv paper.zip --config my_rules.yaml`
    Then the process exits non-zero
    And stderr contains a YAML parse error pointing to the problem location

  Scenario: Custom rules compose with built-in rules
    Given "my_rules.yaml" declares a custom command "mynote"
    And the main .tex contains both `\mynote{...}` and `\todo{...}`
    When I run `latex2arxiv paper.zip --config my_rules.yaml`
    Then both `\mynote{...}` and `\todo{...}` are removed
