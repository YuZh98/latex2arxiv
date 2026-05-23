Feature: GitHub Action for arXiv pre-flight in CI
  As a maintainer of a paper repository
  I want a composite action that fails the build on submission blockers
  So that pull requests can't merge if they regress arXiv compatibility

  # Manifest: action.yml at the repo root.

  Background:
    Given a CI job using `uses: YuZh98/latex2arxiv@<ref>` in a step

  Scenario: Default dry-run mode validates without producing a zip
    Given the step input `input` points at a LaTeX project (directory or .zip)
    And the input `dry-run` is left at its default ("true")
    When the action runs
    Then the latex2arxiv CLI is invoked with `--dry-run`
    And no `cleaned-zip` step output is exported

  Scenario: dry-run=false produces an output zip and exports cleaned-zip
    Given the input `dry-run` is set to "false"
    When the action runs
    Then the latex2arxiv CLI is invoked without `--dry-run`
    And the step output `cleaned-zip` is exported pointing at the written zip

  Scenario: Directory input is zipped before invocation
    Given the input `input` is a directory
    When the action runs
    Then the action zips the directory to a temporary location
    And `.git/`, `.github/`, `__pycache__/`, `*.pyc`, `.DS_Store`,
      `*/.DS_Store`, `Thumbs.db`, and `*/Thumbs.db` are excluded from that zip
    And the CLI is invoked against the temp zip

  Scenario Outline: Optional inputs are forwarded to the CLI
    Given the input `<input>` is set to "<value>"
    When the action runs
    Then the CLI is invoked with the flag `<flag>` and the same value

    Examples:
      | input  | value         | flag      |
      | main   | JASA_main.tex | --main    |
      | config | arxiv.yaml    | --config  |
      | resize | 800           | --resize  |

  Scenario: flatten=true appends --flatten to the CLI
    Given the input `flatten` is set to "true"
    When the action runs
    Then the latex2arxiv CLI is invoked with `--flatten`
    And the resulting output reflects the flattened single-file `.tex`

  Scenario: flatten=false (default) does not append --flatten
    Given the input `flatten` is left at its default ("false")
    When the action runs
    Then the latex2arxiv CLI is invoked without `--flatten`

  Scenario: resize value downscales images
    Given the input `resize` is set to "800"
    When the action runs
    Then the latex2arxiv CLI is invoked with `--resize 800`
    And images in the output are downscaled so the longest side ≤ 800 px

  Scenario: resize left empty (default) does not append --resize
    Given the input `resize` is left empty
    When the action runs
    Then the latex2arxiv CLI is invoked without `--resize`

  Scenario: Specific latex2arxiv version pin
    Given the input `version` is set to "0.6.0"
    When the action runs
    Then the install step runs `pip install "latex2arxiv==0.6.0"`

  Scenario: Default install uses the latest from PyPI
    Given the input `version` is left empty
    When the action runs
    Then the install step runs `pip install latex2arxiv` without a version pin

  Scenario: Python version override
    Given the input `python-version` is set to "3.11"
    When the action runs
    Then `actions/setup-python` is invoked with `python-version: 3.11`

  Scenario: Submission blocker fails the job
    Given the LaTeX project triggers a `[error]` (e.g. minted)
    When the action runs in dry-run mode
    Then the latex2arxiv CLI exits with code 1
    And the step fails (`set -e` propagates the non-zero exit)
    And the job is marked failed by the GitHub runner
