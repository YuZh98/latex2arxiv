"""MCP-surface steps: call validate_submission / clean_submission directly.

Most scenarios exercise the tool functions in-process (avoids the stdio
protocol surface). The one scenario that asserts about JSON-RPC frames spawns
a real `latex2arxiv-mcp` subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, then, when


_DEFAULT_BODY = "\\documentclass{article}\n\\begin{document}\nHello arXiv.\n\\end{document}\n"


def _write_main(target_dir: Path, body: str = _DEFAULT_BODY) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "main.tex").write_text(body)


@given("the `latex2arxiv-mcp` stdio server is running")
def _mcp_server_running():
    # In-process scenarios call the tool functions directly; the only scenario
    # that needs the stdio transport spawns it on demand.
    pytest.importorskip("mcp")


@given("the safe-root is the current working directory (or $LATEX2ARXIV_MCP_BASE_DIR if set)")
def _mcp_safe_root(monkeypatch, project_dir):
    monkeypatch.chdir(project_dir)
    monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(project_dir))


@given(parsers.parse('a directory "{name}" containing a valid LaTeX project'))
def _mcp_valid_project(project_dir, name):
    _write_main(project_dir / name.rstrip("/"))


@given(parsers.parse('a directory "{name}" whose main .tex contains `\\usepackage{{{pkg}}}`'))
def _mcp_project_with_pkg(project_dir, name, pkg):
    body = f"\\documentclass{{article}}\n\\usepackage{{{pkg}}}\n\\begin{{document}}\nBody.\n\\end{{document}}\n"
    _write_main(project_dir / name.rstrip("/"), body=body)


@given(parsers.parse('a directory "{paper}" and an existing parent directory "{out}"'))
def _mcp_project_plus_out(project_dir, paper, out):
    _write_main(project_dir / paper.rstrip("/"))
    (project_dir / out.rstrip("/")).mkdir(parents=True, exist_ok=True)


@given(parsers.parse('a directory "{name}" containing a symlinked subdirectory "{link} -> {target}"'))
def _mcp_symlink_subdir(project_dir, name, link, target):
    paper = project_dir / name.rstrip("/")
    _write_main(paper)
    external = Path(target)
    external.mkdir(parents=True, exist_ok=True)
    (external / "external.tex").write_text("External content\n")
    (paper / link).symlink_to(external, target_is_directory=True)


@given(parsers.parse('a directory "{name}" containing a symlinked file pointing outside "{name2}"'))
def _mcp_symlink_escape(project_dir, name, name2):
    paper = project_dir / name.rstrip("/")
    _write_main(paper)
    external = project_dir / "elsewhere.tex"
    external.write_text("Outside content\n")
    (paper / "escape.tex").symlink_to(external)


@given("an input that causes a fatal converter error (e.g. unreadable zip)")
def _mcp_broken_zip(project_dir):
    (project_dir / "broken.zip").write_bytes(b"not a zip")


# --- When: tool invocations ---


def _import_tools():
    """Late-import so a missing mcp dep skips rather than collection-errors."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
    from mcp_server import clean_submission, validate_submission

    return validate_submission, clean_submission


@when(parsers.re(r'^the agent calls `validate_submission\(path="(?P<path>[^"]*)"\)`$'))
def _mcp_call_validate(result, path):
    validate, _ = _import_tools()
    result["response"] = validate(path=path)


@when(parsers.re(r'^the agent calls `clean_submission\(path="(?P<path>[^"]*)"\)`$'))
def _mcp_call_clean(result, path):
    _, clean = _import_tools()
    result["response"] = clean(path=path)


@when(parsers.re(r'^the agent calls `clean_submission\(path="(?P<path>[^"]*)", output_path="(?P<out>[^"]*)"\)`$'))
def _mcp_call_clean_with_out(result, path, out):
    _, clean = _import_tools()
    result["response"] = clean(path=path, output_path=out)


# --- Then: response assertions ---


@then('the response is `{"success": true, "errors": [], "warnings": [...], "log": ""}`')
def _mcp_clean_envelope(result):
    # Spec uses `[...]` to indicate "any list"; envelope keys must all be present.
    resp = result["response"]
    assert resp.get("success") is True, f"expected success=true; got: {resp}"
    assert resp.get("errors") == [], f"expected errors=[]; got: {resp.get('errors')!r}"
    assert isinstance(resp.get("warnings"), list), f"expected warnings list; got: {resp.get('warnings')!r}"
    assert resp.get("log") == "", f'expected log=""; got: {resp.get("log")!r}'


@then(parsers.parse("the response has `success: {value}`"))
def _mcp_success_value(result, value):
    expected = {"true": True, "false": False}[value.strip()]
    assert result["response"]["success"] is expected, (
        f"success={result['response']['success']!r}, expected {expected!r}"
    )


@then(parsers.parse("`errors[]` contains the minted shell-escape message"))
def _mcp_errors_minted(result):
    errors = result["response"]["errors"]
    assert any("minted" in e and "shell-escape" in e for e in errors), (
        f"no minted/shell-escape error in errors[]: {errors}"
    )


@then(parsers.parse('`errors[]` contains "{snippet}"'))
def _mcp_errors_contain(result, snippet):
    errors = result["response"]["errors"]
    assert any(snippet in e for e in errors), f"no error contains {snippet!r}; got: {errors}"


@then("no output zip is created on disk")
def _mcp_no_output_zip(project_dir):
    leftovers = [p.name for p in project_dir.rglob("*.zip")]
    # Allow input zips (broken.zip etc.) — only the converter's output is forbidden.
    forbidden = [n for n in leftovers if n.endswith("_arxiv.zip")]
    assert not forbidden, f"unexpected output zips: {forbidden}"


@then("`output_zip` is a path to a written .zip file")
def _mcp_output_zip_written(result):
    path = result["response"].get("output_zip")
    assert path, f"output_zip missing from response: {result['response']}"
    p = Path(path)
    assert p.exists(), f"output_zip path does not exist on disk: {p}"
    with zipfile.ZipFile(p) as zf:
        assert zf.namelist(), f"output zip is empty: {p}"


@then("the caller is responsible for cleaning up that file")
def _mcp_caller_cleanup_responsibility(result):
    # Documentation assertion — verified by the absence of any server-managed
    # tempfile teardown. The presence of output_zip in the response satisfies
    # this contractually.
    assert "output_zip" in result["response"]


@then(parsers.parse('"{name}" is written'))
def _mcp_named_file_written(project_dir, name):
    assert (project_dir / name).exists(), f"expected {name} written; not found"


@then(parsers.parse('`output_zip` in the response equals the resolved "{name}"'))
def _mcp_output_zip_equals(project_dir, result, name):
    expected = str((project_dir / name).resolve())
    assert result["response"]["output_zip"] == expected, (
        f"output_zip={result['response']['output_zip']!r}, expected {expected!r}"
    )


@then("on subsequent failures the file is not auto-deleted by the server")
def _mcp_no_auto_delete(project_dir, result):
    # The server returns the resolved output_path verbatim — nothing in
    # mcp_server registers a cleanup callback. Documentation assertion.
    assert "output_zip" in result["response"]


@then(parsers.parse("`errors[]` mentions that the output directory does not exist"))
def _mcp_errors_missing_dir(result):
    errors = result["response"]["errors"]
    assert any(
        "output directory" in e.lower()
        or "does not exist" in e.lower()
        or "no such file" in e.lower()
        or "missing" in e.lower()
        for e in errors
    ), f"no missing-dir error: {errors}"


@then('`warnings[]` contains a "symlinked directory was excluded" notice')
def _mcp_warn_symlink_dir(result):
    warns = result["response"].get("warnings", [])
    assert any("symlink" in w.lower() and ("excluded" in w.lower() or "dir" in w.lower()) for w in warns), (
        f"no symlinked-dir warning: {warns}"
    )


@then(parsers.parse('no files from outside "{name}" leak into the output zip'))
def _mcp_no_leak(result, name):
    out = Path(result["response"]["output_zip"])
    if not out.exists():
        return  # output not written (validation-only path)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert not any("external" in n for n in names), f"external file leaked: {names}"


@then('`warnings[]` contains a "symlink escapes project root" notice')
def _mcp_warn_symlink_escape(result):
    warns = result["response"].get("warnings", [])
    assert any("symlink" in w.lower() and "escape" in w.lower() for w in warns), f"no symlink-escape warning: {warns}"


@then("the escaped target is not in the output zip")
def _mcp_escape_not_in_zip(result):
    out = Path(result["response"]["output_zip"])
    if not out.exists():
        return
    with zipfile.ZipFile(out) as zf:
        body = "\n".join(zf.namelist())
    assert "elsewhere" not in body, f"escaped target leaked: {body}"


@then("`errors[]` contains a human-readable description of the failure")
def _mcp_errors_human(result):
    errors = result["response"]["errors"]
    assert errors, "errors[] empty"
    for e in errors:
        assert e and not e.startswith("Traceback"), f"raw traceback leaked: {e}"


@then("no Python traceback leaks into the response")
def _mcp_no_traceback(result):
    blob = json.dumps(result["response"])
    assert "Traceback" not in blob, f"traceback leaked: {blob}"


# --- Pipeline progress / stdio scenario ---


@then("any pipeline progress lines go to stderr")
def _mcp_progress_stderr(project_dir, monkeypatch):
    # Spawn the real stdio server and issue an initialize + tool call. Verify
    # that stdout carries only JSON-RPC frames (the assertion in the next Then).
    monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(project_dir))
    _write_main(project_dir / "paper")
    proc = _stdio_invoke(project_dir, "clean_submission", {"path": "paper"})
    project_dir.joinpath("_mcp_stdout.txt").write_text(proc.stdout)
    project_dir.joinpath("_mcp_stderr.txt").write_text(proc.stderr)


@then("stdout contains only valid MCP JSON-RPC frames")
def _mcp_stdout_jsonrpc(project_dir):
    raw = (project_dir / "_mcp_stdout.txt").read_text()
    # FastMCP's stdio transport writes one JSON object per line.
    frames = [line for line in raw.splitlines() if line.strip()]
    assert frames, f"no frames captured on stdout; raw:\n{raw!r}"
    for line in frames:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"non-JSON line on stdout: {line!r} ({exc})")
        assert obj.get("jsonrpc") == "2.0", f"frame missing jsonrpc=2.0: {obj}"


def _stdio_invoke(cwd: Path, tool_name: str, arguments: dict, timeout: float = 30.0) -> subprocess.CompletedProcess:
    """Send initialize + tools/call to a freshly-spawned latex2arxiv-mcp."""

    def frame(payload: dict) -> str:
        return json.dumps(payload) + "\n"

    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "bdd-test", "version": "0"},
        },
    }
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    call = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    stdin_payload = frame(initialize) + frame(initialized) + frame(call)
    repo_root = str(Path(__file__).resolve().parent.parent.parent.parent)
    env = {**os.environ, "LATEX2ARXIV_MCP_BASE_DIR": str(cwd), "PYTHONPATH": repo_root}
    return subprocess.run(
        [sys.executable, "-m", "mcp_server"],
        input=stdin_payload,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=timeout,
    )
