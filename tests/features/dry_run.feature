Feature: Preview the run without producing output
  As a CI maintainer or cautious author
  I want to see what would change without writing anything to disk
  So that I can gate a build on arXiv compliance and inspect changes safely

  Background:
    Given the `latex2arxiv` CLI is installed
    And a LaTeX project zip "paper.zip"

  Scenario: --dry-run writes no output zip
    When I run `latex2arxiv paper.zip --dry-run`
    Then no "paper_arxiv.zip" file is created
    And no intermediate files are left on disk
    And the input "paper.zip" is unchanged

  Scenario: --dry-run still reports the planned actions
    # Non-JSON mode routes all progress to stdout; --json switches progress
    # to stderr so the JSON envelope can be parsed cleanly from stdout.
    When I run `latex2arxiv paper.zip --dry-run`
    Then stdout summarises files that would be removed
    And stdout summarises files that would be kept
    And stdout contains a "[dry-run] No output written." style notice

  Scenario: --dry-run still runs all pre-flight checks
    Given the project triggers a `[warn]` (e.g. `\today` in `\date`)
    And the project triggers an `[error]` (e.g. `\usepackage{minted}`)
    When I run `latex2arxiv paper.zip --dry-run`
    Then both the warning and the error are emitted on stdout
    And the process exits with code 1 because of the error

  Scenario: --dry-run on a clean project exits zero
    Given a project that triggers no errors and no warnings
    When I run `latex2arxiv paper.zip --dry-run`
    Then the process exits with code 0

  Scenario: --dry-run + --json still emits a complete JSON envelope
    When I run `latex2arxiv paper.zip --dry-run --json`
    Then stdout is a single JSON object
    And the field `dry_run` is `true`
    And the field `output` is `null`
    And the field `sizes.output_bytes` is `null`
