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
from pipeline.deps import find_included_tex, find_used_images, find_used_bib_files, find_used_style_files
from pipeline.config import apply_config, load_config
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

    def test_commands_to_unwrap(self):
        result = apply_config(r"{\color{red} keep this}", {"commands_to_unwrap": ["color{red}"]})
        assert "keep this" in result
        assert r"\color{red}" not in result

    def test_commands_to_unwrap_with_braces(self):
        result = apply_config(r"\textcolor{red}{keep this}", {"commands_to_unwrap": ["textcolor{red}"]})
        assert "keep this" in result
        assert r"\textcolor" not in result

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
    import bibtexparser
    HAS_BIBTEXPARSER = True
except ImportError:
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
