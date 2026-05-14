"""latex2arxiv MCP server — exposes arXiv submission validation to AI agents.

Run with:
    python -m mcp_server          (stdio, for Claude Desktop / Cursor / etc.)
    latex2arxiv-mcp               (entry point, same as above)
"""

from __future__ import annotations

import os
import tempfile
import zipfile
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout

from mcp.server.fastmcp import FastMCP

from converter import convert, ConverterError

mcp = FastMCP("latex2arxiv", instructions=(
    "Validates LaTeX projects against arXiv submission requirements. "
    "Use validate_submission for a dry-run pre-flight check, or "
    "clean_submission to produce an arXiv-ready zip."
))


def _safe_root() -> Path:
    """Return the base directory that MCP tool paths must reside under."""
    env = os.environ.get("LATEX2ARXIV_MCP_BASE_DIR")
    return Path(env).resolve() if env else Path.cwd()


def _validate_path(raw: str) -> tuple[Path | None, dict | None]:
    """Resolve *raw* and verify it is inside the safe root.

    Returns (resolved_path, None) on success, or (None, error_dict) on rejection.
    Rejects tilde-prefixed paths before resolution so agents cannot probe home dirs.
    """
    if raw.startswith("~"):
        return None, {"success": False, "errors": [f"Path outside allowed base directory: {raw}"], "warnings": [], "log": ""}
    resolved = Path(raw).resolve()
    root = _safe_root()
    if not resolved.is_relative_to(root):
        return None, {"success": False, "errors": [f"Path outside allowed base directory: {raw}"], "warnings": [], "log": ""}
    return resolved, None


def _run_convert(path: str, dry_run: bool, main_hint: str | None = None,
                 config_path: str | None = None) -> dict:
    """Run the converter and capture structured results."""
    inp, err = _validate_path(path)
    if err or inp is None:
        return err or {"success": False, "errors": ["internal: path validation failed"], "warnings": [], "log": ""}
    if not inp.exists():
        return {"success": False, "errors": [f"Path not found: {path}"], "warnings": [], "log": ""}

    # If input is a directory, we pass it through; if zip, use directly
    if inp.is_dir():
        # Zip the directory into a temp file
        tmp = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
        tmp.close()
        tmp_path = Path(tmp.name)
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(inp.rglob('*')):
                if file.is_file() and '.git' not in file.parts:
                    zf.write(file, file.relative_to(inp))
        inp = tmp_path
        cleanup_input = True
    else:
        cleanup_input = False

    fd, _tmp = tempfile.mkstemp(suffix='_arxiv.zip')
    os.close(fd)
    out = Path(_tmp)
    if config_path is not None:
        cfg_resolved, cfg_err = _validate_path(config_path)
        if cfg_err or cfg_resolved is None:
            return cfg_err or {"success": False, "errors": ["internal: config path validation failed"], "warnings": [], "log": ""}
        cfg = cfg_resolved
    else:
        cfg = None

    # Capture stdout (the tool's print output)
    buf = StringIO()
    try:
        with redirect_stdout(buf):
            issues = convert(inp, out, main_hint=main_hint,
                             config_path=cfg, dry_run=dry_run)
    except ConverterError as e:
        return {"success": False, "errors": [str(e)], "warnings": [], "log": buf.getvalue()}
    except SystemExit:
        # Legacy guard for any sys.exit() paths that may still slip through.
        output = buf.getvalue()
        return {"success": False, "errors": [output.strip()], "warnings": [], "log": output}
    finally:
        if cleanup_input:
            inp.unlink(missing_ok=True)

    result: dict = {
        "success": len(issues.errors) == 0,
        "errors": issues.errors,
        "warnings": issues.warnings,
        "log": buf.getvalue(),
    }
    if not dry_run and out.exists():
        result["output_zip"] = str(out)
    elif out.exists():
        out.unlink()

    return result


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
) -> dict:
    """Clean a LaTeX project and produce an arXiv-ready zip.

    Prunes unused files, strips comments and draft annotations, runs pre-flight
    checks, and outputs a submission-ready .zip file.

    Args:
        path: Path to a .zip file or directory containing the LaTeX project.
        main_tex: Optional filename of the main .tex file (auto-detected if omitted).
        config: Optional path to a YAML config file for custom removal rules.
    """
    return _run_convert(path, dry_run=False, main_hint=main_tex, config_path=config)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
