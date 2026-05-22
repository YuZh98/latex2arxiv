# BDD feature specifications

Gherkin-format user cases describing latex2arxiv's external behavior from the
user's point of view. Grouped by surface (CLI, MCP server, VS Code extension,
GitHub Action).

**Status: specification only.** These files document expected behavior in a
human-and-machine-readable form. They are **not wired to a step-definition
runner** (e.g. `pytest-bdd`). The authoritative executable test suite remains
under `tests/test_*.py`.

A future PR may add `pytest-bdd` step definitions; until then, treat these
files as living acceptance criteria — they should be updated alongside any
behavior change in the same PR, and audited against the executable tests on
each major release.

## File index

| File | Surface | Covers |
|---|---|---|
| `cli_inputs.feature` | CLI | zip / directory / git URL / `--demo` input acceptance |
| `clean_prune.feature` | CLI | file pruning, comment stripping, draft-command removal |
| `preflight_checks.feature` | CLI | error/warn checks from `docs/pre-flight.md` |
| `compile.feature` | CLI | `--compile` running pdflatex and opening the PDF |
| `guide.feature` | CLI | `--guide` upload walkthrough generation |
| `dry_run.feature` | CLI | `--dry-run` preview without writing |
| `json_output.feature` | CLI | `--json` schema (v1) and exit codes |
| `flatten.feature` | CLI | `--flatten` single-file output |
| `custom_config.feature` | CLI | `--config` YAML custom removal rules |
| `resize_images.feature` | CLI | `--resize` image downscaling |
| `mcp_server.feature` | MCP | `validate_submission` / `clean_submission` tools |
| `vscode_extension.feature` | VS Code | Validate / Clean commands, settings, validate-on-save |
| `github_action.feature` | CI | composite action inputs/outputs and failure semantics |

## Conventions

- One `Feature:` per file, describing the user-visible capability.
- `Scenario:` lines cover one observable behavior each.
- `Scenario Outline:` with `Examples:` is used where a single rule fans out
  over many triggers (e.g. shell-escape package list).
- Source-of-truth references (CLI flag, pre-flight table row, JSON schema
  field) are noted inline as comments where ambiguity is possible.
