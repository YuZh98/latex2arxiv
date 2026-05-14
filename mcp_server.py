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
from typing import TypedDict, NotRequired

from mcp.server.fastmcp import FastMCP

from converter import convert, ConverterError

mcp = FastMCP("latex2arxiv", instructions=(
    "Validates LaTeX projects against arXiv submission requirements. "
    "Use validate_submission for a dry-run pre-flight check, or "
    "clean_submission to produce an arXiv-ready zip."
))


class MCPEnvelope(TypedDict):
    """Stable return shape for all MCP tools (v1.0)."""
    success: bool
    errors: list[str]
    warnings: list[str]
    log: str
    output_zip: NotRequired[str]  # present in clean_submission on success


def _error_envelope(errors: list[str], log: str = "",
                    warnings: list[str] | None = None) -> MCPEnvelope:
    return MCPEnvelope(success=False, errors=errors,
                       warnings=warnings or [], log=log)


def _safe_root() -> Path:
    """Return the base directory that MCP tool paths must reside under."""
    env = os.environ.get("LATEX2ARXIV_MCP_BASE_DIR")
    return Path(env).resolve() if env else Path.cwd().resolve()


def _validate_path(raw: str) -> tuple[Path | None, MCPEnvelope | None]:
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


def _run_convert(path: str, dry_run: bool, main_hint: str | None = None,
                 config_path: str | None = None) -> MCPEnvelope:
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

    extra_warnings: list[str] = []
    tmp_input_path: Path | None = None

    fd, _tmp = tempfile.mkstemp(suffix='_arxiv.zip')
    os.close(fd)
    out = Path(_tmp)
    out_claimed = False  # True when caller receives output_zip and owns cleanup

    try:
        if inp.is_dir():
            tmp = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
            tmp.close()
            tmp_input_path = Path(tmp.name)
            with zipfile.ZipFile(tmp_input_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file in sorted(inp.rglob('*')):
                    if not file.is_file():
                        continue
                    # Resolve symlinks; skip and warn if they escape the project root.
                    try:
                        file.resolve().relative_to(inp.resolve())
                    except ValueError:
                        extra_warnings.append(
                            f"symlink escapes project root and was excluded: "
                            f"{file.relative_to(inp)}"
                        )
                        continue
                    parts = file.relative_to(inp).parts
                    if any(p in {'.git', '__pycache__'} for p in parts):
                        continue
                    if file.suffix in {'.pyc', '.pyo'}:
                        continue
                    zf.write(file, file.relative_to(inp))
            inp = tmp_input_path

        buf = StringIO()
        try:
            with redirect_stdout(buf):
                issues = convert(inp, out, main_hint=main_hint,
                                 config_path=cfg, dry_run=dry_run)
        except ConverterError as e:
            return _error_envelope([str(e)], buf.getvalue(), extra_warnings)
        except SystemExit:
            output = buf.getvalue()
            return _error_envelope([output.strip()], output, extra_warnings)
        except Exception as e:
            output = buf.getvalue()
            return _error_envelope(
                [f"unexpected error: {type(e).__name__}: {e}"], output, extra_warnings
            )

        result = MCPEnvelope(
            success=len(issues.errors) == 0,
            errors=issues.errors,
            warnings=extra_warnings + issues.warnings,
            log=buf.getvalue(),
        )
        if not dry_run and out.exists():
            result["output_zip"] = str(out)
            out_claimed = True
        elif out.exists():
            out.unlink()

        return result

    finally:
        if tmp_input_path is not None:
            tmp_input_path.unlink(missing_ok=True)
        if not out_claimed and out.exists():
            out.unlink()


@mcp.tool()
def validate_submission(
    path: str,
    main_tex: str | None = None,
    config: str | None = None,
) -> MCPEnvelope:
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
) -> MCPEnvelope:
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
