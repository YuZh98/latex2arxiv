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
from pipeline.deps import find_used_images, find_used_style_files, find_used_bib_files
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

    def test_normalizes_pdfoutput_zero(self):
        src = "\\pdfoutput=0\n\\documentclass{article}"
        result = ensure_pdfoutput(src)
        assert "\\pdfoutput=0" not in result
        assert result.count("\\pdfoutput=1") == 1
        assert result.startswith("\\pdfoutput=1")

    def test_normalizes_pdfoutput_with_spaces(self):
        src = "\\pdfoutput = 0\n\\documentclass{article}"
        result = ensure_pdfoutput(src)
        assert "\\pdfoutput = 0" not in result
        assert result.count("\\pdfoutput=1") == 1

    def test_strips_late_pdfoutput_override(self):
        # User had \pdfoutput=0 mid-file; result should not contain any =0 declaration.
        src = "\\documentclass{article}\n\\pdfoutput=0\n\\begin{document}hi\\end{document}"
        result = ensure_pdfoutput(src)
        assert "\\pdfoutput=0" not in result
        assert result.startswith("\\pdfoutput=1")

    def test_normalizes_pdfoutput_two(self):
        src = "\\pdfoutput=2\n\\documentclass{article}"
        result = ensure_pdfoutput(src)
        assert "\\pdfoutput=2" not in result
        assert result.startswith("\\pdfoutput=1")


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


class TestFindUsedBibFiles:
    def test_finds_bibliography(self):
        used = find_used_bib_files([r"\bibliography{refs}"])
        assert "refs.bib" in used

    def test_finds_addbibresource(self):
        used = find_used_bib_files([r"\addbibresource{refs.bib}"])
        assert "refs.bib" in used

    def test_addbibresource_strips_subdirectory(self):
        used = find_used_bib_files([r"\addbibresource{bib/refs.bib}"])
        assert used == {"refs.bib"}

    def test_bibliography_strips_subdirectory(self):
        used = find_used_bib_files([r"\bibliography{bib/refs}"])
        assert used == {"refs.bib"}

    def test_ignores_commented(self):
        used = find_used_bib_files([r"% \addbibresource{refs.bib}"])
        assert used == set()


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

    def test_biblatex_addbibresource_in_subdirectory(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{biblatex}'
                        r'\addbibresource{bib/refs.bib}'
                        r'\begin{document}\cite{x}\printbibliography\end{document}',
            'bib/refs.bib': '@misc{x, title={t}}',
        }
        names = self._run(files)
        assert 'main.tex' in names
        assert 'bib/refs.bib' in names

    def test_00readme_preserved_at_root(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
            '00README': 'arxiv processor hints',
            '00README.XXX': 'aux file list',
        }
        names = self._run(files)
        assert '00README' in names
        assert '00README.XXX' in names

    def test_00readme_in_subdir_not_preserved(self):
        # 00README is only meaningful at root; subdirectory copies are not arXiv-recognized
        # and can be safely pruned along with other non-whitelisted files.
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
            'sub/00README': 'not at root',
        }
        names = self._run(files)
        assert 'sub/00README' not in names

    def test_pdfoutput_zero_normalized_in_output(self):
        # End-to-end: a user-supplied \pdfoutput=0 must become =1 in the converted main.tex.
        import tempfile
        from converter import convert
        files = {
            'main.tex': "\\pdfoutput=0\n\\documentclass{article}\n"
                        "\\begin{document}hi\\end{document}",
        }
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
            f.write(self._make_zip(files))
            inp = Path(f.name)
        out = inp.with_stem('pdfoutput_out')
        convert(inp, out)
        with zipfile.ZipFile(out) as zf:
            converted = zf.read('main.tex').decode('utf-8')
        inp.unlink()
        out.unlink()
        assert '\\pdfoutput=0' not in converted
        assert '\\pdfoutput=1' in converted


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

    def test_psfig_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{psfig}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('psfig' in e for e in issues.errors)

    def test_commented_psfig_not_flagged(self):
        files = {
            'main.tex': "\\documentclass{article}\n% \\usepackage{psfig}\n\\begin{document}hi\\end{document}",
        }
        issues, _ = self._run(files)
        assert not any('psfig' in e for e in issues.errors)

    def test_psfig_with_options_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage[draft]{psfig}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('psfig' in e for e in issues.errors)

    def test_psfig_co_listed_with_other_packages_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{graphicx,psfig}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('psfig' in e for e in issues.errors)

    def test_xr_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{xr}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('\\usepackage{xr}' in w for w in issues.warnings)

    def test_xr_hyper_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{xr-hyper}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        # Message must name xr-hyper specifically, not just "xr",
        # so the user doesn't dismiss it thinking it's about a different package.
        assert any('\\usepackage{xr-hyper}' in w for w in issues.warnings)

    def test_xrcolor_not_flagged(self):
        # \b xr \b should not match unrelated packages whose names start with "xr".
        files = {
            'main.tex': r'\documentclass{article}\usepackage{xcolor}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert not any('xr' in w and 'arXiv' in w for w in issues.warnings)

    def test_printindex_without_ind_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{makeidx}\makeindex'
                        r'\begin{document}hi\printindex\end{document}',
        }
        issues, _ = self._run(files)
        assert any('\\printindex' in w and '.ind' in w for w in issues.warnings)

    def test_printindex_with_ind_silent(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{makeidx}\makeindex'
                        r'\begin{document}hi\printindex\end{document}',
            'main.ind': r'\begin{theindex}\end{theindex}',
        }
        issues, _ = self._run(files)
        assert not any('\\printindex' in w and '.ind' in w for w in issues.warnings)

    def test_printglossary_without_gls_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{glossaries}\makeglossaries'
                        r'\begin{document}hi\printglossary\end{document}',
        }
        issues, _ = self._run(files)
        assert any('\\printglossary' in w and '.gls' in w for w in issues.warnings)

    def test_printglossaries_plural_form(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{glossaries}\makeglossaries'
                        r'\begin{document}hi\printglossaries\end{document}',
        }
        issues, _ = self._run(files)
        assert any('\\printglossary' in w and '.gls' in w for w in issues.warnings)

    def test_printnomenclature_without_nls_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{nomencl}\makenomenclature'
                        r'\begin{document}hi\printnomenclature\end{document}',
        }
        issues, _ = self._run(files)
        assert any('\\printnomenclature' in w and '.nls' in w for w in issues.warnings)

    def test_main_in_subdirectory_warns(self):
        # Two top-level entries in the zip prevent the unwrap, leaving main in 'paper/'.
        files = {
            'paper/main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
            'figures/.keep': '',
        }
        issues, _ = self._run(files)
        assert any('not at the submission root' in w for w in issues.warnings)

    def test_main_at_root_no_warn(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert not any('not at the submission root' in w for w in issues.warnings)

    def test_single_top_level_dir_unwraps_cleanly(self):
        # Single 'project/' directory at top should be unwrapped, leaving main at root.
        files = {
            'project/main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert not any('not at the submission root' in w for w in issues.warnings)

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


class TestSummary:
    def _make_zip(self, files: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            for name, content in files.items():
                zf.writestr(name, content if isinstance(content, str) else content)
        return buf.getvalue()

    def _run(self, files: dict, dry_run: bool = False) -> str:
        import tempfile
        from converter import convert
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
            f.write(self._make_zip(files))
            inp = Path(f.name)
        out = inp.with_stem('summary_out')
        captured = io.StringIO()
        sys.stdout = captured
        try:
            convert(inp, out, dry_run=dry_run)
        finally:
            sys.stdout = sys.__stdout__
        inp.unlink()
        if out.exists():
            out.unlink()
        return captured.getvalue()

    def test_summary_line_counts_match(self):
        # Kept: main.tex, fig.png. Removed: unused.tex, unused.png, .DS_Store, main.aux. = 4 removed, 2 kept.
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics{fig}\end{document}',
            'fig.png': b'PNG',
            'unused.tex': r'\section{x}',
            'unused.png': b'PNG',
            '.DS_Store': b'junk',
            'main.aux': 'aux',
        }
        output = self._run(files)
        assert 'Summary: 4 removed, 2 kept' in output
        assert 'MB →' in output
        assert '0 errors' in output

    def test_summary_dry_run_skips_size(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
            'unused.tex': r'\section{x}',
        }
        output = self._run(files, dry_run=True)
        assert 'Summary: 1 removed, 1 kept' in output
        # Dry-run has no output zip; size segment is omitted.
        assert 'MB →' not in output

    def test_summary_pluralization(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{minted}\begin{document}hi\end{document}',
        }
        output = self._run(files)
        # 1 minted error → "1 error" (singular). 0 warnings → "0 warnings" (plural).
        assert '1 error,' in output
        assert '0 warnings' in output


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
