"""GitHub Action surface: static-analysis assertions over action.yml.

The composite action cannot run headless inside pytest, so each spec scenario
reduces to verifying that action.yml declares the right inputs, defaults, and
runs the CLI / install / setup-python steps with the right shell logic.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pytest_bdd import given, parsers, then, when


_REPO = Path(__file__).resolve().parent.parent.parent.parent
_ACTION = _REPO / "action.yml"


def _load_action() -> dict:
    return yaml.safe_load(_ACTION.read_text())


def _run_steps() -> list[dict]:
    return _load_action()["runs"]["steps"]


def _run_pre_flight_script() -> str:
    for step in _run_steps():
        if step.get("id") == "run":
            return step["run"]
    raise AssertionError("no step with id=run in action.yml")


def _install_step_script() -> str:
    for step in _run_steps():
        if step.get("name", "").lower().startswith("install"):
            return step["run"]
    raise AssertionError("no install step in action.yml")


# --- Background + Givens ---


@given(parsers.re(r"^a CI job using `uses: YuZh98/latex2arxiv@<ref>` in a step$"))
def _act_using():
    assert _ACTION.exists(), f"action.yml missing at {_ACTION}"
    data = _load_action()
    assert data.get("runs", {}).get("using") == "composite", (
        f"action.yml is not a composite action: {data.get('runs')!r}"
    )


@given(parsers.parse("the step input `{name}` points at a LaTeX project (directory or .zip)"))
def _act_input_present(result, name):
    result.setdefault("act_inputs", {})[name] = "input.zip"


@given(parsers.parse('the input `{name}` is left at its default ("{default}")'))
def _act_input_default(result, name, default):
    inputs = _load_action()["inputs"]
    assert name in inputs, f"input {name!r} not declared in action.yml"
    declared_default = str(inputs[name].get("default", ""))
    assert declared_default == default, f"input {name!r} default = {declared_default!r}, spec asserts {default!r}"
    result.setdefault("act_inputs", {})[name] = default


@given(parsers.parse('the input `{name}` is set to "{value}"'))
def _act_input_set(result, name, value):
    result.setdefault("act_inputs", {})[name] = value


@given(parsers.parse("the input `{name}` is a directory"))
def _act_input_dir(result, name):
    result.setdefault("act_inputs", {})[name] = "src/"


@given(parsers.parse("the input `{name}` is left empty"))
def _act_input_empty(result, name):
    inputs = _load_action()["inputs"]
    assert name in inputs, f"input {name!r} not declared in action.yml"
    default = str(inputs[name].get("default", ""))
    assert default == "", f"input {name!r} default is not empty: {default!r}"
    result.setdefault("act_inputs", {})[name] = ""


@given("the LaTeX project triggers a `[error]` (e.g. minted)")
def _act_project_with_error(result):
    result["act_project_error"] = True


# --- When ---


@when("the action runs")
def _act_runs(result):
    result["act_action"] = "run"


@when("the action runs in dry-run mode")
def _act_runs_dry(result):
    result.setdefault("act_inputs", {}).setdefault("dry-run", "true")
    result["act_action"] = "run"


# --- Then ---


def _arg_branch(flag: str, env_var: str, value_check: str = "-n") -> str:
    """Return the bash-arg block that conditionally appends `flag` based on
    whether `env_var` is non-empty (-n) or equals true (=true).
    """
    return f'if [ "{value_check}" "${env_var}" ];' if value_check else env_var


def _has_block(script: str, *required_substrings: str) -> bool:
    """All substrings must be present in `script` in the given order, with no
    intervening newlines outside their own content. We approximate by checking
    each appears and the next one starts after the previous one ends.
    """
    cursor = 0
    for needle in required_substrings:
        idx = script.find(needle, cursor)
        if idx < 0:
            return False
        cursor = idx + len(needle)
    return True


@then("the latex2arxiv CLI is invoked with `--dry-run`")
def _act_dry_run_on():
    script = _run_pre_flight_script()
    # Assert the gated block literally: `if [ "$L2A_DRY_RUN" = "true" ]` … `ARGS+=(--dry-run)`.
    assert _has_block(script, '"$L2A_DRY_RUN" = "true"', "ARGS+=(--dry-run)"), (
        f"action.yml does not conditionally append --dry-run inside the dry-run gate; script:\n{script}"
    )


@then("no `cleaned-zip` step output is exported")
def _act_no_cleaned_zip_output():
    script = _run_pre_flight_script()
    # The cleaned-zip export must be guarded by NOT dry-run.
    assert 'L2A_DRY_RUN" != "true"' in script, f"cleaned-zip export is unguarded; script:\n{script}"
    assert "cleaned-zip=" in script, "cleaned-zip output never written"


@then("the latex2arxiv CLI is invoked without `--dry-run`")
def _act_dry_run_off():
    script = _run_pre_flight_script()
    # The only --dry-run occurrence must live inside the L2A_DRY_RUN == "true"
    # gate; that's what makes the false-input path skip the flag.
    assert _has_block(script, '"$L2A_DRY_RUN" = "true"', "ARGS+=(--dry-run)"), (
        f"--dry-run is not gated inside the dry-run-true branch; script:\n{script}"
    )
    # If --dry-run appears anywhere outside the gate, the flag would be
    # appended unconditionally. There is exactly one occurrence in the gated
    # block; assert that count is also 1.
    assert script.count("--dry-run") == 1, (
        f"--dry-run appears outside the dry-run-true gate {script.count('--dry-run')} time(s); script:\n{script}"
    )


@then("the step output `cleaned-zip` is exported pointing at the written zip")
def _act_cleaned_zip_exported():
    data = _load_action()
    outputs = data.get("outputs", {})
    assert "cleaned-zip" in outputs, f"cleaned-zip output not declared in action.yml outputs: {outputs}"
    value = outputs["cleaned-zip"].get("value", "")
    assert "steps.run.outputs.cleaned-zip" in value, (
        f"cleaned-zip output does not reference steps.run.outputs: {value!r}"
    )
    script = _run_pre_flight_script()
    assert 'echo "cleaned-zip=$OUTPUT_PATH"' in script or "cleaned-zip=" in script, (
        "run step does not echo cleaned-zip=... to $GITHUB_OUTPUT"
    )


@then("the action zips the directory to a temporary location")
def _act_dir_zipped():
    script = _run_pre_flight_script()
    assert "if [ -d" in script and "zip" in script, f"no directory→zip branch in run step:\n{script}"
    assert "mktemp" in script, "no mktemp invocation for the temp zip location"


@then(parsers.parse("`{exclusions}` are excluded from that zip"))
def _act_zip_exclusions(exclusions):
    script = _run_pre_flight_script()
    # Spec lists exclusions backtick-comma-separated with an English "and "
    # before the last entry. Strip both before/after each token.
    expected = []
    for tok in exclusions.split(","):
        cleaned = tok.strip().strip("`")
        if cleaned.lower().startswith("and "):
            cleaned = cleaned[4:].strip().strip("`")
        if cleaned:
            expected.append(cleaned)
    for pattern in expected:
        assert pattern in script, f"zip exclusion {pattern!r} missing from run step:\n{script}"


@then("the CLI is invoked against the temp zip")
def _act_cli_temp_zip():
    script = _run_pre_flight_script()
    assert "ZIP_PATH" in script and "INPUT_PATH=" in script, "no temp-zip path threading in run step"
    assert 'latex2arxiv "$INPUT_PATH"' in script, "CLI is not invoked against $INPUT_PATH"


@then(parsers.parse("the CLI is invoked with the flag `{flag}` and the same value"))
def _act_flag_with_value(result, flag):
    script = _run_pre_flight_script()
    # Examples: --main, --config, --resize. Each input maps to a conditional
    # ARGS+=("<flag>" "$L2A_<UPPER>") branch.
    env_var = {
        "--main": "L2A_MAIN",
        "--config": "L2A_CONFIG",
        "--resize": "L2A_RESIZE",
    }.get(flag)
    assert env_var, f"unmapped flag in spec: {flag!r}"
    assert (
        f'ARGS+=({flag} "${env_var}")' in script
        or f'ARGS+=({flag!r} "${env_var}")' in script
        or (f"ARGS+=({flag}" in script and f'"${env_var}"' in script)
    ), f"action.yml does not forward {flag} from {env_var}:\n{script}"


@then("the latex2arxiv CLI is invoked with `--flatten`")
def _act_flatten_on():
    script = _run_pre_flight_script()
    assert _has_block(script, '"$L2A_FLATTEN" = "true"', "ARGS+=(--flatten)"), (
        f"--flatten branch missing or unguarded:\n{script}"
    )


@then("the resulting output reflects the flattened single-file `.tex`")
def _act_flatten_outcome():
    # Static-analysis only — the actual flatten effect is owned by the CLI and
    # already covered by flatten.feature. Here we just confirm the flag wiring.
    script = _run_pre_flight_script()
    assert "--flatten" in script, "--flatten flag not present in run step"


@then("the latex2arxiv CLI is invoked without `--flatten`")
def _act_flatten_off():
    script = _run_pre_flight_script()
    inputs = _load_action()["inputs"]
    assert inputs["flatten"]["default"] == "false", "flatten default is not 'false'"
    # The --flatten flag must live entirely inside the L2A_FLATTEN gate so the
    # default-false input path skips it.
    assert _has_block(script, '"$L2A_FLATTEN" = "true"', "ARGS+=(--flatten)"), (
        f"no gated --flatten block in run step; script:\n{script}"
    )
    assert script.count("--flatten") == 1, (
        f"--flatten appears outside the flatten gate {script.count('--flatten')} time(s); script:\n{script}"
    )


@then("the latex2arxiv CLI is invoked with `--resize 800`")
def _act_resize_with_value():
    script = _run_pre_flight_script()
    assert "--resize" in script and "L2A_RESIZE" in script, "--resize/L2A_RESIZE wiring missing"
    assert '-n "$L2A_RESIZE"' in script, "no non-empty guard on L2A_RESIZE"


@then("images in the output are downscaled so the longest side ≤ 800 px")
def _act_resize_outcome():
    # Static-analysis only — actual downscaling is owned by the CLI and covered
    # by resize_images.feature.
    script = _run_pre_flight_script()
    assert "--resize" in script, "--resize flag not present"


@then("the latex2arxiv CLI is invoked without `--resize`")
def _act_resize_off():
    inputs = _load_action()["inputs"]
    assert inputs["resize"]["default"] == "", "resize default is not empty"
    script = _run_pre_flight_script()
    assert '-n "$L2A_RESIZE"' in script, "no empty-guard on resize"


@then(parsers.parse('the install step runs `pip install "latex2arxiv=={version}"`'))
def _act_pip_install_pin(version):
    script = _install_step_script()
    assert 'pip install "latex2arxiv==$L2A_VERSION"' in script, f"install step does not pin via L2A_VERSION:\n{script}"


@then("the install step runs `pip install latex2arxiv` without a version pin")
def _act_pip_install_no_pin():
    script = _install_step_script()
    assert "pip install latex2arxiv" in script and "-z" in script and "L2A_VERSION" in script, (
        f"install step does not branch on empty L2A_VERSION:\n{script}"
    )


@then(parsers.parse("`actions/setup-python` is invoked with `python-version: {version}`"))
def _act_setup_python(result, version):
    for step in _run_steps():
        if "setup-python" in step.get("uses", ""):
            with_block = step.get("with", {})
            template = str(with_block.get("python-version", ""))
            # Template uses ${{ inputs.python-version }}; the override is then
            # supplied by the input. We assert the wiring exists.
            assert "inputs.python-version" in template, (
                f"setup-python python-version is not wired to inputs.python-version: {template!r}"
            )
            input_value = result.get("act_inputs", {}).get("python-version")
            assert input_value == version, f"python-version input expected {version!r}, got {input_value!r}"
            return
    raise AssertionError("no actions/setup-python step in action.yml")


@then("the latex2arxiv CLI exits with code 1")
def _act_cli_exits_1(result):
    # Static-analysis: the CLI's exit-1-on-error behavior itself is covered by
    # preflight_checks.feature. Here we verify the action actually invokes
    # `latex2arxiv` AND nothing after the invocation could mask a non-zero exit
    # before `set -e` propagates it (no unconditional `exit 0`, no `&& :` etc).
    assert result.get("act_project_error") is True
    script = _run_pre_flight_script()
    invoke_line = next(
        (line for line in script.splitlines() if line.strip().startswith("latex2arxiv ")),
        None,
    )
    assert invoke_line is not None, f"no latex2arxiv invocation in run script:\n{script}"
    tail = script.split(invoke_line, 1)[1]
    assert "exit 0" not in tail, f"unconditional `exit 0` after latex2arxiv would mask exit code:\n{tail}"
    assert "&& :" not in tail and "|| :" not in tail, f"`&& :` / `|| :` after latex2arxiv would mask exit code:\n{tail}"


@then("the step fails (`set -e` propagates the non-zero exit)")
def _act_set_e():
    script = _run_pre_flight_script()
    assert "set -e" in script, "run step does not use set -e"


@then("the job is marked failed by the GitHub runner")
def _act_job_fails():
    # Three guards must hold for non-zero CLI exit to surface as a job failure:
    # (1) no `continue-on-error` escape hatch on any step,
    # (2) the run script does not contain `|| true` (would swallow the CLI exit),
    # (3) the run script does not contain `set +e` (would disable the propagation set -e provides).
    for step in _run_steps():
        assert not step.get("continue-on-error"), (
            f"step {step.get('name')!r} silently swallows failures via continue-on-error"
        )
    script = _run_pre_flight_script()
    assert "|| true" not in script, f"run script contains `|| true` and would swallow exit:\n{script}"
    assert "set +e" not in script, f"run script disables `set -e` and would not propagate exit:\n{script}"
