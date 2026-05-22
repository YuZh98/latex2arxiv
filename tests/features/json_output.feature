Feature: Machine-readable JSON summary for CI and tooling
  As a CI pipeline author or downstream tool builder
  I want a stable JSON envelope describing the run
  So that I can branch on errors, sizes, and metadata without scraping logs

  # Schema canonical reference: docs/json-schema.md (schema_version: 1).

  Background:
    Given the `latex2arxiv` CLI is installed
    And a LaTeX project zip "paper.zip"

  Scenario: --json writes exactly one JSON object on stdout
    When I run `latex2arxiv paper.zip --json`
    Then stdout is a single valid JSON object
    And no human-progress text appears on stdout
    And human-progress text appears on stderr instead

  Scenario: --json envelope contains the v1 top-level keys
    When I run `latex2arxiv paper.zip --json`
    Then the JSON object contains at minimum the keys:
      | version          |
      | schema_version   |
      | input            |
      | output           |
      | main_tex         |
      | dry_run          |
      | removed_files    |
      | kept_files       |
      | errors           |
      | warnings         |
      | counts           |
      | sizes            |
      | compile          |
      | flatten          |
      | inlined_files    |
      | metadata         |
    And `schema_version` equals `1`

  Scenario: errors and warnings are flat strings without [error]/[warn] prefixes
    Given the project triggers at least one error and one warning
    When I run `latex2arxiv paper.zip --json --dry-run`
    Then each entry in `errors[]` is a plain string without an "[error]" prefix
    And each entry in `warnings[]` is a plain string without a "[warn]" prefix

  Scenario: counts and sizes match the file lists
    When I run `latex2arxiv paper.zip --json`
    Then `counts.removed` equals the length of `removed_files`
    And `counts.kept` equals the length of `kept_files`
    And `counts.errors` equals the length of `errors`
    And `counts.warnings` equals the length of `warnings`
    And `sizes.input_bytes` matches the on-disk size of the input
    And `sizes.uncompressed_bytes` matches the sum of kept-file sizes

  Scenario: Exit code 1 on any pre-flight error, with JSON still emitted
    Given the project triggers a `[error]`
    When I run `latex2arxiv paper.zip --json`
    Then stdout still contains a valid JSON object with `errors` non-empty
    And the process exits with code 1

  Scenario: Fatal failure still emits the JSON envelope
    Given an input that causes a fatal converter error (e.g. corrupt zip)
    When I run `latex2arxiv paper.zip --json`
    Then stdout still contains a valid JSON object describing the failure
    And the process exits with code 1

  Scenario: --json field stability — unknown keys must be ignored by consumers
    Given a future release adds a new top-level key not listed in v1.0
    When a v1.x consumer parses the output
    Then it ignores the unknown key and reads `schema_version` to branch
