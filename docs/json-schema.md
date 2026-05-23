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
  "version": "1.2.0",            // tool version (from installed package metadata)
  "schema_version": 1,           // bump on any breaking change to this layout
  "input": "path/to/paper.zip",  // absolute or as-passed
  "output": "paper_arxiv.zip",   // null when --dry-run
  "main_tex": "main.tex",        // relative to project root; null if not yet found
  "dry_run": false,              // mirrors the --dry-run flag
  "removed_files": ["foo.aux", "draft/old.tex", "..."],   // relative paths
  "kept_files":    ["main.tex", "refs.bib", "..."],
  "errors":   ["minted requires shell-escape; arXiv does not support it", "..."],   // flat strings, v1; no [error] prefix
  "warnings": ["\\today used in \\date — arXiv may rebuild the PDF", "..."],          // flat strings, v1; no [warn] prefix
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
  "compile": null,                                        // always null in v1.0; reserved for a future --compile result shape
  "flatten": false,                                       // true when --flatten was passed; mirrors the flag
  "inlined_files": [],                                    // list of fragment .tex files that were inlined when --flatten is on (empty otherwise)
  "metadata": null                                        // extracted paper metadata (see below); null on fatal errors or when extraction fails
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

## Stability contract

**Schema structure** (`schema_version`, all field names, field types) is stable from v1.0.0.

**String content** of `errors[]` and `warnings[]` items is **NOT stable**. Do not
substring-match, regex-match, or hard-code against the exact wording of any message.
Messages may change in any release without a schema-version bump. Use the presence and
count of errors/warnings to gate decisions; parse field names (`errors`, `warnings`,
`counts.*`) not message text.

**`compile` field:** Always `null` in v1.0 — including when `--compile` is used. The
field is reserved for a future release that will expose the compile result as a structured
object. MCP tools do not support `--compile`. Do not write code that expects a non-null
value here.

## Notes on specific fields

- **`errors` / `warnings`** are flat strings in v1, with **no
  `[error]` / `[warn]` prefix**. The prefixes are part of the
  text-mode console rendering only; the JSON-payload strings are the
  raw messages. Structured codes (`{code, message, file, line}`
  objects) are reserved for v2 — they require assigning stable codes
  to every pre-flight string, which is more work than fits a v1
  release.
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
- **`flatten`** mirrors the `--flatten` flag. `false` for the default
  invocation; `true` when the run inlined every `\input` / `\include`
  / `\subfile` into the main `.tex`.
- **`inlined_files`** is the list of fragment files that `--flatten`
  inlined (relative paths). Empty when `flatten: false`.
- **`metadata`** contains extracted paper metadata when available:
  `{"title": str, "authors": str, "abstract": str, "stats": {"figures": int, "tables": int, "pages": int|null}}`.
  `null` on fatal errors or when the main `.tex` content cannot be parsed.

## Errors and the JSON envelope

Even when the run fails fatally (input not found, no `.tex` in the
zip, zip-slip detected, etc.), `--json` emits a JSON envelope with the
error captured under `errors` and exit code 1:

```json
{
  "version": "1.2.0",
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
  "compile": null,
  "flatten": false,
  "inlined_files": [],
  "metadata": null
}
```

argparse-level errors (missing `input` argument, unknown flag) are
the one exception — they short-circuit through argparse and do not
produce a JSON envelope. The exit code is 2 for those, per Python
convention.

An unexpected internal exception (`MemoryError`, library crash) is
also not captured into `errors`: the JSON envelope is still emitted
with an empty `errors` list, the traceback prints to stderr, and the
process exits 1. Consumers should treat a non-zero exit code as a
failure signal even when `errors` is empty.
