"""latex2arxiv MCP server — exposes arXiv submission validation to AI agents.

Run with:
    python -m mcp_server          (stdio, for Claude Desktop / Cursor / etc.)
    latex2arxiv-mcp               (entry point, same as above)
"""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from converter import convert, ConverterError


mcp = FastMCP(
    "latex2arxiv",
    instructions=(
        "Validates LaTeX projects against arXiv submission requirements. "
        "Use validate_submission for a dry-run pre-flight check, or "
        "clean_submission to produce an arXiv-ready zip."
    ),
)


def _error_envelope(errors: list[str], log: str = "", warnings: list[str] | None = None) -> dict:
    return {"success": False, "errors": errors, "warnings": warnings or [], "log": log}


def _safe_root() -> Path:
    """Return the base directory that MCP tool paths must reside under."""
    env = os.environ.get("LATEX2ARXIV_MCP_BASE_DIR")
    return Path(env).resolve() if env else Path.cwd().resolve()


def _validate_path(raw: str) -> tuple[Path | None, dict | None]:
    """Resolve *raw* and verify it is inside the safe root.

    Returns (resolved_path, None) on success, or (None, error_envelope) on rejection.
    Rejects empty strings and tilde-prefixed paths before resolution.
    """
    if not raw or not raw.strip():
        return None, _error_envelope(["path must not be empty"])
    if raw.startswith("~"):
        return None, _error_envelope([f"Path outside allowed base directory: {raw}"])
    resolved = Path(raw).resolve()
    root = _safe_root()
    if not resolved.is_relative_to(root):
        return None, _error_envelope([f"Path outside allowed base directory: {raw}"])
    return resolved, None


def _run_convert(
    path: str,
    dry_run: bool,
    main_hint: str | None = None,
    config_path: str | None = None,
    output_path: str | None = None,
) -> dict:
    """Run the converter and capture structured results."""
    inp, err = _validate_path(path)
    if err or inp is None:
        return err or _error_envelope(["internal: path validation failed"])
    if not inp.exists():
        return _error_envelope([f"Path not found: {path}"])

    # Validate config path before creating any temp files so early rejection
    # does not leak the output sentinel.
    if config_path is not None:
        cfg_resolved, cfg_err = _validate_path(config_path)
        if cfg_err or cfg_resolved is None:
            return cfg_err or _error_envelope(["internal: config path validation failed"])
        cfg = cfg_resolved
    else:
        cfg = None

    # Validate output_path before creating any temp files.
    if output_path is not None:
        out_resolved, out_err = _validate_path(output_path)
        if out_err or out_resolved is None:
            return out_err or _error_envelope(["internal: output path validation failed"])
        if not out_resolved.parent.exists():
            return _error_envelope([f"Output directory does not exist: {out_resolved.parent}"])
        out = out_resolved
    else:
        fd, _tmp = tempfile.mkstemp(suffix="_arxiv.zip")
        os.close(fd)
        out = Path(_tmp)

    extra_warnings: list[str] = []
    tmp_input_path: Path | None = None

    out_claimed = False  # True when caller receives output_zip and owns cleanup

    try:
        if inp.is_dir():
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            tmp.close()
            tmp_input_path = Path(tmp.name)
            inp_resolved = inp.resolve()
            with zipfile.ZipFile(tmp_input_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for dirpath_str, dirnames, filenames in os.walk(inp, followlinks=False):
                    dirpath = Path(dirpath_str)
                    kept_dirs: list[str] = []
                    for d in dirnames:
                        if d in {".git", "__pycache__"}:
                            continue
                        sub = dirpath / d
                        if sub.is_symlink():
                            # os.walk(followlinks=False) silently skips symlinked
                            # dirs; emit a warning so users see content was dropped.
                            extra_warnings.append(
                                f"symlinked directory was excluded (followlinks=False): {sub.relative_to(inp)}"
                            )
                            continue
                        kept_dirs.append(d)
                    dirnames[:] = kept_dirs
                    for filename in sorted(filenames):
                        file = dirpath / filename
                        if file.suffix in {".pyc", ".pyo"}:
                            continue
                        if file.is_symlink():
                            try:
                                file.resolve().relative_to(inp_resolved)
                            except ValueError:
                                extra_warnings.append(
                                    f"symlink escapes project root and was excluded: {file.relative_to(inp)}"
                                )
                                continue
                        zf.write(file, file.relative_to(inp))
            inp = tmp_input_path

        # Pipeline print() calls go to stderr (the correct channel for MCP
        # diagnostic output). We do NOT redirect sys.stdout because FastMCP
        # captures sys.stdout.buffer at startup for JSON-RPC frames; any global
        # swap of sys.stdout risks silently dropping protocol writes into a buffer.
        # TODO (Option B): thread a log-callable through convert() in converter.py
        # so pipeline output can be captured cleanly without touching sys.stdout.
        try:
            issues = convert(inp, out, main_hint=main_hint, config_path=cfg, dry_run=dry_run)
        except ConverterError as e:
            return _error_envelope([str(e)], "", extra_warnings)
        except SystemExit as e:
            return _error_envelope([f"converter exited unexpectedly (code {e.code})"], "", extra_warnings)
        except Exception as e:
            return _error_envelope([f"unexpected error: {type(e).__name__}: {e}"], "", extra_warnings)

        result: dict = {
            "success": len(issues.errors) == 0,
            "errors": issues.errors,
            "warnings": extra_warnings + issues.warnings,
            # Pipeline progress goes to stderr; structured findings are in errors/warnings above.
            "log": "",
        }
        if not dry_run and out.exists():
            result["output_zip"] = str(out)
            out_claimed = True
        elif out.exists():
            out.unlink()

        return result

    finally:
        if tmp_input_path is not None:
            tmp_input_path.unlink(missing_ok=True)
        # Only unlink output if WE created it (temp file path). When the caller
        # supplied output_path they own the file; never delete it on failure.
        if not out_claimed and output_path is None and out.exists():
            out.unlink()


@mcp.tool()
def validate_submission(
    path: str,
    main_tex: str | None = None,
    config: str | None = None,
) -> dict:
    """Validate a LaTeX project against arXiv submission requirements (dry-run).

    Runs all pre-flight checks without producing output. Returns errors and
    warnings that would block or complicate an arXiv submission.

    Args:
        path: Path to a .zip file or directory containing the LaTeX project.
        main_tex: Optional filename of the main .tex file (auto-detected if omitted).
        config: Optional path to a YAML config file for custom removal rules.
    """
    return _run_convert(path, dry_run=True, main_hint=main_tex, config_path=config)


@mcp.tool()
def clean_submission(
    path: str,
    main_tex: str | None = None,
    config: str | None = None,
    output_path: str | None = None,
) -> dict:
    """Clean a LaTeX project and produce an arXiv-ready zip.

    Prunes unused files, strips comments and draft annotations, runs pre-flight
    checks, and outputs a submission-ready .zip file.

    Args:
        path: Path to a .zip file or directory containing the LaTeX project.
        main_tex: Optional filename of the main .tex file (auto-detected if omitted).
        config: Optional path to a YAML config file for custom removal rules.
        output_path: Optional path where the output zip should be written. When
            provided the caller owns the file and is responsible for cleanup.
            If omitted, a temporary file is created and its path is returned in
            ``output_zip``; the caller must delete it after use.
    """
    return _run_convert(path, dry_run=False, main_hint=main_tex, config_path=config, output_path=output_path)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
