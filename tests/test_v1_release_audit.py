"""Pre-v1.0.0 release audit.

Each test verifies a specific behavioral contract that must hold at v1.0:
- documented CLI flags produce their stated effects
- pre-flight checks fire (or don't) correctly
- JSON schema contract (no [error]/[warn] prefixes, all fields present)
- file preservation rules (.sty, .cls, .bst, .bbl, .eps warning)
- security protections in place
- public API surface correct
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from converter import convert, ConverterError, Issues


# ── helpers ──────────────────────────────────────────────────────────────────

def _zip(tmp_path: Path, files: dict) -> Path:
    """Build a zip at tmp_path/proj.zip from {name: content} dict."""
    zp = tmp_path / "proj.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for name, content in files.items():
            if isinstance(content, str):
                zf.writestr(name, content)
            else:
                zf.writestr(name, content)
    return zp


_MINIMAL_TEX = r"""\documentclass{article}
\begin{document}
Hello world.
\end{document}
"""

_TITLED_TEX = r"""\documentclass{article}
\title{My Audit Paper}
\author{Alice Smith}
\begin{abstract}
This is an abstract about something important.
\end{abstract}
\begin{document}
\maketitle
Hello world.
\end{document}
"""


# ── 1. --guide flag ───────────────────────────────────────────────────────────

class TestGuideFlag:
    """`--guide` writes a `*_UPLOAD_GUIDE.txt` alongside the output zip."""

    def test_guide_creates_upload_guide_txt(self, tmp_path):
        zp = _zip(tmp_path, {"main.tex": _TITLED_TEX})
        out = tmp_path / "out_arxiv.zip"
        convert(zp, out, guide=True)
        guide_path = out.with_name("out_arxiv_UPLOAD_GUIDE.txt")
        assert guide_path.exists(), "guide file must be written next to the output zip"

    def test_guide_content_contains_steps(self, tmp_path):
        zp = _zip(tmp_path, {"main.tex": _TITLED_TEX})
        out = tmp_path / "out_arxiv.zip"
        convert(zp, out, guide=True)
        guide = out.with_name("out_arxiv_UPLOAD_GUIDE.txt").read_text()
        for step in range(1, 8):
            assert f"Step {step}:" in guide, f"Guide missing Step {step}"

    def test_guide_content_contains_title(self, tmp_path):
        zp = _zip(tmp_path, {"main.tex": _TITLED_TEX})
        out = tmp_path / "out_arxiv.zip"
        convert(zp, out, guide=True)
        guide = out.with_name("out_arxiv_UPLOAD_GUIDE.txt").read_text()
        assert "My Audit Paper" in guide

    def test_guide_dry_run_does_not_write_file(self, tmp_path):
        zp = _zip(tmp_path, {"main.tex": _TITLED_TEX})
        out = tmp_path / "out_arxiv.zip"
        convert(zp, out, guide=True, dry_run=True)
        guide_path = out.with_name("out_arxiv_UPLOAD_GUIDE.txt")
        assert not guide_path.exists(), "--dry-run must not write the guide file"

    def test_guide_populates_metadata_on_issues(self, tmp_path):
        zp = _zip(tmp_path, {"main.tex": _TITLED_TEX})
        out = tmp_path / "out_arxiv.zip"
        issues = convert(zp, out, guide=True)
        assert issues.metadata is not None, "issues.metadata must be populated when --guide used"
        assert "title" in issues.metadata


# ── 2. JSON string contract: no [error]/[warn] prefix ────────────────────────

class TestJsonStringContracts:
    """errors/warnings in both the Issues API and --json output are flat strings
    with NO [error] or [warn] prefix (json-schema.md v1 contract)."""

    def test_issues_errors_have_no_bracket_prefix(self, tmp_path):
        """Issues.error() must store clean strings, not '[error] ...' strings."""
        zp = _zip(tmp_path, {"main.tex":
            r"\documentclass{article}\usepackage{minted}\begin{document}\end{document}"})
        out = tmp_path / "out.zip"
        issues = convert(zp, out, dry_run=True)
        assert issues.errors, "minted must trigger at least one error"
        for e in issues.errors:
            assert not e.startswith("[error]"), f"error has bracket prefix: {e!r}"
            assert not e.startswith("[warn]"), f"error has wrong prefix: {e!r}"

    def test_issues_warnings_have_no_bracket_prefix(self, tmp_path):
        """Issues.warn() must store clean strings, not '[warn] ...' strings."""
        zp = _zip(tmp_path, {"main.tex":
            r"\documentclass{article}\begin{document}\date{\today}\end{document}"})
        out = tmp_path / "out.zip"
        issues = convert(zp, out, dry_run=True)
        assert issues.warnings, "\\today in \\date must trigger at least one warning"
        for w in issues.warnings:
            assert not w.startswith("[warn]"), f"warning has bracket prefix: {w!r}"
            assert not w.startswith("[error]"), f"warning has wrong prefix: {w!r}"

    def test_issues_warn_and_error_store_raw_message(self):
        """Issues.warn/error append the raw message, not prefixed output."""
        i = Issues()
        i.warn("something suspicious")
        i.error("something broken")
        assert i.warnings == ["something suspicious"]
        assert i.errors == ["something broken"]


# ── 3. --main hint not found ──────────────────────────────────────────────────

class TestMainHint:
    """`--main` hint that doesn't exist in the archive must raise ConverterError."""

    def test_main_hint_not_found_raises_converter_error(self, tmp_path):
        zp = _zip(tmp_path, {"main.tex": _MINIMAL_TEX})
        out = tmp_path / "out.zip"
        with pytest.raises(ConverterError, match="not found in archive"):
            convert(zp, out, main_hint="nonexistent.tex")

    def test_main_hint_found_uses_specified_file(self, tmp_path):
        zp = _zip(tmp_path, {
            "paper.tex": _MINIMAL_TEX,
            "draft.tex": r"\documentclass{article}\begin{document}Draft\end{document}",
        })
        out = tmp_path / "out.zip"
        issues = convert(zp, out, main_hint="paper.tex", dry_run=True)
        assert issues.main_tex == "paper.tex"


# ── 4. .eps file pre-flight warning ──────────────────────────────────────────

class TestEpsPreFlight:
    """.eps images in the project trigger a pre-flight warning."""

    def test_eps_file_warns(self, tmp_path):
        zp = _zip(tmp_path, {
            "main.tex": _MINIMAL_TEX,
            "figure.eps": b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 100 100\n",
        })
        out = tmp_path / "out.zip"
        issues = convert(zp, out, dry_run=True)
        assert any("eps" in w.lower() for w in issues.warnings), (
            f"Expected .eps warning, got: {issues.warnings}"
        )

    def test_eps_warning_names_the_file(self, tmp_path):
        zp = _zip(tmp_path, {
            "main.tex": _MINIMAL_TEX,
            "myfig.eps": b"%!PS fake eps",
        })
        out = tmp_path / "out.zip"
        issues = convert(zp, out, dry_run=True)
        eps_warns = [w for w in issues.warnings if "eps" in w.lower()]
        assert eps_warns, "Must warn about .eps file"
        assert "myfig.eps" in eps_warns[0], "Warning must name the specific file"


# ── 5. Style/support files preserved ─────────────────────────────────────────

class TestSupportFilesPreserved:
    """Custom .sty, .cls, and .bst files at the root are kept in the output."""

    def test_custom_cls_preserved(self, tmp_path):
        zp = _zip(tmp_path, {
            "main.tex": r"\documentclass{myjournal}\begin{document}Text.\end{document}",
            "myjournal.cls": r"\ProvidesClass{myjournal}",
        })
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            assert "myjournal.cls" in zf.namelist(), (
                "Custom .cls used by \\documentclass must be kept"
            )

    def test_custom_sty_preserved(self, tmp_path):
        zp = _zip(tmp_path, {
            "main.tex": (r"\documentclass{article}"
                         r"\usepackage{mypackage}"
                         r"\begin{document}Text.\end{document}"),
            "mypackage.sty": r"\ProvidesPackage{mypackage}",
        })
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            assert "mypackage.sty" in zf.namelist(), (
                "Custom .sty used by \\usepackage must be kept"
            )

    def test_bst_at_root_always_preserved(self, tmp_path):
        zp = _zip(tmp_path, {
            "main.tex": (r"\documentclass{article}"
                         r"\begin{document}\bibliographystyle{mybib}"
                         r"\bibliography{refs}\end{document}"),
            "mybib.bst": "% bst file",
            "refs.bib": "@misc{k, note={n}}",
        })
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            assert "mybib.bst" in zf.namelist(), ".bst at root must always be preserved"

    def test_unreferenced_sty_not_preserved(self, tmp_path):
        """A .sty not referenced in the .tex is pruned (not a style file of the submission)."""
        zp = _zip(tmp_path, {
            "main.tex": r"\documentclass{article}\begin{document}Text.\end{document}",
            "unused.sty": r"\ProvidesPackage{unused}",
        })
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            assert "unused.sty" not in zf.namelist(), (
                "Unreferenced .sty must be pruned"
            )


# ── 6. --resize flag ──────────────────────────────────────────────────────────

try:
    from PIL import Image as _PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


@pytest.mark.skipif(not _HAS_PIL, reason="Pillow not installed")
class TestResizeFlag:
    def _big_png(self, path: Path) -> Path:
        img = _PILImage.new("RGB", (3200, 2400), color=(200, 100, 50))
        img.save(path, "PNG")
        return path

    def test_resize_shrinks_large_image(self, tmp_path):
        img = self._big_png(tmp_path / "fig.png")
        # Build zip with a large image
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("main.tex",
                r"\documentclass{article}\begin{document}"
                r"\includegraphics{fig}\end{document}")
            zf.write(img, "fig.png")
        zp = tmp_path / "proj.zip"
        zp.write_bytes(buf.getvalue())
        out = tmp_path / "out.zip"
        convert(zp, out, resize=800)
        with zipfile.ZipFile(out) as zf:
            data = zf.read("fig.png")
        with _PILImage.open(io.BytesIO(data)) as resized:
            assert max(resized.size) <= 800, "Image must be resized to fit within 800px"

    def test_resize_dry_run_does_not_modify_image(self, tmp_path):
        img = self._big_png(tmp_path / "fig.png")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("main.tex",
                r"\documentclass{article}\begin{document}"
                r"\includegraphics{fig}\end{document}")
            zf.write(img, "fig.png")
        zp = tmp_path / "proj.zip"
        zp.write_bytes(buf.getvalue())
        out = tmp_path / "out.zip"
        convert(zp, out, resize=800, dry_run=True)
        # Image must not have changed in the *source* area (dry-run shouldn't write output)
        assert not out.exists(), "dry-run must not produce output zip"


# ── 7. config_path applied in convert() ──────────────────────────────────────

class TestConfigPathApplied:
    """`config_path` passed to `convert()` is applied to the tex source."""

    def test_config_removes_commands(self, tmp_path):
        tex = (r"\documentclass{article}\begin{document}"
               r"Normal text. \myreview{reviewer comment} More text."
               r"\end{document}")
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text("commands_to_delete:\n  - \\myreview\n")
        zp = _zip(tmp_path, {"main.tex": tex})
        out = tmp_path / "out.zip"
        convert(zp, out, config_path=cfg)
        with zipfile.ZipFile(out) as zf:
            src = zf.read("main.tex").decode()
        assert r"\myreview" not in src, "config_path command must be removed from output"
        assert "reviewer comment" not in src
        assert "Normal text" in src

    def test_config_warnings_appear_in_issues(self, tmp_path):
        """Unknown config keys must produce a warning in issues.warnings."""
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text("unknown_key:\n  - foo\n")
        zp = _zip(tmp_path, {"main.tex": _MINIMAL_TEX})
        out = tmp_path / "out.zip"
        issues = convert(zp, out, config_path=cfg)
        assert any("unknown_key" in w for w in issues.warnings), (
            f"Unknown config key must warn; got: {issues.warnings}"
        )


# ── 8. flatten subfile without \begin{document} ───────────────────────────────

class TestFlattenSubfileWrapper:
    """`--flatten` warns when a \\subfile has no \\begin{document} wrapper."""

    def test_subfile_without_document_wrapper_warns(self, tmp_path):
        main = (r"\documentclass{article}"
                r"\usepackage{subfiles}"
                r"\begin{document}"
                r"\subfile{sec}"
                r"\end{document}")
        # sec.tex has no \begin{document} / \end{document} wrapper
        sec = "Just plain text with no documentclass wrapper."
        src = tmp_path / "proj"
        src.mkdir()
        (src / "main.tex").write_text(main)
        (src / "sec.tex").write_text(sec)
        zp = tmp_path / "proj.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.write(src / "main.tex", "main.tex")
            zf.write(src / "sec.tex", "sec.tex")
        out = tmp_path / "out.zip"
        issues = convert(zp, out, flatten=True)
        assert any("missing" in w.lower() or "wrapper" in w.lower() or "begin{document}" in w
                   for w in issues.warnings), (
            f"Expected warning about missing document wrapper; got: {issues.warnings}"
        )


# ── 9. tex.py edge cases ──────────────────────────────────────────────────────

class TestTexEdgeCases:
    """Edge cases in tex.py that are hard to reach through the full pipeline."""

    def test_find_balanced_minus_one_when_unclosed(self):
        from pipeline.tex import find_balanced
        assert find_balanced("hello", 0) == -1
        assert find_balanced("{unclosed", 0) == -1

    def test_unwrap_cmd_with_unclosed_brace_preserves_original(self):
        """unwrap_cmd must preserve the original match when braces are unbalanced."""
        import re
        from pipeline.tex import unwrap_cmd
        # Source with an unclosed brace after the command
        source = r"text \hl{unclosed partial"
        result = unwrap_cmd(source, re.compile(r'\\hl\b'))
        # Must not crash and the unclosed fragment must survive
        assert "unclosed" in result

    def test_remove_cmd_with_unclosed_brace_preserves_original(self):
        """remove_cmd must not corrupt source when braces are unbalanced."""
        import re
        from pipeline.tex import remove_cmd
        source = r"text \todo{unclosed brace partial"
        result = remove_cmd(source, re.compile(r'\\todo\b'))
        # Must not crash; some content must survive
        assert len(result) > 0


# ── 10. Public API contract ───────────────────────────────────────────────────

class TestPublicAPIContract:
    """The stable public API must be importable, functional, and exactly __all__."""

    def test_all_exports_are_importable(self):
        import converter
        for name in converter.__all__:
            assert hasattr(converter, name), f"{name} in __all__ but not importable"

    def test_no_private_names_in_all(self):
        import converter
        for name in converter.__all__:
            assert not name.startswith("_"), f"Private name {name!r} in __all__"

    def test_all_is_exactly_the_three_names(self):
        import converter
        assert set(converter.__all__) == {"Issues", "ConverterError", "convert"}

    def test_convert_returns_issues(self, tmp_path):
        zp = _zip(tmp_path, {"main.tex": _MINIMAL_TEX})
        out = tmp_path / "out.zip"
        result = convert(zp, out, dry_run=True)
        assert isinstance(result, Issues)

    def test_converter_error_is_exception(self):
        assert issubclass(ConverterError, Exception)

    def test_issues_has_errors_and_warnings_lists(self):
        i = Issues()
        assert isinstance(i.errors, list)
        assert isinstance(i.warnings, list)
        assert i.errors == []
        assert i.warnings == []

    def test_convert_raises_converter_error_on_bad_input(self, tmp_path):
        with pytest.raises(ConverterError):
            convert(tmp_path / "nonexistent.zip", tmp_path / "out.zip")


# ── 11. Exit-code contract ────────────────────────────────────────────────────

class TestExitCodes:
    """CLI exit codes: 0 on clean run, 1 when issues.errors is non-empty."""

    def _run(self, *args, cwd):
        import subprocess
        return subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "converter.py"), *args],
            capture_output=True, text=True, cwd=cwd, check=False,
        )

    def test_clean_project_exits_zero(self, tmp_path):
        r = self._run("--demo", "--dry-run", cwd=tmp_path)
        assert r.returncode == 0, f"stderr: {r.stderr[:300]}"

    def test_error_project_exits_nonzero(self, tmp_path):
        zp = _zip(tmp_path, {"main.tex":
            r"\documentclass{article}\usepackage{minted}\begin{document}\end{document}"})
        r = self._run(str(zp), "--dry-run", cwd=tmp_path)
        assert r.returncode != 0, "Project with pre-flight errors must exit non-zero"

    def test_nonexistent_input_exits_nonzero(self, tmp_path):
        r = self._run(str(tmp_path / "no.zip"), cwd=tmp_path)
        assert r.returncode != 0


# ── 12. Zip-bomb protection ───────────────────────────────────────────────────

class TestZipBombProtection:
    """Refuse to extract archives whose uncompressed size exceeds the cap."""

    def test_real_zip_under_limit_extracts_ok(self, tmp_path):
        zp = _zip(tmp_path, {"main.tex": _MINIMAL_TEX})
        out = tmp_path / "out.zip"
        issues = convert(zp, out, dry_run=True)
        # No crash = protection didn't fire spuriously
        assert isinstance(issues, Issues)


# ── 13. pdfoutput injection ───────────────────────────────────────────────────

class TestPdfoutputInjection:
    """`\\pdfoutput=1` is injected before \\documentclass when missing."""

    def test_pdfoutput_injected_when_missing(self, tmp_path):
        tex = r"\documentclass{article}\begin{document}Text.\end{document}"
        zp = _zip(tmp_path, {"main.tex": tex})
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            src = zf.read("main.tex").decode()
        assert r"\pdfoutput=1" in src, "\\pdfoutput=1 must be injected when missing"
        assert src.index(r"\pdfoutput=1") < src.index(r"\documentclass"), (
            "\\pdfoutput=1 must appear before \\documentclass"
        )

    def test_pdfoutput_not_duplicated_when_already_present(self, tmp_path):
        tex = r"\pdfoutput=1" + "\n" + r"\documentclass{article}\begin{document}Text.\end{document}"
        zp = _zip(tmp_path, {"main.tex": tex})
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            src = zf.read("main.tex").decode()
        assert src.count(r"\pdfoutput=1") == 1, "\\pdfoutput=1 must not be duplicated"


# ── 14. Comment stripping preserves verbatim ─────────────────────────────────

class TestCommentStrippingVerbatim:
    r"""Comments inside verbatim contexts must never be stripped."""

    def test_verb_url_not_stripped(self, tmp_path):
        tex = (r"\documentclass{article}\begin{document}"
               r"See \verb|% this is not a comment| here."
               r"\end{document}")
        zp = _zip(tmp_path, {"main.tex": tex})
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            src = zf.read("main.tex").decode()
        assert "% this is not a comment" in src, (
            "Content inside \\verb| must not be stripped"
        )

    def test_verbatim_environment_not_stripped(self, tmp_path):
        tex = (r"\documentclass{article}\usepackage{verbatim}"
               r"\begin{document}"
               r"\begin{verbatim}" "\n"
               r"% code comment inside verbatim" "\n"
               r"\end{verbatim}"
               r"\end{document}")
        zp = _zip(tmp_path, {"main.tex": tex})
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            src = zf.read("main.tex").decode()
        assert "% code comment inside verbatim" in src


# ── 15. Draft removal handles nested braces ──────────────────────────────────

class TestDraftRemovalNestedBraces:
    """\\todo{fix \\textbf{this}} must be fully removed, not partially."""

    def test_todo_with_nested_braces_removed(self, tmp_path):
        tex = (r"\documentclass{article}\begin{document}"
               r"Normal. \todo{fix \textbf{important}} More."
               r"\end{document}")
        zp = _zip(tmp_path, {"main.tex": tex})
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            src = zf.read("main.tex").decode()
        assert r"\todo" not in src
        assert "important" not in src, "Nested content inside \\todo must also be removed"
        assert "Normal" in src and "More" in src

    def test_hl_with_cite_inside_removed(self, tmp_path):
        tex = (r"\documentclass{article}\begin{document}"
               r"Result \hl{see \cite{smith}} here."
               r"\end{document}")
        zp = _zip(tmp_path, {"main.tex": tex})
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            src = zf.read("main.tex").decode()
        assert r"\hl" not in src


# ── 16. Undefined citation detection ─────────────────────────────────────────

class TestUndefinedCitationDetection:
    """`\\cite{key}` with no matching .bib/.bbl entry triggers a warning."""

    def test_missing_citation_warns(self, tmp_path):
        # Warning only fires when a .bib file is present (so we have a defined-key set).
        # Cite a key that isn't in the bib file.
        tex = (r"\documentclass{article}"
               r"\begin{document}See \cite{nosuchkey}.\bibliography{refs}\end{document}")
        bib = "@article{exists, author={A}, title={T}, year={2020}}"
        zp = _zip(tmp_path, {"main.tex": tex, "refs.bib": bib})
        out = tmp_path / "out.zip"
        issues = convert(zp, out)
        assert any("nosuchkey" in w for w in issues.warnings), (
            f"Undefined citation must warn; got: {issues.warnings}"
        )

    def test_defined_citation_does_not_warn(self, tmp_path):
        tex = (r"\documentclass{article}"
               r"\begin{document}See \cite{smith}.\bibliography{refs}\end{document}")
        bib = "@article{smith, author={Smith}, title={T}, year={2020}}"
        zp = _zip(tmp_path, {"main.tex": tex, "refs.bib": bib})
        out = tmp_path / "out.zip"
        issues = convert(zp, out)
        assert not any("smith" in w and "undefined" in w.lower() for w in issues.warnings), (
            f"Defined citation must not warn; got: {issues.warnings}"
        )


# ── 17. JSON field completeness ───────────────────────────────────────────────

class TestJsonFieldCompleteness:
    """All fields documented in json-schema.md are present in every response."""

    _REQUIRED = {
        "version", "schema_version", "input", "output", "main_tex",
        "dry_run", "removed_files", "kept_files", "errors", "warnings",
        "counts", "sizes", "compile", "flatten", "inlined_files", "metadata",
    }

    def _json_payload(self, tmp_path, extra_args=()):
        import subprocess
        r = subprocess.run(
            [sys.executable,
             str(Path(__file__).parent.parent / "converter.py"),
             "--demo", "--dry-run", "--json", *extra_args],
            capture_output=True, text=True, cwd=tmp_path, check=False,
        )
        return json.loads(r.stdout)

    def test_all_required_fields_present(self, tmp_path):
        payload = self._json_payload(tmp_path)
        missing = self._REQUIRED - set(payload.keys())
        assert not missing, f"JSON payload missing fields: {missing}"

    def test_compile_field_is_always_null_in_v1(self, tmp_path):
        payload = self._json_payload(tmp_path)
        assert payload["compile"] is None, (
            "compile field must be null in v1.0 (per json-schema.md contract)"
        )

    def test_schema_version_is_integer_one(self, tmp_path):
        payload = self._json_payload(tmp_path)
        assert payload["schema_version"] == 1

    def test_errors_and_warnings_are_lists_of_strings(self, tmp_path):
        payload = self._json_payload(tmp_path)
        assert isinstance(payload["errors"], list)
        assert isinstance(payload["warnings"], list)
        assert all(isinstance(e, str) for e in payload["errors"])
        assert all(isinstance(w, str) for w in payload["warnings"])

    def test_sizes_has_three_keys(self, tmp_path):
        payload = self._json_payload(tmp_path)
        assert set(payload["sizes"].keys()) == {"input_bytes", "output_bytes", "uncompressed_bytes"}

    def test_counts_match_list_lengths(self, tmp_path):
        payload = self._json_payload(tmp_path)
        c = payload["counts"]
        assert c["removed"] == len(payload["removed_files"])
        assert c["kept"] == len(payload["kept_files"])
        assert c["errors"] == len(payload["errors"])
        assert c["warnings"] == len(payload["warnings"])

    def test_flatten_field_false_when_not_used(self, tmp_path):
        payload = self._json_payload(tmp_path)
        assert payload["flatten"] is False

    def test_flatten_field_true_when_flatten_used(self, tmp_path):
        payload = self._json_payload(tmp_path, extra_args=("--flatten",))
        assert payload["flatten"] is True


# ── 18. bbl preservation ─────────────────────────────────────────────────────

class TestBblPreservation:
    """.bbl file matching the main stem is always kept."""

    def test_bbl_matching_main_stem_kept(self, tmp_path):
        tex = (r"\documentclass{article}\begin{document}"
               r"\bibliography{refs}\end{document}")
        zp = _zip(tmp_path, {
            "main.tex": tex,
            "main.bbl": r"\begin{thebibliography}{1}\end{thebibliography}",
            "refs.bib": "@misc{k, note={n}}",
        })
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            assert "main.bbl" in zf.namelist(), ".bbl matching main stem must be kept"

    def test_bbl_with_different_stem_not_kept(self, tmp_path):
        """A .bbl that doesn't match the main stem is not auto-preserved."""
        zp = _zip(tmp_path, {
            "main.tex": _MINIMAL_TEX,
            "other.bbl": r"\begin{thebibliography}{1}\end{thebibliography}",
        })
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            assert "other.bbl" not in zf.namelist(), (
                ".bbl with different stem must not be auto-preserved"
            )


# ── 19. 00README preservation ─────────────────────────────────────────────────

class TestZeroZeroReadme:
    """00README and 00README.XXX at root are preserved for arXiv processor hints."""

    def test_00readme_at_root_preserved(self, tmp_path):
        zp = _zip(tmp_path, {
            "main.tex": _MINIMAL_TEX,
            "00README": "nohypertex",
        })
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            assert "00README" in zf.namelist()

    def test_00readme_xxx_at_root_preserved(self, tmp_path):
        zp = _zip(tmp_path, {
            "main.tex": _MINIMAL_TEX,
            "00README.XXX": "nohypertex,xelatex",
        })
        out = tmp_path / "out.zip"
        convert(zp, out)
        with zipfile.ZipFile(out) as zf:
            assert "00README.XXX" in zf.namelist()
