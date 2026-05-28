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
# Returns: JSON string with main_tex + errors + warnings, marshalled back
# to JS via the runPython return value.

import json
from pathlib import Path
from converter import convert

issues = convert(
    input_zip=Path("/tmp/input.zip"),
    output_zip=Path("/tmp/output.zip"),
    dry_run=(_l2a_mode == "validate"),
    flatten=bool(_l2a_opts.get("flatten")),
    resize=1600 if _l2a_opts.get("resize") else None,
    guide=bool(_l2a_opts.get("guide")),
)

json.dumps({
    "main_tex": issues.main_tex,
    "errors": list(issues.errors),
    "warnings": list(issues.warnings),
})
