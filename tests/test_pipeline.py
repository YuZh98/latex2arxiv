"""
Test suite for latex2arxiv.
Run with: python3.13 -m pytest tests/ -v
"""
import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.tex import (
    strip_comments,
    remove_draft_annotations,
    remove_comment_environments,
    ensure_pdfoutput,
    remove_draft_packages,
)
from pipeline.deps import find_used_images, find_used_style_files
from pipeline.config import apply_config
from pipeline.bibtex import normalize_bibtex


# ── tex.py ────────────────────────────────────────────────────────────────────

class TestStripComments:
    def test_removes_line_comment(self):
        assert strip_comments("hello % world\nnext") == "hello \nnext"

    def test_preserves_escaped_percent(self):
        assert "100\\%" in strip_comments("100\\% done % comment")

    def test_preserves_verbatim(self):
        src = "\\begin{verbatim}\n% keep this\n\\end{verbatim}"
        assert "% keep this" in strip_comments(src)

    def test_removes_full_comment_line(self):
        result = strip_comments("% entire line\ncode")
        assert "entire line" not in result
        assert "code" in result

    def test_no_spurious_paragraph_break(self):
        """A comment-only line should not become a blank line (paragraph break)."""
        result = strip_comments("First.\n% comment\nSecond.")
        assert "\n\n" not in result
        assert "First." in result and "Second." in result

    def test_multiple_comment_lines_no_break(self):
        result = strip_comments("a\n% c1\n% c2\nb")
        assert "\n\n" not in result


class TestRemoveDraftAnnotations:
    def test_removes_todo(self):
        assert remove_draft_annotations(r"\todo{fix this}") == ""

    def test_removes_todo_with_option(self):
        assert remove_draft_annotations(r"\todo[inline]{fix}") == ""

    def test_removes_hl(self):
        assert remove_draft_annotations(r"\hl{highlighted}") == ""

    def test_removes_note(self):
        assert remove_draft_annotations(r"\note{a note}") == ""

    def test_preserves_surrounding_text(self):
        result = remove_draft_annotations(r"before \todo{x} after")
        assert "before" in result and "after" in result

    def test_removes_todo_with_nested_braces(self):
        assert remove_draft_annotations(r"\todo{fix \textbf{this}}") == ""

    def test_removes_todo_with_cite(self):
        assert remove_draft_annotations(r"\todo{see \cite{smith2020}}") == ""

    def test_removes_hl_with_nested_braces(self):
        assert remove_draft_annotations(r"\hl{some \emph{important} text}") == ""


class TestRemoveCommentEnvironments:
    def test_removes_comment_block(self):
        src = "before\n\\begin{comment}\nhidden\n\\end{comment}\nafter"
        result = remove_comment_environments(src)
        assert "hidden" not in result
        assert "before" in result and "after" in result

    def test_removes_iffalse_block(self):
        src = "before\n\\iffalse\nhidden\n\\fi\nafter"
        result = remove_comment_environments(src)
        assert "hidden" not in result
        assert "before" in result and "after" in result


class TestEnsurePdfoutput:
    def test_injects_when_missing(self):
        src = "\\documentclass{article}"
        result = ensure_pdfoutput(src)
        assert result.startswith("\\pdfoutput=1")

    def test_no_duplicate_when_present(self):
        src = "\\pdfoutput=1\n\\documentclass{article}"
        result = ensure_pdfoutput(src)
        assert result.count("\\pdfoutput=1") == 1


class TestRemoveDraftPackages:
    def test_removes_todonotes(self):
        src = "\\usepackage{todonotes}\n\\usepackage{amsmath}"
        result = remove_draft_packages(src)
        assert "todonotes" not in result
        assert "amsmath" in result

    def test_removes_comment_package(self):
        src = "\\usepackage{comment}"
        assert "comment" not in remove_draft_packages(src)


# ── deps.py ───────────────────────────────────────────────────────────────────

class TestFindUsedImages:
    def _run(self, src, tmp_path):
        img = tmp_path / "fig.png"
        img.write_bytes(b"PNG")
        return find_used_images([src], [tmp_path], tmp_path)

    def test_finds_includegraphics(self, tmp_path):
        paths, refs = self._run(r"\includegraphics{fig}", tmp_path)
        assert any("fig" in str(p) for p in paths)

    def test_finds_overpic(self, tmp_path):
        paths, refs = self._run(r"\begin{overpic}{fig}\end{overpic}", tmp_path)
        assert any("fig" in str(p) for p in paths)

    def test_ignores_commented_out(self, tmp_path):
        paths, refs = self._run(r"% \includegraphics{fig}", tmp_path)
        assert len(paths) == 0

    def test_graphicspath(self, tmp_path):
        fig_dir = tmp_path / "figures"
        fig_dir.mkdir()
        (fig_dir / "fig.png").write_bytes(b"PNG")
        src = r"\graphicspath{{figures/}}" + "\n" + r"\includegraphics{fig}"
        paths, refs = find_used_images([src], [tmp_path], tmp_path)
        assert any("fig.png" in str(p) for p in paths)


class TestFindUsedStyleFiles:
    def test_finds_usepackage(self):
        used = find_used_style_files([r"\usepackage{imsart}"])
        assert "imsart.sty" in used

    def test_finds_documentclass(self):
        used = find_used_style_files([r"\documentclass{imsart}"])
        assert "imsart.cls" in used
        assert "imsart.sty" in used  # both extensions tried

    def test_ignores_commented(self):
        used = find_used_style_files([r"% \usepackage{imsart}"])
        assert "imsart.sty" not in used


# ── config.py ─────────────────────────────────────────────────────────────────

class TestApplyConfig:
    def test_commands_to_delete(self):
        result = apply_config(r"\revision{old text}", {"commands_to_delete": ["revision"]})
        assert "old text" not in result

    def test_commands_to_delete_nested_braces(self):
        result = apply_config(
            r"before \deleted{see \cite{smith2020} too} after",
            {"commands_to_delete": ["deleted"]},
        )
        assert "before  after" in result
        assert "smith2020" not in result
        assert r"\deleted" not in result
        assert r"\cite" not in result

    def test_commands_to_delete_nested_textbf(self):
        result = apply_config(
            r"\deleted{remove \textbf{this} too}",
            {"commands_to_delete": ["deleted"]},
        )
        assert result.strip() == ""

    def test_commands_to_delete_with_optional_arg(self):
        result = apply_config(
            r"\revision[v2]{old} kept",
            {"commands_to_delete": ["revision"]},
        )
        assert "old" not in result
        assert "kept" in result

    def test_commands_to_delete_bare_switch(self):
        result = apply_config(r"a \deprecated b", {"commands_to_delete": ["deprecated"]})
        assert r"\deprecated" not in result
        assert "a " in result and " b" in result

    def test_commands_to_delete_multiple_occurrences(self):
        result = apply_config(
            r"\del{first} middle \del{second}",
            {"commands_to_delete": ["del"]},
        )
        assert "first" not in result
        assert "second" not in result
        assert "middle" in result

    def test_commands_to_unwrap(self):
        result = apply_config(r"{\color{red} keep this}", {"commands_to_unwrap": ["color{red}"]})
        assert "keep this" in result
        assert r"\color{red}" not in result

    def test_commands_to_unwrap_with_braces(self):
        result = apply_config(r"\textcolor{red}{keep this}", {"commands_to_unwrap": ["textcolor{red}"]})
        assert "keep this" in result
        assert r"\textcolor" not in result

    def test_commands_to_unwrap_nested_braces(self):
        result = apply_config(
            r"\added{see \cite{smith2020}}",
            {"commands_to_unwrap": ["added"]},
        )
        assert r"see \cite{smith2020}" in result
        assert r"\added" not in result

    def test_commands_to_unwrap_with_emph_inside(self):
        result = apply_config(
            r"before \added{some \emph{important} text} after",
            {"commands_to_unwrap": ["added"]},
        )
        assert r"some \emph{important} text" in result
        assert r"\added" not in result

    def test_commands_to_unwrap_no_arg(self):
        result = apply_config(r"a \added b", {"commands_to_unwrap": ["added"]})
        assert r"\added" not in result
        assert "a " in result and " b" in result

    def test_environments_to_delete(self):
        src = "before\n\\begin{response}\nhidden\n\\end{response}\nafter"
        result = apply_config(src, {"environments_to_delete": ["response"]})
        assert "hidden" not in result
        assert "before" in result

    def test_replacements(self):
        result = apply_config(
            r"\added{new text}",
            {"replacements": [{"pattern": r"\\added\{([^}]*)\}", "replacement": r"\1"}]}
        )
        assert result == "new text"


# ── bibtex.py ─────────────────────────────────────────────────────────────────

try:
    import importlib.util
    HAS_BIBTEXPARSER = importlib.util.find_spec("bibtexparser") is not None
except Exception:
    HAS_BIBTEXPARSER = False


@pytest.mark.skipif(not HAS_BIBTEXPARSER, reason="bibtexparser not installed")
class TestNormalizeBibtex:
    BIB = """@article{smith2020,
  author = {Smith, John},
  title = {A Paper},
  journal = {Journal},
  year = {2020},
  abstract = {private},
  file = {smith.pdf},
}"""

    def test_removes_private_fields(self):
        result = normalize_bibtex(self.BIB)
        assert "abstract" not in result
        assert "file" not in result

    def test_preserves_required_fields(self):
        result = normalize_bibtex(self.BIB)
        assert "Smith, John" in result
        assert "A Paper" in result


# ── Full pipeline integration test ────────────────────────────────────────────

class TestFullPipeline:
    def _make_zip(self, files: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def _run(self, files: dict, **kwargs) -> list[str]:
        import tempfile
        from converter import convert
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
            f.write(self._make_zip(files))
            inp = Path(f.name)
        out = inp.with_stem('out')
        convert(inp, out, **kwargs)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        inp.unlink()
        out.unlink()
        return names

    def test_keeps_main_and_used_image(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics{fig}\end{document}',
            'fig.png': b'PNG',
            'unused.png': b'PNG',
        }
        names = self._run(files)
        assert 'main.tex' in names
        assert 'fig.png' in names
        assert 'unused.png' not in names

    def test_removes_unused_tex(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hello\end{document}',
            'unused.tex': r'\section{unused}',
        }
        names = self._run(files)
        assert 'main.tex' in names
        assert 'unused.tex' not in names

    def test_removes_junk_files(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hello\end{document}',
            'main.aux': 'aux',
            'main.log': 'log',
            '.DS_Store': 'junk',
        }
        names = self._run(files)
        assert 'main.aux' not in names
        assert '.DS_Store' not in names

    def test_removes_hidden_files(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hello\end{document}',
            '.hidden': 'secret',
        }
        names = self._run(files)
        assert '.hidden' not in names

    def test_subfile_included(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{subfiles}\begin{document}\subfile{sub}\end{document}',
            'sub.tex': r'\documentclass[main]{subfiles}\begin{document}sub content\end{document}',
        }
        names = self._run(files)
        assert 'sub.tex' in names

    def test_commented_subfile_excluded(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}% \subfile{sub}\end{document}',
            'sub.tex': r'\documentclass[main]{subfiles}\begin{document}sub\end{document}',
        }
        names = self._run(files, main_hint='main.tex')
        assert 'sub.tex' not in names


class TestPreflightChecks:
    """Pre-flight compliance checks added in Direction 4."""

    def _make_zip(self, files: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            for name, content in files.items():
                zf.writestr(name, content if isinstance(content, str) else content)
        return buf.getvalue()

    def _run(self, files: dict, **kwargs):
        import tempfile
        from converter import convert
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
            f.write(self._make_zip(files))
            inp = Path(f.name)
        out = inp.with_stem('preflight_out')
        captured = io.StringIO()
        sys.stdout = captured
        try:
            issues = convert(inp, out, **kwargs)
        finally:
            sys.stdout = sys.__stdout__
        inp.unlink()
        if out.exists():
            out.unlink()
        return issues, captured.getvalue()

    def test_minted_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{minted}\begin{document}hi\end{document}',
        }
        issues, output = self._run(files)
        assert any('minted' in e for e in issues.errors)
        assert '[error]' in output

    def test_pythontex_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{pythontex}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('pythontex' in e for e in issues.errors)

    def test_commented_minted_not_flagged(self):
        files = {
            'main.tex': "\\documentclass{article}\n% \\usepackage{minted}\n\\begin{document}hi\\end{document}",
        }
        issues, _ = self._run(files)
        assert not any('minted' in e for e in issues.errors)

    def test_biblatex_without_bbl_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{biblatex}\addbibresource{refs.bib}'
                        r'\begin{document}hi\end{document}',
            'refs.bib': '@misc{x, title={t}}',
        }
        issues, _ = self._run(files)
        assert any('biblatex' in w and '.bbl' in w for w in issues.warnings)

    def test_biblatex_with_bbl_does_not_warn(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{biblatex}\addbibresource{refs.bib}'
                        r'\begin{document}hi\end{document}',
            'refs.bib': '@misc{x, title={t}}',
            'main.bbl': r'\begin{thebibliography}{1}\end{thebibliography}',
        }
        issues, _ = self._run(files)
        assert not any('biblatex' in w and '.bbl' in w for w in issues.warnings)

    def test_filename_with_spaces_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics{my fig}\end{document}',
            'my fig.png': b'PNG',
        }
        issues, _ = self._run(files)
        assert any('spaces' in w for w in issues.warnings)

    def test_filename_with_non_ascii_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics{café}\end{document}',
            'café.png': b'PNG',
        }
        issues, _ = self._run(files)
        assert any('non-ASCII' in w for w in issues.warnings)

    def test_clean_project_has_no_errors(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hello\end{document}',
        }
        issues, _ = self._run(files)
        assert issues.errors == []


class TestDryRun:
    def _make_zip(self, files: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            for name, content in files.items():
                zf.writestr(name, content if isinstance(content, str) else content)
        return buf.getvalue()

    def _run_dry(self, files: dict) -> tuple[list[str], str]:
        """Run convert with dry_run=True; return (output_zip_names_or_empty, stdout)."""
        import tempfile
        from converter import convert
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
            f.write(self._make_zip(files))
            inp = Path(f.name)
        out = inp.with_stem('out_dry')
        captured = io.StringIO()
        sys.stdout = captured
        try:
            convert(inp, out, dry_run=True)
        finally:
            sys.stdout = sys.__stdout__
        inp.unlink()
        names = []
        if out.exists():
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
            out.unlink()
        return names, captured.getvalue()

    def test_no_output_zip_created(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hello\end{document}',
            'unused.png': b'PNG',
        }
        names, _ = self._run_dry(files)
        assert names == []

    def test_reports_files_to_remove(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hello\end{document}',
            'unused.png': b'PNG',
        }
        _, output = self._run_dry(files)
        assert 'remove' in output
        assert 'unused.png' in output

    def test_reports_tex_to_process(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hello\end{document}',
        }
        _, output = self._run_dry(files)
        assert 'would process (tex)' in output
        assert 'main.tex' in output

    def test_dry_run_summary_line(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hello\end{document}',
        }
        _, output = self._run_dry(files)
        assert '[dry-run]' in output
        assert 'No output written' in output


class TestDemoFlag:
    def test_demo_dry_run(self, tmp_path):
        """--demo --dry-run should print dry-run output and not create any output zip."""
        from converter import convert
        from importlib import resources
        import converter as conv_module

        ref = resources.files(conv_module).joinpath('demo_project.zip')
        demo_zip = Path(str(ref))
        assert demo_zip.exists(), "demo_project.zip not found in package"

        out = tmp_path / 'demo_arxiv.zip'
        captured = io.StringIO()
        sys.stdout = captured
        try:
            convert(demo_zip, out, dry_run=True)
        finally:
            sys.stdout = sys.__stdout__

        assert not out.exists()
        output = captured.getvalue()
        assert '[dry-run]' in output
        assert 'No output written' in output
