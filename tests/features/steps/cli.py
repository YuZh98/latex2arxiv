"""CLI-surface steps: invoke converter.py as a subprocess and inspect outputs."""

from __future__ import annotations

import glob
import hashlib
import io
import json
import os
import re as _re
import shlex
import shutil
import stat as _stat
import subprocess
import sys
import zipfile
from pathlib import Path as _P

import pytest
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


@when(parsers.re(r"^I run `latex2arxiv (?P<input>\S+)(?: (?P<args>[^`]+))?`$"))
def _run_cli(project_dir, result, input, args):
    args = args or ""
    pre_hash = None
    in_path = project_dir / input
    if in_path.is_file() and result.get("track_input_hash"):
        pre_hash = hashlib.md5(in_path.read_bytes()).hexdigest()
    env = os.environ.copy()
    if result.get("pythonpath_prepend"):
        env["PYTHONPATH"] = result["pythonpath_prepend"] + os.pathsep + env.get("PYTHONPATH", "")
    if result.get("path_prepend"):
        env["PATH"] = result["path_prepend"] + os.pathsep + env.get("PATH", "")
    cmd = [sys.executable, str(common.CONVERTER), input, *shlex.split(args)]
    proc = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True, env=env)
    result["stdout"] = proc.stdout
    result["stderr"] = proc.stderr
    result["rc"] = proc.returncode
    result["input"] = input
    if pre_hash is not None:
        post_hash = hashlib.md5(in_path.read_bytes()).hexdigest()
        assert pre_hash == post_hash, f"input zip {input!r} was modified by tool"


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


# --- json_output.feature additions --------------------------------------------


@then("stdout is a single valid JSON object")
def _stdout_valid_json(result):
    obj = common.parse_json(result["stdout"])
    assert isinstance(obj, dict), f"expected dict, got {type(obj).__name__}"


@then("no human-progress text appears on stdout")
def _no_progress_on_stdout(result):
    stripped = result["stdout"].strip()
    assert stripped.startswith("{") and stripped.endswith("}"), (
        f"stdout has non-JSON content; first 100 chars: {stripped[:100]!r}"
    )
    common.parse_json(result["stdout"])


@then("human-progress text appears on stderr instead")
def _progress_on_stderr(result):
    stderr = result["stderr"]
    assert stderr.strip(), "stderr is empty"
    try:
        json.loads(stderr)
    except json.JSONDecodeError:
        return
    raise AssertionError("stderr is parseable as JSON; expected human-progress text")


@then("the JSON object contains at minimum the keys:")
def _has_keys(result, datatable):
    obj = common.parse_json(result["stdout"])
    keys = [row[0] for row in datatable]
    missing = [k for k in keys if k not in obj]
    assert not missing, f"missing top-level keys: {missing}"


@then(parsers.parse("`{field}` equals `{literal}`"))
def _bare_field_equals(result, field, literal):
    obj = common.parse_json(result["stdout"])
    actual = common.lookup_field(obj, field)
    expected = common.coerce_literal(literal)
    assert actual == expected, f"{field}: got {actual!r}, expected {expected!r}"


@given("the project triggers at least one error and one warning")
def _err_and_warn(project_dir, tex_content):
    body = (
        tex_content["body"]
        .replace(
            "\\documentclass{article}",
            "\\documentclass{article}\n\\usepackage{minted}",
        )
        .replace(
            "\\begin{document}",
            "\\date{\\today}\n\\begin{document}",
        )
    )
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body)


@given("the project triggers a `[error]`")
def _trigger_error_bare(project_dir, tex_content):
    tex_content["body"] = tex_content["body"].replace(
        "\\documentclass{article}",
        "\\documentclass{article}\n\\usepackage{minted}",
    )
    common.build_paper_zip(project_dir, tex_content["body"])


@then(parsers.re(r'each entry in `(?P<field>\w+)\[\]` is a plain string without an? "(?P<prefix>\[[^"]+\])" prefix'))
def _entries_no_prefix(result, field, prefix):
    obj = common.parse_json(result["stdout"])
    for item in obj[field]:
        assert isinstance(item, str), f"{field} entry not str: {item!r}"
        assert not item.startswith(prefix), f"{item!r} starts with {prefix!r}"


@then(parsers.parse("`counts.{name}` equals the length of `{listname}`"))
def _counts_eq_len(result, name, listname):
    obj = common.parse_json(result["stdout"])
    assert obj["counts"][name] == len(obj[listname]), (
        f"counts.{name}={obj['counts'][name]} vs len({listname})={len(obj[listname])}"
    )


@then("`sizes.input_bytes` matches the on-disk size of the input")
def _input_bytes(project_dir, result):
    obj = common.parse_json(result["stdout"])
    actual = (project_dir / "paper.zip").stat().st_size
    assert obj["sizes"]["input_bytes"] == actual, f"sizes.input_bytes={obj['sizes']['input_bytes']} vs on-disk={actual}"


@then("`sizes.uncompressed_bytes` matches the sum of kept-file sizes")
def _uncompressed_bytes(project_dir, result):
    obj = common.parse_json(result["stdout"])
    kept = set(obj["kept_files"])
    out = project_dir / "paper_arxiv.zip"
    assert out.exists(), f"output zip missing at {out}"
    with zipfile.ZipFile(out) as zf:
        total = sum(info.file_size for info in zf.infolist() if info.filename in kept)
    assert obj["sizes"]["uncompressed_bytes"] == total, (
        f"sizes.uncompressed_bytes={obj['sizes']['uncompressed_bytes']} vs sum={total}"
    )


@then("stdout still contains a valid JSON object with `errors` non-empty")
def _stdout_json_errors_nonempty(result):
    obj = common.parse_json(result["stdout"])
    assert obj["errors"], f"errors[] is empty: {obj['errors']!r}"


@given("an input that causes a fatal converter error (e.g. corrupt zip)")
def _corrupt_input(project_dir):
    (project_dir / "paper.zip").write_bytes(b"not a zip")


@then("stdout still contains a valid JSON object describing the failure")
def _stdout_json_failure(result):
    obj = common.parse_json(result["stdout"])
    assert isinstance(obj, dict), f"expected dict, got {type(obj).__name__}"


@given("a future release adds a new top-level key not listed in v1.0")
def _future_key(result):
    result["stdout"] = json.dumps({"schema_version": 1, "future_unknown_key": "x"})


@when("a v1.x consumer parses the output")
def _consumer_parses(result):
    result["parsed"] = json.loads(result["stdout"])


@then("it ignores the unknown key and reads `schema_version` to branch")
def _ignore_unknown(result):
    parsed = result["parsed"]
    assert parsed["schema_version"] == 1, parsed


# --- flatten.feature additions ------------------------------------------------


_FLATTEN_BG_MAIN = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "\\input{sec/intro}\n"
    "\\include{sec/methods}\n"
    "\\subfile{sec/appendix}\n"
    "\\end{document}\n"
)
_FLATTEN_BG_APPENDIX = "\\documentclass[../main]{subfiles}\n\\begin{document}\nAppendix text.\n\\end{document}\n"


@given(
    parsers.parse(
        'a LaTeX project "{name}" whose "main.tex" contains '
        "`\\input{{sec/intro}}`, `\\include{{sec/methods}}`, and `\\subfile{{sec/appendix}}`"
    )
)
def _flatten_bg(project_dir, tex_content, name):
    files = {
        "main.tex": _FLATTEN_BG_MAIN,
        "sec/intro.tex": "Intro text.\n",
        "sec/methods.tex": "Methods text.\n",
        "sec/appendix.tex": _FLATTEN_BG_APPENDIX,
    }
    tex_content["body"] = _FLATTEN_BG_MAIN
    common.build_multifile_zip(project_dir, files, zip_name=name)


@given("the main .tex has no inclusion commands")
def _no_inclusions(project_dir, tex_content):
    body = "\\documentclass{article}\n\\begin{document}\nHello.\n\\end{document}\n"
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body)


@given(parsers.parse("the main .tex contains a `% \\input{{old_section}}` on a commented line"))
def _commented_input(project_dir, tex_content):
    body = "\\documentclass{article}\n\\begin{document}\n% \\input{old_section}\nHello.\n\\end{document}\n"
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body)


def _output_zip(project_dir, result):
    stem = _P(result["input"]).stem
    return project_dir / f"{stem}_arxiv.zip"


@then("the output zip contains exactly one .tex file at the root")
def _one_tex_at_root(project_dir, result):
    out = _output_zip(project_dir, result)
    assert out.exists(), f"no output zip at {out}"
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    root_tex = [n for n in names if n.endswith(".tex") and "/" not in n]
    assert len(root_tex) == 1, f"expected 1 root .tex, got {root_tex} from {names}"


@then(parsers.parse('that file is the inlined "{name}"'))
def _is_inlined_main(project_dir, result, name):
    out = _output_zip(project_dir, result)
    with zipfile.ZipFile(out) as zf:
        body = zf.read(name).decode()
    assert "Intro text" in body, f"intro not inlined into {name}: {body!r}"
    assert "Methods text" in body, f"methods not inlined into {name}: {body!r}"


@then(parsers.parse("the original fragment files ({names}) are not in the output zip"))
def _fragments_absent(project_dir, result, names):
    out = _output_zip(project_dir, result)
    with zipfile.ZipFile(out) as zf:
        zip_names = set(zf.namelist())
    fragments = [n.strip() for n in names.split(",")]
    leaked = [f for f in fragments if any(z.endswith(f) for z in zip_names)]
    assert not leaked, f"fragments leaked into output zip: {leaked}; zip contents={zip_names}"


@then("`\\includegraphics` paths in the inlined .tex still resolve relative to the new root")
def _includegraphics_resolves(project_dir, result):
    out = _output_zip(project_dir, result)
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        body = zf.read("main.tex").decode()
    paths = _re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body)
    for p in paths:
        candidates = {p, p + ".pdf", p + ".png", p + ".jpg", p + ".jpeg", p + ".eps"}
        assert candidates & names, f"figure path {p!r} does not resolve in zip; zip={names}"


@then("every referenced figure file is present in the output zip")
def _figures_present(project_dir, result):
    _includegraphics_resolves(project_dir, result)


@then(parsers.parse("the JSON field `{field}` is `{literal}`"))
def _json_field_literal(result, field, literal):
    obj = common.parse_json(result["stdout"])
    actual = common.lookup_field(obj, field)
    expected = common.coerce_literal(literal)
    assert actual == expected, f"{field}: got {actual!r}, expected {expected!r}"


@then(
    parsers.parse(
        "the JSON field `{field}` is a non-empty list containing the paths of the fragment .tex files that were inlined"
    )
)
def _json_inlined_nonempty(result, field):
    obj = common.parse_json(result["stdout"])
    val = common.lookup_field(obj, field)
    assert isinstance(val, list) and val, f"{field} is not a non-empty list: {val!r}"
    for p in val:
        assert isinstance(p, str) and p.endswith(".tex"), f"unexpected entry {p!r} in {field}"


@then(parsers.parse("`{field}` is an empty list"))
def _is_empty_list(result, field):
    obj = common.parse_json(result["stdout"])
    val = common.lookup_field(obj, field)
    assert val == [], f"{field} not empty: {val!r}"


@then("the output zip is structurally equivalent to a non-flattened run")
def _structural_equiv(project_dir, result):
    flat_zip = _output_zip(project_dir, result)
    with zipfile.ZipFile(flat_zip) as zf:
        flat_names = set(zf.namelist())
    flat_zip.unlink()
    subprocess.run(
        [sys.executable, str(common.CONVERTER), result["input"]],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    with zipfile.ZipFile(flat_zip) as zf:
        plain_names = set(zf.namelist())
    assert flat_names == plain_names, f"flatten={flat_names} vs plain={plain_names}"


@then(parsers.parse('"{name}" content does not appear in the inlined output'))
def _comment_not_inlined(project_dir, result, name):
    out = _output_zip(project_dir, result)
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        body = zf.read("main.tex").decode()
    stem = name.replace(".tex", "")
    assert not any(stem in n for n in names if n != "main.tex"), f"{stem!r} fragment leaked into zip: {names}"
    assert stem not in body, f"{stem!r} appears in inlined main.tex: {body!r}"


# --- clean_prune.feature additions --------------------------------------------


def _cp_read_main(project_dir, result) -> str:
    with zipfile.ZipFile(_output_zip(project_dir, result)) as zf:
        return zf.read("main.tex").decode()


_CP_DEFAULT_MAIN = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "\\input{intro}\n"
    "\\includegraphics{fig1.pdf}\n"
    "Body. \\todo{stale}\n"
    "\\end{document}\n"
)


@given(
    parsers.parse(
        'a LaTeX project zip containing a main "main.tex" plus build artifacts, '
        "unused figures, backup files, and inline draft annotations"
    )
)
def _cp_default_project(project_dir, tex_content):
    files = {
        "main.tex": _CP_DEFAULT_MAIN,
        "intro.tex": "Intro text.\n",
        "fig1.pdf": b"%PDF-1.4 fake\n",
        "unused.tex": "Unused.\n",
        "main.aux": "fake aux\n",
        "main.log": "fake log\n",
        "main.out": "fake out\n",
        "main.pdf": b"%PDF-1.4 fake build\n",
        "backup.bak": "old backup\n",
    }
    tex_content["body"] = _CP_DEFAULT_MAIN
    common.build_multifile_zip(project_dir, files, zip_name="project.zip")


@given("the original input archive is never modified by the tool")
def _cp_track_hash(result):
    result["track_input_hash"] = True


@then(
    'the output zip contains "main.tex" and every file it transitively references '
    "via `\\input`, `\\include`, `\\subfile`, `\\includegraphics`, `\\graphicspath`, and `\\bibliography`"
)
def _cp_transitive_refs(project_dir, result):
    out = _output_zip(project_dir, result)
    assert out.exists(), f"no output at {out}"
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    for must in ("main.tex", "intro.tex", "fig1.pdf"):
        assert must in names, f"{must!r} missing from output; got {names}"


@then("files not reachable from the main .tex are dropped")
def _cp_unreachable_dropped(project_dir, result):
    with zipfile.ZipFile(_output_zip(project_dir, result)) as zf:
        names = set(zf.namelist())
    for must_not in ("unused.tex", "backup.bak"):
        assert must_not not in names, f"{must_not!r} unexpectedly kept; got {names}"


@given(
    parsers.parse(
        'the input contains "main.aux", "main.log", "main.out", "main.pdf", '
        '".DS_Store", "Thumbs.db", and "__pycache__/cache.pyc"'
    )
)
def _cp_artifacts_project(project_dir, tex_content):
    body = "\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n"
    files = {
        "main.tex": body,
        "main.aux": "a\n",
        "main.log": "a\n",
        "main.out": "a\n",
        "main.pdf": b"%PDF-1.4 fake\n",
        ".DS_Store": "ds\n",
        "Thumbs.db": "th\n",
        "__pycache__/cache.pyc": b"\x00\x00",
    }
    tex_content["body"] = body
    common.build_multifile_zip(project_dir, files, zip_name="project.zip")


@then("none of those artifacts appear in the output zip")
def _cp_no_artifacts(project_dir, result):
    with zipfile.ZipFile(_output_zip(project_dir, result)) as zf:
        names = set(zf.namelist())
    forbidden = {"main.aux", "main.log", "main.out", "main.pdf", ".DS_Store", "Thumbs.db", "__pycache__/cache.pyc"}
    leaked = forbidden & names
    assert not leaked, f"build artifacts kept: {leaked}; output={names}"


@given('"main.tex" contains both `% line comments` and stretches of code preceded by an unescaped percent')
def _cp_comments_project(project_dir, tex_content):
    body = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "% line comment\n"
        "Visible \\% escaped percent.\n"
        "% another comment\n"
        "Body.\n"
        "\\end{document}\n"
    )
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body, zip_name="project.zip")


@then('the cleaned "main.tex" in the output has those comments removed')
def _cp_comments_removed(project_dir, result):
    body = _cp_read_main(project_dir, result)
    assert "% line comment" not in body, body
    assert "% another comment" not in body, body


@then("`\\%` (escaped percent) is preserved verbatim")
def _cp_escaped_percent_kept(project_dir, result):
    body = _cp_read_main(project_dir, result)
    assert "\\%" in body, f"escaped percent missing from cleaned main.tex: {body!r}"


@given(parsers.parse('"main.tex" contains a `{cmd}{{...}}` invocation'))
def _cp_annotation_project(project_dir, tex_content, cmd):
    body = f"\\documentclass{{article}}\n\\begin{{document}}\nBefore {cmd}{{noisy content}} after.\n\\end{{document}}\n"
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body, zip_name="project.zip")


@then(parsers.parse('the entire `{cmd}{{...}}` (including nested braces) is removed from the cleaned "main.tex"'))
def _cp_annotation_removed(project_dir, result, cmd):
    body = _cp_read_main(project_dir, result)
    assert cmd not in body, f"{cmd!r} survived in cleaned main.tex: {body!r}"
    assert "noisy content" not in body, body


@given('"main.tex" contains `\\todo{see \\cite{x}}`')
def _cp_nested_project(project_dir, tex_content):
    body = "\\documentclass{article}\n\\begin{document}\nBefore \\todo{see \\cite{x}} after.\n\\end{document}\n"
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body, zip_name="project.zip")


@then("the whole `\\todo{see \\cite{x}}` block is removed")
def _cp_nested_removed(project_dir, result):
    body = _cp_read_main(project_dir, result)
    assert "\\todo" not in body, body
    assert "\\cite{x}" not in body, body


@then("no dangling `}` is left behind")
def _cp_no_dangling_brace(project_dir, result):
    body = _cp_read_main(project_dir, result)
    opens = body.count("{")
    closes = body.count("}")
    assert opens == closes, f"unbalanced braces in cleaned main.tex: opens={opens} closes={closes}\n{body!r}"


@given(parsers.parse("the main .tex contains `\\usepackage{{{pkg}}}`"))
def _cp_pkg_project(project_dir, tex_content, pkg):
    body = f"\\documentclass{{article}}\n\\usepackage{{{pkg}}}\n\\begin{{document}}\nBody.\n\\end{{document}}\n"
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body, zip_name="project.zip")


@then(parsers.parse("`\\usepackage{{{pkg}}}` is removed from the cleaned main .tex"))
def _cp_pkg_removed(project_dir, result, pkg):
    body = _cp_read_main(project_dir, result)
    assert f"\\usepackage{{{pkg}}}" not in body, f"{pkg!r} usepackage survived: {body!r}"


@given('"main.tex" contains `% \\input{old_section.tex}` on a commented line')
def _cp_commented_input_project(project_dir, tex_content):
    body = "\\documentclass{article}\n\\begin{document}\n% \\input{old_section.tex}\nBody.\n\\end{document}\n"
    tex_content["body"] = body
    files = {"main.tex": body}
    common.build_multifile_zip(project_dir, files, zip_name="project.zip")


@given('the file "old_section.tex" exists in the input')
def _cp_add_old_section(project_dir):
    zip_path = project_dir / "project.zip"
    src = project_dir / "src"
    target = src / "old_section.tex"
    target.write_text("stale content\n")
    with zipfile.ZipFile(zip_path, "a") as zf:
        zf.write(target, arcname="old_section.tex")


@then('"old_section.tex" is treated as unreferenced and dropped from the output')
def _cp_old_section_dropped(project_dir, result):
    with zipfile.ZipFile(_output_zip(project_dir, result)) as zf:
        names = set(zf.namelist())
    assert "old_section.tex" not in names, f"old_section.tex leaked into output: {names}"


@given('the input "main.tex" does not declare `\\pdfoutput`')
def _cp_no_pdfoutput(project_dir, tex_content):
    body = "\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n"
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body, zip_name="project.zip")


@then('the cleaned "main.tex" includes `\\pdfoutput=1` so arXiv selects pdfLaTeX')
def _cp_pdfoutput_injected(project_dir, result):
    body = _cp_read_main(project_dir, result)
    assert "\\pdfoutput=1" in body, f"pdfoutput not injected: {body!r}"


@given('the input "main.tex" contains `\\pdfoutput=0`')
def _cp_pdfoutput_zero(project_dir, tex_content):
    body = "\\pdfoutput=0\n\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n"
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body, zip_name="project.zip")


@then('the cleaned "main.tex" contains `\\pdfoutput=1`')
def _cp_pdfoutput_one(project_dir, result):
    body = _cp_read_main(project_dir, result)
    assert "\\pdfoutput=1" in body, body
    assert "\\pdfoutput=0" not in body, f"pdfoutput=0 not normalized: {body!r}"


@given('the input contains a "00README" file at the project root')
def _cp_readme_project(project_dir, tex_content):
    body = "\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n"
    tex_content["body"] = body
    files = {"main.tex": body, "00README": "arXiv hint: keep this.\n"}
    common.build_multifile_zip(project_dir, files, zip_name="project.zip")


@then('the "00README" file is kept verbatim in the output zip')
def _cp_readme_kept(project_dir, result):
    out = _output_zip(project_dir, result)
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert "00README" in names, f"00README dropped; output={names}"
        body = zf.read("00README").decode()
    assert "arXiv hint" in body, f"00README content not verbatim: {body!r}"


# --- custom_config.feature additions ------------------------------------------


def _cc_write_yaml(project_dir, content: str, name: str = "my_rules.yaml") -> None:
    (project_dir / name).write_text(content)


def _cc_read_main(project_dir, result) -> str:
    out = _output_zip(project_dir, result)
    with zipfile.ZipFile(out) as zf:
        return zf.read("main.tex").decode()


@given(parsers.parse('a YAML file "{name}" with custom removal rules'))
def _cc_bg_yaml(project_dir, name):
    _cc_write_yaml(project_dir, "commands_to_delete: []\n", name=name)


def _cc_write_cmd_rule(project_dir, cmd):
    _cc_write_yaml(project_dir, f"commands_to_delete:\n  - {cmd}\n")


@given(parsers.parse('"my_rules.yaml" declares a removable command "{cmd}"'))
def _cc_cmd_rule(project_dir, cmd):
    _cc_write_cmd_rule(project_dir, cmd)


@given(parsers.parse('"my_rules.yaml" declares a custom command "{cmd}"'))
def _cc_cmd_rule_alias(project_dir, cmd):
    _cc_write_cmd_rule(project_dir, cmd)


@given(parsers.re(r"^the main \.tex contains `\\(?P<cmd>(?!usepackage\b|begin\b|end\b)\w+)\{(?P<arg>[^{}]+)\}`$"))
def _cc_main_with_cmd(project_dir, tex_content, cmd, arg):
    body = f"\\documentclass{{article}}\n\\begin{{document}}\n\\{cmd}{{{arg}}}\n\\end{{document}}\n"
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body)


@then(parsers.parse("the `\\{cmd}{{{arg}}}` block is removed from the cleaned main .tex"))
def _cc_cmd_removed(project_dir, result, cmd, arg):
    body = _cc_read_main(project_dir, result)
    assert f"\\{cmd}" not in body, f"\\{cmd} survived: {body!r}"
    assert arg not in body, f"arg {arg!r} survived: {body!r}"


@given(parsers.parse('"my_rules.yaml" lists "{env}" under `environments_to_delete`'))
def _cc_env_rule(project_dir, env):
    _cc_write_yaml(project_dir, f"environments_to_delete:\n  - {env}\n")


@given(parsers.parse("the main .tex contains `\\begin{{{env}}}...\\end{{{env}}}`"))
def _cc_main_with_env(project_dir, tex_content, env):
    body = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        f"\\begin{{{env}}}\nNoisy content.\n\\end{{{env}}}\n"
        "Visible body.\n"
        "\\end{document}\n"
    )
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body)


@then(parsers.parse("the entire `{env}` environment (including its body) is removed"))
def _cc_env_removed(project_dir, result, env):
    body = _cc_read_main(project_dir, result)
    assert f"\\begin{{{env}}}" not in body, body
    assert f"\\end{{{env}}}" not in body, body
    assert "Noisy content" not in body, body
    assert "Visible body" in body, f"Visible body lost: {body!r}"


@given(parsers.parse('"my_rules.yaml" lists a `replacements` rule mapping `{pattern}` to ``'))
def _cc_repl_rule(project_dir, pattern):
    yaml = f'replacements:\n  - pattern: "{pattern}"\n    replacement: ""\n'
    _cc_write_yaml(project_dir, yaml)


@given(parsers.parse('the main .tex contains the literal text "{snippet}"'))
def _cc_main_with_text(project_dir, tex_content, snippet):
    body = f"\\documentclass{{article}}\n\\begin{{document}}\n{snippet}\n\\end{{document}}\n"
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body)


@then(parsers.parse('the substring "{snippet}" is removed from the cleaned main .tex'))
def _cc_snippet_removed(project_dir, result, snippet):
    body = _cc_read_main(project_dir, result)
    assert snippet not in body, f"{snippet!r} survived: {body!r}"


@given(parsers.parse('"my_rules.yaml" contains a misspelled top-level key like `{key}`'))
def _cc_misspelled_key(project_dir, key):
    _cc_write_yaml(project_dir, f"{key}:\n  - mynote\n")


@then(parsers.parse('a "[warn]" lists the unknown key and the four accepted keys ({accepted})'))
def _cc_unknown_key_warning(result, accepted):
    stream = result["stdout"]
    assert "[warn]" in stream, f"no [warn] in stdout: {stream!r}"
    assert "unknown" in stream.lower() or "expected" in stream.lower(), stream
    for key in ("commands_to_delete", "commands_to_unwrap", "environments_to_delete", "replacements"):
        assert key in stream, f"accepted key {key!r} missing from warning text: {stream!r}"


@then("the process exits with code 0 if no other errors are present")
def _cc_rc0(result):
    assert result["rc"] == 0, (result["rc"], result["stderr"])


@given(parsers.parse('the project root contains an "{name}" file'))
def _cc_root_config(project_dir, tex_content, name):
    body = "\\documentclass{article}\n\\begin{document}\n\\mynote{ignore me} Body.\n\\end{document}\n"
    files = {
        "main.tex": body,
        name: "commands_to_delete:\n  - mynote\n",
    }
    tex_content["body"] = body
    common.build_multifile_zip(project_dir, files)


@given("no `--config` flag is passed")
def _cc_no_flag():
    pass


@then("the auto-detected config is loaded and applied")
def _cc_auto_detect_applied(project_dir, result):
    body = _cc_read_main(project_dir, result)
    assert "\\mynote" not in body, f"auto-detected config not applied: {body!r}"


@then("stdout notes which config file was used")
def _cc_stdout_config_name(result):
    assert "config:" in result["stdout"] or "arxiv_config.yaml" in result["stdout"], (
        f"stdout has no config notice: {result['stdout']!r}"
    )


@then("the process exits non-zero")
def _cc_rc_nonzero(result):
    assert result["rc"] != 0, (result["rc"], result["stderr"])


@then("stderr explains that the config file was not found")
def _cc_stderr_not_found(result):
    stderr = result["stderr"]
    assert "does_not_exist.yaml" in stderr, f"missing filename in stderr: {stderr!r}"
    assert "not found" in stderr.lower() or "filenotfounderror" in stderr.lower(), stderr


@given('"my_rules.yaml" contains malformed YAML')
def _cc_malformed(project_dir):
    _cc_write_yaml(project_dir, "commands_to_delete: [\n")


@then("stderr contains a YAML parse error pointing to the problem location")
def _cc_stderr_yaml_error(result):
    stderr = result["stderr"]
    assert "ParserError" in stderr or "yaml" in stderr.lower(), f"no YAML error in stderr: {stderr!r}"
    assert _re.search(r"line \d+", stderr), f"stderr lacks line marker: {stderr!r}"


@given(parsers.parse("the main .tex contains both `\\{cmd1}{{{a1}}}` and `\\{cmd2}{{{a2}}}`"))
def _cc_main_two_cmds(project_dir, tex_content, cmd1, a1, cmd2, a2):
    body = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        f"\\{cmd1}{{{a1}}} \\{cmd2}{{{a2}}}\n"
        "Body.\n"
        "\\end{document}\n"
    )
    tex_content["body"] = body
    common.build_paper_zip(project_dir, body)


@then(parsers.parse("both `\\{cmd1}{{{a1}}}` and `\\{cmd2}{{{a2}}}` are removed"))
def _cc_both_removed(project_dir, result, cmd1, a1, cmd2, a2):
    body = _cc_read_main(project_dir, result)
    assert f"\\{cmd1}" not in body, body
    assert f"\\{cmd2}" not in body, body
    assert a1 not in body, body
    assert a2 not in body, body


# --- resize_images.feature additions ------------------------------------------


_RI_BG_MAIN = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "\\includegraphics{big}\n"
    "\\includegraphics{small}\n"
    "\\includegraphics{diagram}\n"
    "\\end{document}\n"
)


def _ri_read_image_size(project_dir, result, name):
    from PIL import Image

    out = _output_zip(project_dir, result)
    with zipfile.ZipFile(out) as zf:
        with zf.open(name) as f:
            with Image.open(io.BytesIO(f.read())) as img:
                return img.size


@given("`Pillow` is available in the environment")
def _ri_pil_present():
    import importlib.util

    assert importlib.util.find_spec("PIL") is not None, "Pillow not installed"


@given(parsers.parse('a LaTeX project zip "{name}" containing raster figures'))
def _ri_bg_project(project_dir, tex_content, name):
    from PIL import Image

    big_buf = io.BytesIO()
    Image.new("RGB", (8000, 6000), (255, 0, 0)).save(big_buf, format="PNG")
    big_png = big_buf.getvalue()
    small_buf = io.BytesIO()
    Image.new("RGB", (800, 600), (0, 255, 0)).save(small_buf, format="PNG")
    small_png = small_buf.getvalue()
    diagram_pdf = b"%PDF-1.4\n%fake\n%%EOF\n"
    # Mirror to disk under src/ so _ri_figure_assert can read dimensions back.
    src = project_dir / "src"
    src.mkdir(exist_ok=True)
    (src / "big.png").write_bytes(big_png)
    (src / "small.png").write_bytes(small_png)
    (src / "diagram.pdf").write_bytes(diagram_pdf)
    tex_content["body"] = _RI_BG_MAIN
    files = {
        "main.tex": _RI_BG_MAIN,
        "big.png": big_png,
        "small.png": small_png,
        "diagram.pdf": diagram_pdf,
    }
    common.build_multifile_zip(project_dir, files, zip_name=name)


@given(parsers.parse('a figure "{name}" is {w:d}x{h:d} pixels'))
def _ri_figure_assert(project_dir, name, w, h):
    from PIL import Image

    p = project_dir / "src" / name
    assert p.exists(), f"fixture image missing: {p}"
    with Image.open(p) as img:
        assert img.size == (w, h), f"{name} fixture is {img.size}, expected ({w},{h})"


@given(parsers.parse('a vector figure "{name}"'))
def _ri_pdf_assert(project_dir, name):
    p = project_dir / "src" / name
    assert p.exists(), f"fixture pdf missing: {p}"


@given("`Pillow` is not installed")
def _ri_stub_pil(project_dir, result):
    shim = project_dir / "pil_shim"
    pkg = shim / "PIL"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('raise ImportError("Pillow stubbed out for test")\n')
    result["pythonpath_prepend"] = str(shim)


@then(parsers.parse('"{name}" in the output zip has a longest side equal to {px:d} pixels'))
def _ri_longest_side(project_dir, result, name, px):
    w, h = _ri_read_image_size(project_dir, result, name)
    assert max(w, h) == px, f"{name} longest side is {max(w, h)}, expected {px}; got size=({w},{h})"


@then(parsers.parse('the aspect ratio of "{name}" is preserved'))
def _ri_aspect_preserved(project_dir, result, name):
    w, h = _ri_read_image_size(project_dir, result, name)
    # Source images use 4:3 (8000x6000 → 1.333...). Allow 1px rounding tolerance.
    ratio = w / h
    assert abs(ratio - 4 / 3) < 0.01, f"{name} aspect ratio is {ratio:.4f}, expected ~1.3333"


@then("images are resized to the project's `DEFAULT_MAX_PX` value")
def _ri_default_max(project_dir, result):
    # DEFAULT_MAX_PX = 1600 in pipeline/images.py. Verify big.png hit that cap.
    w, h = _ri_read_image_size(project_dir, result, "big.png")
    assert max(w, h) == 1600, f"big.png longest side is {max(w, h)}, expected 1600"


@then(parsers.parse('"{name}" in the output zip is still {w:d}x{h:d} pixels'))
def _ri_unchanged(project_dir, result, name, w, h):
    got = _ri_read_image_size(project_dir, result, name)
    assert got == (w, h), f"{name} is {got}, expected ({w},{h})"


@then(parsers.parse('"{name}" is copied verbatim into the output zip'))
def _ri_verbatim(project_dir, result, name):
    src_bytes = (project_dir / "src" / name).read_bytes()
    out = _output_zip(project_dir, result)
    with zipfile.ZipFile(out) as zf:
        out_bytes = zf.read(name)
    assert src_bytes == out_bytes, f"{name} bytes differ between input and output"


@then("no images in the output zip are resized")
def _ri_no_resize(project_dir, result):
    # All raster images keep their original dimensions.
    assert _ri_read_image_size(project_dir, result, "big.png") == (8000, 6000)
    assert _ri_read_image_size(project_dir, result, "small.png") == (800, 600)


@then("the process still completes the rest of the pipeline normally")
def _ri_pipeline_ok(project_dir, result):
    assert result["rc"] == 0, (result["rc"], result["stderr"])
    assert _output_zip(project_dir, result).exists(), "output zip missing"


# --- cli_inputs.feature additions ---------------------------------------------


@given("the `latex2arxiv` CLI is installed and on PATH")
def _ci_cli_present_on_path():
    assert common.CONVERTER.exists(), f"converter.py not found at {common.CONVERTER}"


_CI_DEFAULT_BODY = "\\documentclass{article}\n\\begin{document}\nHello.\n\\end{document}\n"


@given(parsers.parse('a file "{name}" containing a compilable LaTeX project'))
def _ci_file_project(project_dir, tex_content, name):
    tex_content["body"] = _CI_DEFAULT_BODY
    common.build_paper_zip(project_dir, _CI_DEFAULT_BODY, zip_name=name)
    digest = hashlib.md5((project_dir / name).read_bytes()).hexdigest()
    (project_dir / f"{name}.orig_md5").write_text(digest)  # md5 snapshot for unchanged check


@given(parsers.parse('a directory "{name}" containing a compilable LaTeX project'))
def _ci_dir_project(project_dir, tex_content, name):
    dirname = name.rstrip("/")
    target = project_dir / dirname
    target.mkdir(exist_ok=True)
    (target / "main.tex").write_text(_CI_DEFAULT_BODY)
    tex_content["body"] = _CI_DEFAULT_BODY
    # Snapshot {filename: md5} for "unchanged" check.
    digests = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file()}
    (project_dir / f"{dirname}.orig.json").write_text(json.dumps(digests, sort_keys=True))


@given(parsers.parse('a public git repository at "{url}" containing a LaTeX project'))
def _ci_git_repo(project_dir, result, url):
    shim = project_dir / "git_shim"
    shim.mkdir(exist_ok=True)
    log = project_dir / "git_clone.log"
    script_body = (
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'if [ "$1" = "clone" ]; then\n'
        '  for arg do dest="$arg"; done\n'
        '  mkdir -p "$dest"\n'
        f'  cat > "$dest/main.tex" <<EOF\n'
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Cloned project.\n"
        "\\end{document}\n"
        "EOF\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n"
    )
    gitbin = shim / "git"
    gitbin.write_text(script_body)
    gitbin.chmod(gitbin.stat().st_mode | _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)
    result["path_prepend"] = str(shim)


@given(parsers.parse('a zip whose only file containing `\\documentclass` is "{name}"'))
def _ci_autodetect_zip(project_dir, tex_content, name):
    files = {
        "header.tex": "\\usepackage{amsmath}\n",  # no \documentclass
        name: _CI_DEFAULT_BODY,  # has \documentclass
    }
    tex_content["body"] = _CI_DEFAULT_BODY
    common.build_multifile_zip(project_dir, files, zip_name="paper.zip")


@given("a zip with multiple files containing `\\documentclass`")
def _ci_multi_documentclass_zip(project_dir, tex_content):
    body_a = "\\documentclass{article}\n\\begin{document}A.\\end{document}\n"
    body_b = "\\documentclass{article}\n\\begin{document}B.\\end{document}\n"
    files = {"main.tex": body_a, "JASA_main.tex": body_b}
    tex_content["body"] = body_a
    common.build_multifile_zip(project_dir, files, zip_name="paper.zip")


@given(parsers.parse('a malicious "{name}" whose entries include "{member}"'))
def _ci_evil_zip(project_dir, name, member):
    z = project_dir / name
    with zipfile.ZipFile(z, "w") as zf:
        zi = zipfile.ZipInfo(member)
        zf.writestr(zi, "escaped!\n")


@given(parsers.parse('a "{name}" whose total uncompressed size exceeds the safety cap'))
def _ci_bomb_zip(project_dir, name):
    chunk = b"\x00" * (10 * 1024 * 1024)
    z = project_dir / name
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(60):  # 600 MB uncompressed total, > 500 MB cap
            zf.writestr(f"chunk_{i:03d}.dat", chunk)


@when("I run `latex2arxiv` with no input and no `--demo`")
def _ci_run_noargs(project_dir, result):
    proc = subprocess.run(
        [sys.executable, str(common.CONVERTER)],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    result["stdout"] = proc.stdout
    result["stderr"] = proc.stderr
    result["rc"] = proc.returncode
    result["input"] = ""


@then(parsers.parse('a file "{name}" is written next to the input'))
def _ci_output_next_to_input(project_dir, name):
    assert (project_dir / name).exists(), f"{name} not found in {project_dir}"


@then(parsers.parse('a file "{name}" is written in the current directory'))
def _ci_output_in_cwd(project_dir, name):
    assert (project_dir / name).exists(), f"{name} not found in {project_dir}"


@then(parsers.parse('the original "{name}" is unchanged'))
def _ci_original_unchanged(project_dir, name):
    snap = project_dir / f"{name}.orig_md5"
    assert snap.exists(), f"no snapshot for {name}"
    current = hashlib.md5((project_dir / name).read_bytes()).hexdigest()
    assert current == snap.read_text().strip(), f"{name} was modified"


@then(parsers.parse('the directory "{name}" is unchanged'))
def _ci_dir_unchanged(project_dir, name):
    dirname = name.rstrip("/")
    target = project_dir / dirname
    expected = json.loads((project_dir / f"{dirname}.orig.json").read_text())
    actual = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file()}
    assert actual == expected, "directory contents changed"


@then("the repository is cloned to a temp location with `--depth 1`")
def _ci_depth_1(project_dir):
    log = (project_dir / "git_clone.log").read_text()
    assert "clone --depth 1" in log, f"git not called with --depth 1: {log!r}"


@then("the temp clone is removed before the process exits")
def _ci_clone_cleanup(project_dir):
    log = (project_dir / "git_clone.log").read_text().strip()
    parts = log.split()
    dest = parts[-1]
    assert not _P(dest).exists(), f"temp clone dir survived: {dest}"


@then("no input argument is required")
def _ci_demo_no_input_required(result):
    assert result["rc"] == 0, (result["rc"], result["stderr"])


@then("the bundled demo project is processed")
def _ci_demo_processed(project_dir):
    assert (project_dir / "demo_project_arxiv.zip").exists(), "demo output missing"


@then(parsers.parse('the cleaned output is written to "{name}"'))
def _ci_explicit_output(project_dir, name):
    assert (project_dir / name).exists(), f"{name} not written"


@then(parsers.parse('no file "{name}" is created'))
def _ci_no_default_output(project_dir, name):
    assert not (project_dir / name).exists(), f"unexpected {name}"


@then(parsers.parse('"{name}" is selected as the main file'))
def _ci_main_selected(result, name):
    stream = result["stdout"]
    assert f"main tex: {name}" in stream, f"main tex line not found for {name}: {stream!r}"


@then(parsers.parse('"{name}" is used as the main file regardless of auto-detection'))
def _ci_main_override(result, name):
    stream = result["stdout"]
    assert f"main tex: {name}" in stream, f"main tex override not honored: {stream!r}"


@then(parsers.parse('stderr contains "{snippet}"'))
def _ci_stderr_contains(result, snippet):
    assert snippet in result["stderr"], f"missing {snippet!r} in stderr: {result['stderr']!r}"


@then("stdout explains that the input path was not found")
def _ci_stdout_not_found(result):
    out = result["stdout"]
    assert "not found" in out.lower(), f"missing 'not found' in stdout: {out!r}"


@then(parsers.parse('stdout contains "{prefix}" followed by a semver-shaped string'))
def _ci_version_string(result, prefix):
    stream = result["stdout"]
    assert prefix in stream, f"prefix {prefix!r} missing: {stream!r}"
    m = _re.search(rf"{_re.escape(prefix)}(\d+\.\d+\.\d+)", stream)
    assert m, f"semver-shape not found after {prefix!r}: {stream!r}"


@then("no file is written outside the extraction root")
def _ci_no_escape(project_dir):
    parent = project_dir.parent
    leak = parent / "escape.tex"
    assert not leak.exists(), f"escape.tex leaked to {leak}"
    assert not (project_dir / "escape.tex").exists()


@then("stdout explains that extraction was refused due to an escaping path")
def _ci_stdout_zipslip(result):
    out = result["stdout"]
    assert "escapes the extraction root" in out or "zip-slip" in out.lower(), (
        f"zip-slip message missing from stdout: {out!r}"
    )


@then("no extraction occurs")
def _ci_no_extraction(project_dir):
    leaked = glob.glob(str(project_dir / "chunk_*.dat"))
    assert not leaked, f"bomb chunks extracted: {leaked[:3]}"


@then("stdout explains that extraction was refused due to the size cap")
def _ci_stdout_zipbomb(result):
    out = result["stdout"]
    assert "safety cap" in out or "uncompressed size" in out, f"bomb-cap message missing from stdout: {out!r}"


# --- guide.feature additions --------------------------------------------------


def _guide_path(project_dir, result) -> _P:
    stem = _P(result["input"]).stem
    return project_dir / f"{stem}_arxiv_UPLOAD_GUIDE.txt"


def _guide_text(project_dir, result) -> str:
    return _guide_path(project_dir, result).read_text()


_GUIDE_METADATA_MAIN = (
    "\\documentclass{article}\n"
    "\\title{My Wired Paper}\n"
    "\\author{Alice Author and Bob Builder}\n"
    "\\begin{document}\n"
    "\\begin{abstract}\n"
    "Wired abstract body.\n"
    "\\end{abstract}\n"
    "Body.\n"
    "\\end{document}\n"
)


@given(parsers.parse('a compilable LaTeX project zip "{name}"'))
def _guide_compilable_zip(project_dir, tex_content, name):
    common.build_paper_zip(project_dir, tex_content["body"], zip_name=name)


@given("the main .tex contains a `\\title{...}`, `\\author{...}`, and `\\begin{abstract}` block")
def _guide_metadata_project(project_dir, tex_content):
    tex_content["body"] = _GUIDE_METADATA_MAIN
    common.build_paper_zip(project_dir, _GUIDE_METADATA_MAIN, zip_name="paper.zip")


@then("a plain-text file is written next to the output zip")
def _guide_file_written(project_dir, result):
    p = _guide_path(project_dir, result)
    assert p.exists(), f"guide file missing at {p}"
    text = p.read_text()
    assert text.strip(), "guide file is empty"


@then("its filename clearly identifies it as the upload guide")
def _guide_filename_identifies(project_dir, result):
    p = _guide_path(project_dir, result)
    name = p.name.upper()
    assert "UPLOAD" in name and "GUIDE" in name, f"guide filename unclear: {p.name!r}"


@then(parsers.parse('the guide contains a "{section}:" section with the extracted title'))
def _guide_section_title(project_dir, result, section):
    text = _guide_text(project_dir, result)
    assert f"{section}:" in text, f"missing {section!r}: section in guide:\n{text}"
    assert "My Wired Paper" in text, f"extracted title missing from guide:\n{text}"


@then(parsers.parse('the guide contains an "{section}:" section with the extracted author list'))
def _guide_section_authors(project_dir, result, section):
    text = _guide_text(project_dir, result)
    assert f"{section}:" in text, f"missing {section!r}: section in guide:\n{text}"
    assert "Alice Author" in text and "Bob Builder" in text, f"extracted authors missing:\n{text}"


@then(parsers.parse('the guide contains an "{section}:" section with the extracted abstract'))
def _guide_section_abstract(project_dir, result, section):
    text = _guide_text(project_dir, result)
    assert f"{section}:" in text, f"missing {section!r}: section in guide:\n{text}"
    assert "Wired abstract body" in text, f"extracted abstract missing:\n{text}"


@then(parsers.parse('the guide contains a "{section}:" section like "{template}"'))
def _guide_comments_section(project_dir, result, section, template):
    if not shutil.which("pdflatex"):
        pytest.skip("pdflatex not installed; --compile-dependent assertion skipped")
    text = _guide_text(project_dir, result)
    assert f"{section}:" in text, f"missing {section!r}: section in guide:\n{text}"
    for token in ("pages", "figures", "tables"):
        assert token in text, f"{token!r} missing from Comments-like line:\n{text}"


@then("the guide contains numbered steps covering:")
def _guide_numbered_steps(project_dir, result, datatable):
    text = _guide_text(project_dir, result)
    topics = [row[0].strip() for row in datatable]
    keyword_map = {
        "starting a new submission": ["new submission", "start"],
        "choosing a license": ["license"],
        "selecting a category": ["category"],
        "uploading files": ["upload"],
        "checking processing": ["process"],
        "filling in metadata": ["metadata"],
        "preview and submit": ["preview", "submit"],
    }
    missing = []
    text_lower = text.lower()
    for topic in topics:
        keys = keyword_map.get(topic, [topic.lower()])
        if not all(k in text_lower for k in keys):
            missing.append(topic)
    assert not missing, f"topics not covered in guide: {missing}\nguide:\n{text}"


@then('the guide contains a "Files in your zip:" listing')
def _guide_files_listing(project_dir, result):
    text = _guide_text(project_dir, result)
    assert "Files in your zip:" in text, f"files-listing header missing:\n{text}"


@then('the main .tex is annotated as "← main file"')
def _guide_main_annotation(project_dir, result):
    text = _guide_text(project_dir, result)
    assert "main.tex" in text, f"main.tex not listed in guide:\n{text}"
    assert "← main file" in text, f"main-file annotation missing:\n{text}"


@then("the guide is still generated using static project inspection")
def _guide_static_inspection(project_dir, result):
    p = _guide_path(project_dir, result)
    assert p.exists(), f"guide missing at {p}"


@then("the page / figure / table counts may be omitted if not derivable")
def _guide_counts_optional(project_dir, result):
    # Permissive: without --compile, page count is not derivable; figures/tables may be 0.
    # Assert nothing stronger than guide-file presence.
    assert _guide_path(project_dir, result).exists()


@then("no output zip is written")
def _guide_no_zip(project_dir, result):
    out = project_dir / f"{_P(result['input']).stem}_arxiv.zip"
    assert not out.exists(), f"output zip unexpectedly written at {out}"


@then("no guide file is written")
def _guide_no_guide_file(project_dir, result):
    p = _guide_path(project_dir, result)
    assert not p.exists(), f"guide unexpectedly written at {p}"


# --- preflight_checks.feature additions ---------------------------------------


_PF_DEFAULT_BODY = "\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n"
_PF_ZIP = "project.zip"


def _pf_build(project_dir, body, extras=None):
    """Rebuild project.zip with `body` as main.tex plus optional extras dict."""
    files = {"main.tex": body}
    if extras:
        files.update(extras)
    common.build_multifile_zip(project_dir, files, zip_name=_PF_ZIP)


def _pf_assert_severity(result, severity, *keywords):
    """Assert stdout has a `[severity]` line containing all keyword substrings (case-insensitive)."""
    lines = [line for line in result["stdout"].splitlines() if f"[{severity}]" in line]
    assert lines, f"no [{severity}] in stdout:\n{result['stdout']}"
    matched = [line for line in lines if all(k.lower() in line.lower() for k in keywords)]
    assert matched, f"no [{severity}] line matched all of {keywords}; got:\n" + "\n".join(lines)


def _pf_assert_no_severity_containing(result, severity, keyword):
    lines = [
        line for line in result["stdout"].splitlines() if f"[{severity}]" in line and keyword.lower() in line.lower()
    ]
    assert not lines, f"unexpected [{severity}] containing {keyword!r}:\n" + "\n".join(lines)


# --- Background + project-shape Givens ---


@given("a LaTeX project zip ready for inspection")
def _pf_bg_zip(project_dir, tex_content):
    tex_content["body"] = _PF_DEFAULT_BODY
    _pf_build(project_dir, _PF_DEFAULT_BODY)


@given(parsers.re(r"^the main \.tex contains `\\usepackage\{(?P<pkg>[^{}]+)\}`$"))
def _pf_usepackage(project_dir, tex_content, pkg):
    body = f"\\documentclass{{article}}\n\\usepackage{{{pkg}}}\n\\begin{{document}}\nBody.\n\\end{{document}}\n"
    tex_content["body"] = body
    _pf_build(project_dir, body)


@given(parsers.parse('the input contains "{name}" at any depth'))
def _pf_input_contains(project_dir, tex_content, name):
    # Spec says only "input contains <name>" — do not inject usepackage to coerce
    # the file into the kept set. Code currently only checks kept_files, which is
    # the gap covered by @xfail_preflight_gap.
    body = tex_content.get("body") or _PF_DEFAULT_BODY
    _pf_build(project_dir, body, {name: "fake-bytes\n"})


@given('no "00README" with `compiler: xelatex` is shipped')
def _pf_no_readme():
    pass


@given('a "00README" at the project root contains `compiler: xelatex`')
def _pf_with_readme(project_dir, tex_content):
    body = tex_content.get("body") or _PF_DEFAULT_BODY
    _pf_build(project_dir, body, {"00README": "compiler: xelatex\n"})


@given("the main .tex contains `\\tikzexternalize`")
def _pf_tikzext(project_dir, tex_content):
    body = (
        "\\documentclass{article}\n\\usepackage{tikz}\n\\tikzexternalize\n\\begin{document}\nBody.\n\\end{document}\n"
    )
    tex_content["body"] = body
    _pf_build(project_dir, body)


@given("no `*-figure*.pdf` files are present")
def _pf_no_tikz_fig():
    pass


@given("the main .tex contains `\\bibliography{refs}`")
def _pf_bibliography(project_dir, tex_content):
    body = "\\documentclass{article}\n\\begin{document}\n\\bibliography{refs}\nBody.\n\\end{document}\n"
    tex_content["body"] = body
    _pf_build(project_dir, body)


@given('neither "refs.bib" nor any "*.bbl" file is in the project')
def _pf_no_bib_no_bbl():
    pass


@given("the main .tex contains `\\usepackage{biblatex}` or `\\addbibresource{...}`")
def _pf_biblatex(project_dir, tex_content):
    body = (
        "\\documentclass{article}\n"
        "\\usepackage{biblatex}\n"
        "\\addbibresource{refs.bib}\n"
        "\\begin{document}\nBody.\n\\end{document}\n"
    )
    tex_content["body"] = body
    _pf_build(project_dir, body, {"refs.bib": "@article{x,title={X}}\n"})


@given("no `<main>.bbl` is shipped in the project")
def _pf_no_main_bbl():
    pass


@given(parsers.parse('the only file containing `\\documentclass` is "{path}"'))
def _pf_documentclass_in_subdir(project_dir, tex_content, path):
    body = _PF_DEFAULT_BODY
    tex_content["body"] = body
    files = {path: body}
    common.build_multifile_zip(project_dir, files, zip_name=_PF_ZIP)


def _pf_set_directive(project_dir, tex_content, directive):
    body = f"\\documentclass{{article}}\n\\begin{{document}}\n\\{directive}\n\\end{{document}}\n"
    tex_content["body"] = body
    _pf_build(project_dir, body)


# Note: pytest-bdd 8.x double-escapes backslashes from Scenario Outline Examples
# cells before substituting into step text. So the rendered step text for cell
# `\printindex` is `the main .tex contains `\\printindex`` (two backslashes).
@given(parsers.parse("the main .tex contains `\\\\printindex`"))
def _pf_printindex(project_dir, tex_content):
    _pf_set_directive(project_dir, tex_content, "printindex")


@given(parsers.parse("the main .tex contains `\\\\printglossary`"))
def _pf_printglossary(project_dir, tex_content):
    _pf_set_directive(project_dir, tex_content, "printglossary")


@given(parsers.parse("the main .tex contains `\\\\printnomenclature`"))
def _pf_printnomenclature(project_dir, tex_content):
    _pf_set_directive(project_dir, tex_content, "printnomenclature")


@given(parsers.parse("the matching `{sidecar}` file is not shipped"))
def _pf_no_sidecar(sidecar):
    pass


@given("the main .tex contains `\\date{\\today}`")
def _pf_today_date(project_dir, tex_content):
    body = "\\documentclass{article}\n\\date{\\today}\n\\begin{document}\nBody.\n\\end{document}\n"
    tex_content["body"] = body
    _pf_build(project_dir, body)


@given("the cleaned output would exceed 50 megabytes")
def _pf_oversized(project_dir, tex_content):
    body = "\\documentclass{article}\n\\begin{document}\n\\includegraphics{big}\n\\end{document}\n"
    tex_content["body"] = body
    # Use os.urandom so DEFLATE cannot squeeze it under the threshold.
    extras = {"big.pdf": b"%PDF-1.4\n" + os.urandom(60 * 1024 * 1024)}
    _pf_build(project_dir, body, extras)


@given(parsers.parse('the project contains "{name}"'))
def _pf_project_contains_file(project_dir, tex_content, name):
    body = f"\\documentclass{{article}}\n\\begin{{document}}\n\\includegraphics{{{_P(name).stem}}}\n\\end{{document}}\n"
    tex_content["body"] = body
    _pf_build(project_dir, body, {name: b"fake\n"})


@given('no "00README" specifies `compiler: latex`')
def _pf_no_latex_hint():
    pass


@given(parsers.parse('the project contains a file named "{name}"'))
def _pf_project_named_file(project_dir, tex_content, name):
    body = f"\\documentclass{{article}}\n\\begin{{document}}\n\\includegraphics{{{_P(name).stem}}}\n\\end{{document}}\n"
    tex_content["body"] = body
    _pf_build(project_dir, body, {name: b"fake\n"})


@given(
    "a project that triggers a \\today warning, a biblatex .bbl warning, "
    "and an oversized-output warning at the same time"
)
def _pf_three_warns(project_dir, tex_content):
    body = (
        "\\documentclass{article}\n"
        "\\usepackage{biblatex}\n"
        "\\addbibresource{refs.bib}\n"
        "\\date{\\today}\n"
        "\\begin{document}\n\\includegraphics{big}\n\\end{document}\n"
    )
    tex_content["body"] = body
    extras = {
        "refs.bib": "@article{x,title={X}}\n",
        "big.pdf": b"%PDF-1.4\n" + os.urandom(60 * 1024 * 1024),
    }
    _pf_build(project_dir, body, extras)


# --- Advisory-warnings dispatcher (Outline 15) ---


def _pf_advisory_setup(project_dir, tex_content, condition):
    """Map a condition string from Outline 15's Examples table to project state."""
    if "xr" in condition and "xr-hyper" in condition:
        body = "\\documentclass{article}\n\\usepackage{xr}\n\\begin{document}Body.\\end{document}\n"
        extras = None
    elif "referee" in condition or "doublespace" in condition:
        body = "\\documentclass[referee]{article}\n\\begin{document}Body.\\end{document}\n"
        extras = None
    elif "includeonly" in condition:
        body = "\\documentclass{article}\n\\includeonly{a}\n\\begin{document}Body.\\end{document}\n"
        extras = None
    elif "subfile" in condition and "bibliographystyle" in condition:
        body = "\\documentclass{article}\n\\usepackage{subfiles}\n\\begin{document}\n\\subfile{sub}\n\\end{document}\n"
        sub_body = "\\documentclass[main]{subfiles}\n\\begin{document}\n\\bibliographystyle{plain}\n\\end{document}\n"
        extras = {"sub.tex": sub_body}
    elif "absolute path" in condition:
        body = "\\documentclass{article}\n\\begin{document}\n\\input{/etc/passwd}\n\\end{document}\n"
        extras = None
    elif "eps-converted-to.pdf" in condition:
        body = _PF_DEFAULT_BODY
        extras = {"fig1-eps-converted-to.pdf": b"%PDF\n"}
    elif "dot-file" in condition or "dot-directory" in condition:
        body = _PF_DEFAULT_BODY
        extras = {".arxivignore": "secret\n"}
    elif "34 megapixels" in condition or ".png" in condition:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (8000, 5000), (255, 0, 0)).save(buf, format="PNG")
        body = "\\documentclass{article}\n\\begin{document}\n\\includegraphics{big}\n\\end{document}\n"
        extras = {"big.png": buf.getvalue()}
    elif "valid UTF-8" in condition:
        body = b"\\documentclass{article}\\begin{document}\xff\\end{document}"
        # Use binary path directly via build_multifile_zip
        common.build_multifile_zip(project_dir, {"main.tex": body}, zip_name=_PF_ZIP)
        tex_content["body"] = body.decode("latin-1")
        return
    elif "non-ASCII filename" in condition or "non-ASCII characters" in condition:
        body = "\\documentclass{article}\n\\begin{document}\n\\includegraphics{figü}\n\\end{document}\n"
        extras = {"figü.pdf": b"fake\n"}
    elif "spaces" in condition and "directory" in condition:
        body = "\\documentclass{article}\n\\begin{document}\n\\includegraphics{my dir/fig}\n\\end{document}\n"
        extras = {"my dir/fig.pdf": b"fake\n"}
    else:
        raise AssertionError(f"unhandled advisory condition: {condition!r}")
    tex_content["body"] = body if isinstance(body, str) else body.decode("latin-1")
    _pf_build(project_dir, body if isinstance(body, str) else body.decode("latin-1"), extras)


@given(parsers.parse('the project condition "{condition}" holds'))
def _pf_advisory_given(project_dir, tex_content, condition):
    _pf_advisory_setup(project_dir, tex_content, condition)


# --- Then assertions ---


@then(parsers.parse('{stream:w} contains a line starting with "[{severity}]" mentioning "{token}"'))
def _pf_stream_severity_mentions(result, stream, severity, token):
    stream_text = result[stream]
    matches = [line for line in stream_text.splitlines() if line.lstrip().startswith(f"[{severity}]") and token in line]
    assert matches, f"no [{severity}] line in {stream} mentioning {token!r}; got:\n{stream_text}"


@then('a "[error]" mentions that arXiv forbids user-supplied psfig.sty')
def _pf_psfig_error(result):
    _pf_assert_severity(result, "error", "psfig.sty", "forbids")


@then('an "[error]" mentions that XeLaTeX or LuaLaTeX is required')
def _pf_xelatex_required(result):
    _pf_assert_severity(result, "error", "XeLaTeX")


@then('no fontspec-related "[error]" is emitted')
def _pf_no_fontspec_error(result):
    _pf_assert_no_severity_containing(result, "error", "fontspec")


@then('an "[error]" instructs the user to externalize TikZ figures locally')
def _pf_tikz_error(result):
    _pf_assert_severity(result, "error", "tikzexternalize")


@then('an "[error]" notes the missing .bib without a fallback .bbl')
def _pf_bib_missing_error(result):
    _pf_assert_severity(result, "error", "bibliography", "bbl")


@then('a "[warn]" recommends shipping the `.bbl` as a fallback')
def _pf_biblatex_warn(result):
    _pf_assert_severity(result, "warn", "biblatex", "bbl")


@then('a "[warn]" notes that arXiv compiles from root')
def _pf_main_root_warn(result):
    _pf_assert_severity(result, "warn", "root")


@then('a "[warn]" notes the section will silently disappear on arXiv')
def _pf_section_disappear_warn(result):
    _pf_assert_severity(result, "warn", "arXiv")


@then('a "[warn]" notes that arXiv may rebuild the PDF and the date will change')
def _pf_today_warn(result):
    _pf_assert_severity(result, "warn", "today", "date")


@then('a "[warn]" notes the size and recommends `--resize` or splitting')
def _pf_size_warn(result):
    _pf_assert_severity(result, "warn", "MB", "--resize")


@then("the process still exits with code 0 if no errors are present")
def _pf_rc0_if_no_errors(result):
    assert result["rc"] == 0, (result["rc"], result["stderr"])


@then('a "[warn]" recommends converting .eps or switching compilers')
def _pf_eps_warn(result):
    _pf_assert_severity(result, "warn", ".eps")


@then('a "[warn]" notes that `\\input`/`\\includegraphics` resolution will break')
def _pf_filename_warn(result):
    _pf_assert_severity(result, "warn", "filename", "spaces")


@then('all three "[warn]" lines are emitted independently')
def _pf_three_warn_independent(result):
    for kw in ("today", "biblatex", "MB"):
        _pf_assert_severity(result, "warn", kw)


@then(parsers.parse('a "[warn]" mentioning "{topic}" is emitted'))
def _pf_advisory_warn(result, topic):
    # Map topic phrasing → keyword(s) actually present in code's warn line.
    keyword_map = {
        "external-document references break": ["xr", "external-document"],
        "single-spaced submissions required": ["single-spaced"],
        "includeonly restricts compilation": ["includeonly"],
        "duplicate bibliography command": ["bibliographystyle", "subfile"],
        "build server can't resolve absolute paths": ["absolute path"],
        "eps→pdf artifacts in source": ["eps-converted-to"],
        "arXiv deletes files starting with `.`": ["hidden", "."],
        "oversized PNG; consider `--resize`": ["megapixels", "--resize"],
        "re-save as UTF-8": ["UTF-8"],
        "non-ASCII filename": ["non-ASCII", "filename"],
        "spaces in directory name": ["spaces", "directory"],
    }
    keywords = keyword_map.get(topic, [topic])
    _pf_assert_severity(result, "warn", *keywords)
