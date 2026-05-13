# `--json` output schema (v1)

When invoked with `--json`, `latex2arxiv` writes a single JSON object to
**stdout** and routes all progress / diagnostic output to **stderr**. The
exit code is 0 on a clean run and 1 on any pre-flight error or fatal
failure — the JSON envelope is still emitted on failure.

Pipe to `jq` directly:

```bash
latex2arxiv paper.zip --dry-run --json | jq .
```

## Schema (v1)

```jsonc
{
  "version": "0.8.0",            // tool version (from installed package metadata)
  "schema_version": 1,           // bump on any breaking change to this layout
  "input": "path/to/paper.zip",  // absolute or as-passed
  "output": "paper_arxiv.zip",   // null when --dry-run
  "main_tex": "main.tex",        // relative to project root; null if not yet found
  "dry_run": false,              // mirrors the --dry-run flag
  "removed_files": ["foo.aux", "draft/old.tex", "..."],   // relative paths
  "kept_files":    ["main.tex", "refs.bib", "..."],
  "errors":   ["[error] description ...", "..."],         // flat strings, v1
  "warnings": ["[warn] description ...",  "..."],
  "counts": {
    "removed":  12,
    "kept":      8,
    "errors":    0,
    "warnings":  3
  },
  "sizes": {
    "input_bytes":         12345,
    "output_bytes":         6789,                         // null when --dry-run
    "uncompressed_bytes":  23456                          // sum of kept-files' sizes
  },
  "compile": null                                         // reserved for --compile result; null otherwise
}
```

## Field stability promise (v1.x)

The `schema_version: 1` line is the contract:

- **Fields are append-only.** New top-level keys may be added in any v1.x
  release. Consumers should ignore unknown keys.
- **Existing field types do NOT change** within v1. If a field's
  semantics need to evolve, a new field is added and the old one stays
  as-is.
- **No keys are removed** in v1.x. Removal is a breaking change and
  requires `schema_version: 2`.

If you build tooling against this output, branch on `schema_version`
and ignore fields you don't recognise. That contract makes future
additions non-breaking.

## Notes on specific fields

- **`errors` / `warnings`** are flat strings in v1. Structured codes
  (`{code, message, file, line}` objects) are reserved for v2 — they
  require assigning stable codes to every pre-flight string, which is
  more work than fits a v1 release.
- **`removed_files`** lists everything pruned by the converter:
  unused images, response letters, `.aux`/`.log` build artefacts,
  config-driven removals. It does NOT list files outside the project
  root (those don't enter the pipeline).
- **`kept_files`** is the set of files that would land in the output
  zip. Under `--dry-run` no zip is written, but the list reflects what
  would be written.
- **`sizes.uncompressed_bytes`** is the sum of `kept_files` on-disk
  sizes (pre-zip-compression). Useful for the 50 MB arXiv ceiling.
- **`compile`** is reserved for a `--compile` result object in a
  future release. Today it is always `null`.

## Errors and the JSON envelope

Even when the run fails fatally (input not found, no `.tex` in the
zip, zip-slip detected, etc.), `--json` emits a JSON envelope with the
error captured under `errors` and exit code 1:

```json
{
  "version": "0.8.0",
  "schema_version": 1,
  "input": null,
  "output": null,
  "main_tex": null,
  "dry_run": false,
  "removed_files": [],
  "kept_files": [],
  "errors": ["missing.zip not found"],
  "warnings": [],
  "counts": {"removed": 0, "kept": 0, "errors": 1, "warnings": 0},
  "sizes": {"input_bytes": null, "output_bytes": null, "uncompressed_bytes": null},
  "compile": null
}
```

argparse-level errors (missing `input` argument, unknown flag) are
the one exception — they short-circuit through argparse and do not
produce a JSON envelope. The exit code is 2 for those, per Python
convention.
