"""Refactor safety net — Python-level Issues snapshot per fixture.

Mirrors how mcp_server.py consumes Issues (direct Python call, not CLI).
Any refactor PR that changes issue messages, severity, or ordering on any
fixture will fail this test. Do not edit baselines casually.

Generation recipe (kept identical between this test and the baseline generator):
zip each fixture directory deterministically (sorted rglob, skip .DS_Store),
call convert(zip, out_zip, dry_run=True), normalize as
{"errors": sorted(issues.errors), "warnings": sorted(issues.warnings)}.

Stored baselines live in tests/baselines/<fixture>.python.json. To regenerate
intentionally after a behavior change: delete the baseline and rerun pytest;
this test only asserts equality, it does not auto-regenerate.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

# Ensure the worktree converter.py wins over any site-packages installation.
sys.path.insert(0, str(Path(__file__).parent.parent))

from converter import Issues, convert  # noqa: E402

FIXTURES = sorted(Path("tests/fixtures").glob("[0-9][0-9]-*"))
BASELINE_DIR = Path("tests/baselines")


def _zip_fixture(fixture_dir: Path, out_zip: Path) -> None:
    """Same recipe used by the baseline generator. Sorted member order,
    macOS noise skipped. Member mtimes are not normalized — Detector B
    hashes Issues content, not zip bytes, so this is robust."""
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(fixture_dir.rglob("*")):
            if p.is_file() and p.name != ".DS_Store":
                zf.write(p, p.relative_to(fixture_dir))


def _normalize(issues: Issues) -> dict:
    return {
        "errors": sorted(issues.errors),
        "warnings": sorted(issues.warnings),
    }


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.name)
def test_convert_issues_baseline(fixture, tmp_path):
    zip_in = tmp_path / "in.zip"
    zip_out = tmp_path / "out.zip"
    _zip_fixture(fixture, zip_in)
    issues = convert(zip_in, zip_out, dry_run=True)
    snapshot = _normalize(issues)
    baseline = BASELINE_DIR / f"{fixture.name}.python.json"
    assert baseline.exists(), f"missing baseline {baseline}; regenerate"
    expected = json.loads(baseline.read_text())
    assert snapshot == expected, (
        f"Python-level Issues baseline drifted for {fixture.name}.\n"
        f"If intentional, regenerate: rm {baseline} && pytest -k {fixture.name}"
    )
