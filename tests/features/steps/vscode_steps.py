"""VS Code extension surface: static-analysis assertions over package.json and
extension.ts. The extension cannot run headless in CI, so each spec scenario
reduces to a pattern match against the declared contributions and source.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pytest_bdd import given, parsers, then, when


_REPO = Path(__file__).resolve().parent.parent.parent.parent
_EXT = _REPO / "vscode-extension"
_PKG = _EXT / "package.json"
_SRC = _EXT / "src" / "extension.ts"


def _load_pkg() -> dict:
    return json.loads(_PKG.read_text())


def _load_src() -> str:
    return _SRC.read_text()


@given("the `latex2arxiv` VS Code extension is installed")
def _vs_ext_installed():
    assert _PKG.exists(), f"package.json missing at {_PKG}"
    assert _SRC.exists(), f"extension.ts missing at {_SRC}"


@given("a workspace folder is opened that contains at least one `.tex` file")
def _vs_workspace_with_tex():
    pkg = _load_pkg()
    events = pkg.get("activationEvents", [])
    assert any("*.tex" in e for e in events), f"no .tex activation event; got: {events}"


@given("the `latex2arxiv` CLI is available at the configured `latex2arxiv.executablePath`")
def _vs_cli_configured():
    pkg = _load_pkg()
    props = pkg["contributes"]["configuration"]["properties"]
    assert "latex2arxiv.executablePath" in props, "executablePath setting not declared"


@given(parsers.parse("the setting `{key}` is `{value}`"))
def _vs_setting(result, key, value):
    result.setdefault("vs_settings", {})[key] = value


@given(parsers.parse('the setting `{key}` is "{value}"'))
def _vs_setting_quoted(result, key, value):
    result.setdefault("vs_settings", {})[key] = value


# --- When ---


@when("VS Code opens the workspace")
def _vs_open_workspace(result):
    result["vs_action"] = "open_workspace"


@when(parsers.parse("I invoke the command `{name}` from the Command Palette"))
def _vs_invoke_command_palette(result, name):
    result["vs_action"] = "invoke"
    result["vs_command"] = name


@when(parsers.parse("I invoke `{name}`"))
def _vs_invoke_short(result, name):
    result["vs_action"] = "invoke"
    result["vs_command"] = name


@when(parsers.parse("I save any `.tex` file in the workspace"))
def _vs_save_tex(result):
    result["vs_action"] = "save_tex"


# --- Then ---


@then("the extension is activated automatically")
def _vs_activated():
    pkg = _load_pkg()
    assert pkg.get("activationEvents"), "no activationEvents declared"
    assert any("workspaceContains" in e for e in pkg["activationEvents"]), (
        f"activationEvents does not include workspaceContains: {pkg['activationEvents']}"
    )


@then("the configured executable is run on the workspace root with `--dry-run`")
def _vs_validate_invokes_dry_run():
    src = _load_src()
    # The validate path should spawn the CLI with --dry-run somewhere.
    assert "--dry-run" in src, "extension.ts never passes --dry-run"
    # And there should be a registerCommand wiring the validate handler.
    assert "registerCommand('latex2arxiv.validate'" in src or 'registerCommand("latex2arxiv.validate"' in src, (
        "validate command not registered"
    )


@then(
    "any pre-flight errors and warnings are surfaced in the editor (e.g. via diagnostics, output channel, or notification)"
)
def _vs_surface_diagnostics():
    src = _load_src()
    assert any(
        marker in src
        for marker in (
            "createDiagnosticCollection",
            "createOutputChannel",
            "showWarningMessage",
            "showErrorMessage",
            "showInformationMessage",
        )
    ), "extension.ts does not surface validation results via any standard channel"


@then("the configured executable is run on the workspace root without `--dry-run`")
def _vs_clean_no_dry_run():
    src = _load_src()
    # The clean handler should NOT include --dry-run in its arg list. We verify
    # by locating the clean handler block and asserting --dry-run is absent.
    m = re.search(r"function\s+clean\b.*?(?=\n(?:export\s+)?function\b|\Z)", src, re.S)
    assert m, "clean() function not found in extension.ts"
    assert "--dry-run" not in m.group(0), "clean handler unexpectedly passes --dry-run"


@then("the resulting `_arxiv.zip` location is reported back to the user")
def _vs_clean_reports_output():
    src = _load_src()
    # Extension parses the converter's "Converting X → Y" output line and
    # reports Y via an information message. Verify both halves.
    assert "parseOutputZip" in src or "Converting" in src, (
        "extension does not parse the output zip path from CLI stdout"
    )
    m = re.search(r"function\s+clean\b.*?(?=\n(?:export\s+|async\s+)?function\b|\Z)", src, re.S)
    assert m, "clean() function not found in extension.ts"
    body = m.group(0)
    assert any(api in body for api in ("showInformationMessage", "appendLine")), (
        "clean handler does not surface a result message"
    )


@then("validation runs automatically in the background")
def _vs_save_triggers_validation(result):
    assert result.get("vs_settings", {}).get("latex2arxiv.validateOnSave") == "true"
    src = _load_src()
    # extension.ts must register a workspace.onDidSaveTextDocument that calls
    # validate when the setting is true.
    assert "onDidSaveTextDocument" in src, "no onDidSaveTextDocument handler in extension.ts"
    assert "validateOnSave" in src, "validateOnSave setting not consulted"


@then("results are surfaced without blocking the editor")
def _vs_nonblocking():
    src = _load_src()
    # Async invocation pattern: validate(false) or similar fire-and-forget.
    assert "validate(false)" in src or "void validate" in src or "validate()" in src, (
        "no fire-and-forget validate call in onSave path"
    )


@then("no validation is triggered")
def _vs_no_save_validation(result):
    assert result.get("vs_settings", {}).get("latex2arxiv.validateOnSave") == "false"
    src = _load_src()
    # The handler must consult validateOnSave before invoking validate(). The
    # current pattern uses `if (cfg.get<boolean>('validateOnSave') && ...)` which
    # short-circuits when false.
    assert re.search(r"cfg\.get[^;]*validateOnSave", src), "onSave handler does not consult validateOnSave setting"


@then(parsers.parse("the CLI is invoked with `--main {path}`"))
def _vs_main_flag(result, path):
    src = _load_src()
    setting = result.get("vs_settings", {}).get("latex2arxiv.mainFile")
    assert setting == path, f"mainFile setting expected {path!r}, got {setting!r}"
    # The source must construct ['--main', mainFile] from the config value.
    assert re.search(r"'--main'|\"--main\"", src), "extension.ts does not pass --main"
    assert "mainFile" in src, "mainFile setting not referenced"


@given("`latex2arxiv` is not on PATH and `latex2arxiv.executablePath` points to a missing binary")
def _vs_missing_cli(result):
    result["vs_cli_missing"] = True


@then("a notification explains that the CLI was not found")
def _vs_notification_missing_cli():
    src = _load_src()
    # The extension surfaces a "not found" / "failed to invoke" notification.
    assert re.search(r"not found|failed to invoke|cannot find", src, re.I), (
        "no missing-CLI notification text in extension.ts"
    )
    assert any(api in src for api in ("showErrorMessage", "showWarningMessage")), "no error-level notification API used"


@then("the notification links to or describes the install instructions")
def _vs_notification_install_hint():
    src = _load_src()
    assert "pip install" in src or "install" in src.lower(), "no install hint text in extension.ts"
