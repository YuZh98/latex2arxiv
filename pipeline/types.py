"""Shared types for the conversion pipeline.

Re-exported from `converter` to preserve the public API:
`from converter import Issues, ConverterError`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ConvertContext:
    """Locals built up by `convert()` before per-file processing begins, bundled
    so they cross function boundaries cleanly. Fields are the union of what the
    extracted pipeline helpers (currently `pipeline.process._process_files`)
    actually read; add new fields only when a helper needs them."""

    root: Path
    main_tex: Path
    all_tex_files: set[Path]
    whitelist: set[Path]
    user_config: dict[str, Any]


class ConverterError(Exception):
    """Fatal converter failure. Raised from within convert() / _resolve_input()
    instead of calling sys.exit(1) so that main() can wrap the call and emit
    a JSON envelope under --json before exiting non-zero."""


class Issues:
    """Collect [warn] and [error] events plus enough run metadata to build
    a machine-readable summary (consumed by --json mode)."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        # JSON-payload fields. All optional, set by convert()/main() as the
        # run progresses. None / empty defaults are safe under fatal early exits.
        self.input_path: str | None = None
        self.output_path: str | None = None
        self.main_tex: str | None = None
        self.dry_run: bool = False
        self.removed_files: list[str] = []
        self.kept_files: list[str] = []
        self.sizes_input: int | None = None
        self.sizes_output: int | None = None
        self.sizes_uncompressed: int | None = None
        self.compile_result: dict | None = None
        # --flatten state (always present in the JSON payload).
        self.flatten: bool = False
        self.inlined_files: list[str] = []
        self.metadata: dict | None = None

    def warn(self, msg: str) -> None:
        print(f"  [warn] {msg}")
        self.warnings.append(msg)

    def error(self, msg: str) -> None:
        print(f"  [error] {msg}")
        self.errors.append(msg)
