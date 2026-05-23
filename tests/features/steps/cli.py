"""CLI-surface steps: invoke converter.py as a subprocess and inspect outputs."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import zipfile

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


def _output_zip(project_dir):
    return project_dir / "paper_arxiv.zip"


@then("the output zip contains exactly one .tex file at the root")
def _one_tex_at_root(project_dir):
    out = _output_zip(project_dir)
    assert out.exists(), f"no output zip at {out}"
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    root_tex = [n for n in names if n.endswith(".tex") and "/" not in n]
    assert len(root_tex) == 1, f"expected 1 root .tex, got {root_tex} from {names}"


@then(parsers.parse('that file is the inlined "{name}"'))
def _is_inlined_main(project_dir, name):
    out = _output_zip(project_dir)
    with zipfile.ZipFile(out) as zf:
        body = zf.read(name).decode()
    assert "Intro text" in body, f"intro not inlined into {name}: {body!r}"
    assert "Methods text" in body, f"methods not inlined into {name}: {body!r}"


@then(parsers.parse("the original fragment files ({names}) are not in the output zip"))
def _fragments_absent(project_dir, names):
    out = _output_zip(project_dir)
    with zipfile.ZipFile(out) as zf:
        zip_names = set(zf.namelist())
    fragments = [n.strip() for n in names.split(",")]
    leaked = [f for f in fragments if any(z.endswith(f) for z in zip_names)]
    assert not leaked, f"fragments leaked into output zip: {leaked}; zip contents={zip_names}"


@then("`\\includegraphics` paths in the inlined .tex still resolve relative to the new root")
def _includegraphics_resolves(project_dir):
    out = _output_zip(project_dir)
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        body = zf.read("main.tex").decode()
    import re as _re

    paths = _re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body)
    for p in paths:
        candidates = {p, p + ".pdf", p + ".png", p + ".jpg", p + ".jpeg", p + ".eps"}
        assert candidates & names, f"figure path {p!r} does not resolve in zip; zip={names}"


@then("every referenced figure file is present in the output zip")
def _figures_present(project_dir):
    _includegraphics_resolves(project_dir)


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
def _structural_equiv(project_dir):
    flat_zip = _output_zip(project_dir)
    with zipfile.ZipFile(flat_zip) as zf:
        flat_names = set(zf.namelist())
    flat_zip.unlink()
    subprocess.run(
        [sys.executable, str(common.CONVERTER), "paper.zip"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    with zipfile.ZipFile(flat_zip) as zf:
        plain_names = set(zf.namelist())
    assert flat_names == plain_names, f"flatten={flat_names} vs plain={plain_names}"


@then(parsers.parse('"{name}" content does not appear in the inlined output'))
def _comment_not_inlined(project_dir, name):
    out = _output_zip(project_dir)
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        body = zf.read("main.tex").decode()
    stem = name.replace(".tex", "")
    assert not any(stem in n for n in names if n != "main.tex"), f"{stem!r} fragment leaked into zip: {names}"
    assert stem not in body, f"{stem!r} appears in inlined main.tex: {body!r}"
