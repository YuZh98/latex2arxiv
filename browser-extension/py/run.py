# Python entrypoint executed by Pyodide inside the worker (worker.js) and
# rehearsed by the Node smoke test (tests/pyodide-smoke.mjs). Single source
# of truth — both call sites load this file at runtime.
#
# Globals injected by the caller via pyodide.globals.set before runPython:
#   _l2a_mode : "clean" | "validate"
#   _l2a_opts : dict (Python dict via pyodide.toPy({...}))
#
# Inputs/outputs on the Pyodide MEMFS:
#   /tmp/input.zip  (written by caller before runPython)
#   /tmp/output.zip (written when mode == "clean"; absent on dry_run)
#
# Returns: JSON string with main_tex + errors + warnings + count/size summary,
# marshalled back to JS via the runPython return value. The full kept/removed
# file lists stay on the Python side so each click does not JSON-serialize
# hundreds of strings across two chrome.runtime hops.

import json
from pathlib import Path
from converter import convert

# Longest-side pixel target when the user enables the "resize images" toggle.
# Matches the value the CLI surfaces via `--resize` without an argument.
RESIZE_LONGEST_SIDE_PX = 1600

# `main` may be missing, None, or an empty string when the user has not typed
# anything in the override field. Coerce all three to None so the pipeline's
# auto-detect heuristic runs.
_main_value = _l2a_opts.get("main")
_main_hint = _main_value if isinstance(_main_value, str) and _main_value.strip() else None

issues = convert(
    input_zip=Path("/tmp/input.zip"),
    output_zip=Path("/tmp/output.zip"),
    main_hint=_main_hint,
    dry_run=(_l2a_mode == "validate"),
    flatten=bool(_l2a_opts.get("flatten")),
    resize=RESIZE_LONGEST_SIDE_PX if _l2a_opts.get("resize") else None,
    guide=bool(_l2a_opts.get("guide")),
)

json.dumps({
    "main_tex": issues.main_tex,
    "errors": list(issues.errors),
    "warnings": list(issues.warnings),
    "kept_count": len(issues.kept_files),
    "removed_count": len(issues.removed_files),
    "sizes_input_bytes": issues.sizes_input,
    "sizes_output_bytes": issues.sizes_output,
    "sizes_uncompressed_bytes": issues.sizes_uncompressed,
})
