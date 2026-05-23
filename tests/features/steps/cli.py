"""CLI-surface steps: invoke converter.py as a subprocess and inspect outputs."""

from __future__ import annotations

import shlex
import subprocess
import sys

from pytest_bdd import given, parsers, then, when

import common


@given("the project triggers a `[warn]` (e.g. `\\today` in `\\date`)")
def _add_warn(project_dir, tex_content):
    tex_content["body"] = tex_content["body"].replace(
        "\\begin{document}",
        "\\date{\\today}\n\\begin{document}",
    )
    common.build_paper_zip(project_dir, tex_content["body"])


@given("the project triggers an `[error]` (e.g. `\\usepackage{minted}`)")
def _add_error(project_dir, tex_content):
    tex_content["body"] = tex_content["body"].replace(
        "\\documentclass{article}",
        "\\documentclass{article}\n\\usepackage{minted}",
    )
    common.build_paper_zip(project_dir, tex_content["body"])


@given("a project that triggers no errors and no warnings")
def _clean(project_dir, tex_content):
    common.build_paper_zip(project_dir, tex_content["body"])


@when(parsers.parse("I run `latex2arxiv paper.zip {args}`"))
def _run_cli(project_dir, result, args):
    cmd = [sys.executable, str(common.CONVERTER), "paper.zip", *shlex.split(args)]
    proc = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True)
    result["stdout"] = proc.stdout
    result["stderr"] = proc.stderr
    result["rc"] = proc.returncode


@then(parsers.parse('no "{name}" file is created'))
def _no_output(project_dir, name):
    assert not (project_dir / name).exists(), f"unexpected file written: {name}"


@then("no intermediate files are left on disk")
def _no_leftovers(project_dir):
    remaining = {p.name for p in project_dir.iterdir()}
    assert remaining == {"paper.zip", "src"}, remaining


@then(parsers.parse('the input "{name}" is unchanged'))
def _input_unchanged(project_dir, name):
    assert (project_dir / name).exists()


@then(parsers.parse("{stream:w} summarises files that would be removed"))
def _stream_removed(result, stream):
    s = result[stream]
    assert "remove" in s.lower() or "removed" in s.lower() or "Summary" in s


@then(parsers.parse("{stream:w} summarises files that would be kept"))
def _stream_kept(result, stream):
    s = result[stream]
    assert "kept" in s.lower() or "Summary" in s


@then(parsers.parse('{stream:w} contains a "{snippet}" style notice'))
def _stream_notice(result, stream, snippet):
    assert snippet in result[stream], f"missing notice {snippet!r} in {stream}; got:\n{result[stream]}"


@then(parsers.parse("both the warning and the error are emitted on {stream:w}"))
def _both_emitted(result, stream):
    assert "[warn]" in result[stream], result[stream]
    assert "[error]" in result[stream], result[stream]


@then(parsers.parse("the process exits with code {code:d} because of the error"))
def _exit_code_error(result, code):
    assert result["rc"] == code, (result["rc"], result["stderr"])


@then(parsers.parse("the process exits with code {code:d}"))
def _exit_code(result, code):
    assert result["rc"] == code, (result["rc"], result["stderr"])


@then("stdout is a single JSON object")
def _stdout_json(result):
    common.parse_json(result["stdout"])


@then(parsers.parse("the field `{field}` is `{literal}`"))
def _field_literal(result, field, literal):
    obj = common.parse_json(result["stdout"])
    actual = common.lookup_field(obj, field)
    expected = common.coerce_literal(literal)
    assert actual == expected, f"{field}: got {actual!r}, expected {expected!r}"
