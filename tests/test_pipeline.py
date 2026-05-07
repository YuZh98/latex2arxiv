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
from pipeline.config import apply_config, load_config, _parse_simple_yaml, HAS_YAML
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

    def test_preserves_verb_inline(self):
        src = r"Use \verb|%foo| for percent"
        result = strip_comments(src)
        assert r"\verb|%foo|" in result

    def test_preserves_verb_with_other_delimiter(self):
        src = r"Use \verb+\todo{x}+ here"
        result = strip_comments(src)
        assert r"\verb+\todo{x}+" in result

    def test_preserves_verb_star(self):
        src = r"Use \verb*|%foo| for percent"
        result = strip_comments(src)
        assert r"\verb*|%foo|" in result

    def test_preserves_lstinline(self):
        src = r"Use \lstinline|%foo| for code"
        result = strip_comments(src)
        assert r"\lstinline|%foo|" in result

    def test_preserves_mintinline(self):
        src = r"Use \mintinline{python}|%foo| for code"
        result = strip_comments(src)
        assert r"\mintinline{python}|%foo|" in result

    def test_preserves_lstinline_braces(self):
        src = r"Use \lstinline{%foo} for code"
        result = strip_comments(src)
        assert "%foo" in result

    def test_preserves_mintinline_braces(self):
        src = r"Use \mintinline{python}{%foo} for code"
        result = strip_comments(src)
        assert "%foo" in result

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

    def test_preserves_verb_containing_todo(self):
        src = r"Use \verb|\todo{x}| in code"
        result = remove_draft_annotations(src)
        assert r"\verb|\todo{x}|" in result

    def test_preserves_lstinline_braces_containing_todo(self):
        src = r"Use \lstinline{\todo{x}} in code"
        result = remove_draft_annotations(src)
        assert r"\todo{x}" in result

    def test_preserves_mintinline_braces_containing_hl(self):
        src = r"Use \mintinline{python}{\hl{x}} in code"
        result = remove_draft_annotations(src)
        assert r"\hl{x}" in result


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

class TestLoadConfig:
    def _write(self, tmp_path, content: str):
        p = tmp_path / "config.yaml"
        p.write_text(content)
        return p

    def test_known_keys_no_warning(self, tmp_path, capsys):
        p = self._write(tmp_path, "commands_to_delete:\n  - revision\n")
        load_config(p)
        out = capsys.readouterr().out
        assert 'unknown config key' not in out

    def test_unknown_key_warns(self, tmp_path, capsys):
        # Singular form is a common typo and should not silently no-op.
        p = self._write(tmp_path, "command_to_delete:\n  - revision\n")
        load_config(p)
        out = capsys.readouterr().out
        assert 'unknown config key' in out
        assert 'command_to_delete' in out

    def test_warning_lists_expected_keys(self, tmp_path, capsys):
        p = self._write(tmp_path, "typo_key:\n  - x\n")
        load_config(p)
        out = capsys.readouterr().out
        assert 'commands_to_delete' in out
        assert 'commands_to_unwrap' in out
        assert 'environments_to_delete' in out
        assert 'replacements' in out

    def test_empty_config_no_warning(self, tmp_path, capsys):
        p = self._write(tmp_path, "")
        load_config(p)
        assert 'unknown config key' not in capsys.readouterr().out

    @pytest.mark.skipif(not HAS_YAML, reason="fallback parser silently drops non-dict roots")
    def test_top_level_list_warns_and_returns_empty(self, tmp_path, capsys):
        # User wrote a list at the root instead of a mapping. Only PyYAML's safe_load
        # actually returns a list here; the fallback parser ignores non-mapping syntax.
        p = self._write(tmp_path, "- foo\n- bar\n")
        result = load_config(p)
        assert result == {}
        assert 'config root must be a mapping' in capsys.readouterr().out

    @pytest.mark.skipif(not HAS_YAML, reason="fallback parser silently drops non-dict roots")
    def test_top_level_string_warns_and_returns_empty(self, tmp_path, capsys):
        p = self._write(tmp_path, "just_a_string\n")
        result = load_config(p)
        assert result == {}
        assert 'config root must be a mapping' in capsys.readouterr().out

    def test_fallback_parser_handles_bundled_template(self):
        # The bundled template ships with everything commented out, so both the
        # PyYAML and the fallback parser should produce {}. Guards against
        # template syntax that only PyYAML accepts.
        template = Path(__file__).parent.parent / 'arxiv_config.yaml'
        result = _parse_simple_yaml(template.read_text(encoding='utf-8'))
        assert result == {}


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

    def test_replacements_bad_regex_does_not_crash(self, capsys):
        # Unbalanced bracket — should warn and skip, not raise.
        result = apply_config(
            r"\added{new text}",
            {"replacements": [{"pattern": r"[unclosed", "replacement": ""}]}
        )
        assert result == r"\added{new text}"
        out = capsys.readouterr().out
        assert 'invalid regex' in out
        assert '[unclosed' in out

    def test_replacements_bad_rule_does_not_block_subsequent(self, capsys):
        # First rule is malformed; second should still apply.
        result = apply_config(
            r"\added{new text}",
            {"replacements": [
                {"pattern": r"[unclosed", "replacement": ""},
                {"pattern": r"\\added\{([^}]*)\}", "replacement": r"\1"},
            ]}
        )
        assert result == "new text"
        out = capsys.readouterr().out
        assert 'rule #0' in out

    def test_replacements_bad_rule_index_in_warning(self, capsys):
        # Second rule (index 1) is bad; warning should name index 1.
        apply_config(
            "text",
            {"replacements": [
                {"pattern": r"x", "replacement": "y"},
                {"pattern": r"(?P<", "replacement": ""},
            ]}
        )
        out = capsys.readouterr().out
        assert 'rule #1' in out

    def test_none_value_for_known_keys_does_not_crash(self):
        # YAML "commands_to_delete:" with no value parses to None.
        result = apply_config(
            r"\added{x}",
            {
                "commands_to_delete": None,
                "commands_to_unwrap": None,
                "environments_to_delete": None,
                "replacements": None,
            },
        )
        assert result == r"\added{x}"

    def test_replacements_non_dict_rule_skipped(self, capsys):
        # YAML list with a string item where a mapping was expected.
        result = apply_config(
            "hello",
            {"replacements": ["just a string", {"pattern": "h", "replacement": "H"}]},
        )
        assert result == "Hello"
        out = capsys.readouterr().out
        assert 'rule #0' in out
        assert 'expected a mapping' in out
        assert 'str' in out

    def test_replacements_none_rule_skipped(self, capsys):
        result = apply_config(
            "hello",
            {"replacements": [None, {"pattern": "h", "replacement": "H"}]},
        )
        assert result == "Hello"
        out = capsys.readouterr().out
        assert 'rule #0' in out
        assert 'NoneType' in out

    def test_replacements_missing_pattern_skipped(self, capsys):
        # Without the empty-pattern guard, re.sub('', 'X', 'hi') corrupts the source.
        result = apply_config(
            "hi",
            {"replacements": [{"replacement": "X"}]},
        )
        assert result == "hi"
        out = capsys.readouterr().out
        assert 'rule #0' in out
        assert "missing or empty 'pattern'" in out

    def test_replacements_empty_pattern_skipped(self, capsys):
        result = apply_config(
            "hi",
            {"replacements": [{"pattern": "", "replacement": "X"}]},
        )
        assert result == "hi"
        assert "missing or empty 'pattern'" in capsys.readouterr().out

    # ── Definition-context skip ───────────────────────────────────────────────
    # When a command rule matches the command's name inside its own
    # definition (\newcommand{\foo}{...}, \def\foo, \let\foo\bar, etc.), we
    # leave the match alone so the definition isn't mangled. Body usages of
    # the same command should still be transformed normally.

    def test_unwrap_skips_newcommand_definition(self):
        src = (
            r"\newcommand{\added}[1]{\textcolor{blue}{#1}}" "\n"
            r"\added{body usage}"
        )
        result = apply_config(src, {"commands_to_unwrap": ["\\added"]})
        # Definition preserved verbatim
        assert r"\newcommand{\added}[1]{\textcolor{blue}{#1}}" in result
        # Body usage unwrapped
        assert "body usage" in result and r"\added{body usage}" not in result

    def test_unwrap_skips_renewcommand_definition(self):
        src = r"\renewcommand{\added}[1]{#1}" "\n" r"\added{x}"
        result = apply_config(src, {"commands_to_unwrap": ["\\added"]})
        assert r"\renewcommand{\added}[1]{#1}" in result
        assert "\nx" in result

    def test_unwrap_skips_providecommand_definition(self):
        src = r"\providecommand{\added}[1]{#1}" "\n" r"\added{x}"
        result = apply_config(src, {"commands_to_unwrap": ["\\added"]})
        assert r"\providecommand{\added}[1]{#1}" in result
        assert "\nx" in result

    def test_unwrap_skips_def_definition(self):
        src = r"\def\added#1{\textcolor{blue}{#1}}" "\n" r"\added{x}"
        result = apply_config(src, {"commands_to_unwrap": ["\\added"]})
        assert r"\def\added#1{\textcolor{blue}{#1}}" in result
        assert "\nx" in result

    def test_unwrap_skips_protected_def_definition(self):
        src = r"\protected\def\added#1{#1}" "\n" r"\added{x}"
        result = apply_config(src, {"commands_to_unwrap": ["\\added"]})
        assert r"\protected\def\added#1{#1}" in result
        assert "\nx" in result

    def test_unwrap_skips_let_definition(self):
        src = r"\let\added\foo" "\n" r"\added{x}"
        result = apply_config(src, {"commands_to_unwrap": ["\\added"]})
        assert r"\let\added\foo" in result
        assert "\nx" in result

    def test_unwrap_skips_declarerobustcommand(self):
        src = r"\DeclareRobustCommand\added[1]{#1}" "\n" r"\added{x}"
        result = apply_config(src, {"commands_to_unwrap": ["\\added"]})
        assert r"\DeclareRobustCommand\added[1]{#1}" in result
        assert "\nx" in result

    def test_delete_skips_newcommand_definition(self):
        # Same protection for commands_to_delete (uses remove_cmd internally).
        src = r"\newcommand{\deleted}[1]{}" "\n" r"\deleted{old text}"
        result = apply_config(src, {"commands_to_delete": ["\\deleted"]})
        assert r"\newcommand{\deleted}[1]{}" in result
        # Body usage was deleted (text gone)
        assert "old text" not in result

    def test_unwrap_handles_whitespace_in_def_form(self):
        # \def\added (no space) and \def \added (with space) both common.
        src = r"\def \added #1{#1}" "\n" r"\added{x}"
        result = apply_config(src, {"commands_to_unwrap": ["\\added"]})
        assert r"\def \added #1{#1}" in result
        assert "\nx" in result

    def test_unwrap_does_not_skip_when_prefix_too_far_back(self):
        # If the definition prefix is more than ~40 chars before the match,
        # it's likely unrelated context and we transform normally.
        src = "\\newcommand{\\foo}{x}" + " " * 60 + "\\added{y}"
        result = apply_config(src, {"commands_to_unwrap": ["\\added"]})
        assert "y" in result and r"\added{y}" not in result


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

    def test_fontspec_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{fontspec}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('fontspec' in e for e in issues.errors)

    def test_unicode_math_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{unicode-math}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('unicode-math' in e for e in issues.errors)

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

    def test_macosx_metadata_sibling_does_not_block_unwrap(self):
        # macOS-created zips contain a __MACOSX/ metadata sibling alongside
        # the project directory. The unwrap heuristic should ignore it so
        # main.tex still resolves to the submission root.
        files = {
            'project/main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
            '__MACOSX/project/._main.tex': 'macos resource fork garbage',
        }
        issues, _ = self._run(files)
        assert not any('not at the submission root' in w for w in issues.warnings)

    def test_ds_store_sibling_does_not_block_unwrap(self):
        files = {
            'project/main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
            '.DS_Store': 'finder metadata',
        }
        issues, _ = self._run(files)
        assert not any('not at the submission root' in w for w in issues.warnings)

    def test_non_utf8_tex_emits_warning(self):
        # Latin-1 encoded byte 0xE9 (é) is invalid UTF-8; the strict bytes
        # decoder raises UnicodeDecodeError and we surface a per-file warning
        # so users know which source needs re-saving.
        files = {
            'main.tex': '\\documentclass{article}\\begin{document}café\\end{document}'.encode('latin-1'),
        }
        issues, _ = self._run(files)
        assert any('not valid UTF-8' in w for w in issues.warnings)
        assert any('main.tex' in w for w in issues.warnings)

    def test_utf8_tex_does_not_emit_encoding_warning(self):
        # Same accented content but encoded as UTF-8 — no warning should fire.
        files = {
            'main.tex': '\\documentclass{article}\\begin{document}café\\end{document}'.encode('utf-8'),
        }
        issues, _ = self._run(files)
        assert not any('not valid UTF-8' in w for w in issues.warnings)

    def test_zip_slip_member_aborts_extraction(self, tmp_path, capsys):
        # Build a zip with a member whose path tries to escape via '..'.
        # The pre-extraction validation must abort before anything is written.
        from converter import convert
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('main.tex', r'\documentclass{article}\begin{document}hi\end{document}')
            zf.writestr('../escape.txt', 'malicious content trying to land outside root')
        inp = tmp_path / 'malicious.zip'
        inp.write_bytes(buf.getvalue())
        out = tmp_path / 'out.zip'
        with pytest.raises(SystemExit) as excinfo:
            convert(inp, out)
        assert excinfo.value.code == 1
        captured = capsys.readouterr().out
        assert 'escapes the extraction root' in captured
        assert "'../escape.txt'" in captured
        # Output zip must not have been created.
        assert not out.exists()

    def test_zip_slip_absolute_path_aborts_extraction(self, tmp_path, capsys):
        # Same protection should catch a member with an absolute path. Python's
        # zipfile would otherwise sanitize the leading slash and write under
        # root, but our pre-validation is stricter — defensive is good.
        from converter import convert
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('main.tex', r'\documentclass{article}\begin{document}hi\end{document}')
            zf.writestr('/etc/passwd', 'malicious absolute-path member')
        inp = tmp_path / 'malicious_abs.zip'
        inp.write_bytes(buf.getvalue())
        out = tmp_path / 'out.zip'
        with pytest.raises(SystemExit) as excinfo:
            convert(inp, out)
        assert excinfo.value.code == 1
        captured = capsys.readouterr().out
        assert 'escapes the extraction root' in captured
        assert not out.exists()

    def test_zip_with_no_tex_exits_with_clear_message(self, tmp_path, capsys):
        # A zip containing files but no .tex should exit 1 with a clear message,
        # not raise a Python traceback.
        from converter import convert
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('README.md', '# This is not a TeX project')
            zf.writestr('image.png', b'PNG')
        inp = tmp_path / 'no_tex.zip'
        inp.write_bytes(buf.getvalue())
        out = tmp_path / 'out.zip'
        with pytest.raises(SystemExit) as excinfo:
            convert(inp, out)
        assert excinfo.value.code == 1
        captured = capsys.readouterr().out
        assert 'no .tex file found' in captured
        assert not out.exists()

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

    # ── New error checks ──────────────────────────────────────────────────────

    def test_svg_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{svg}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('svg' in e for e in issues.errors)

    def test_svg_with_options_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage[inkscapelatex=false]{svg}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('svg' in e for e in issues.errors)

    def test_commented_svg_not_flagged(self):
        files = {
            'main.tex': "\\documentclass{article}\n% \\usepackage{svg}\n\\begin{document}hi\\end{document}",
        }
        issues, _ = self._run(files)
        assert not any('svg' in e for e in issues.errors)

    def test_svg_substring_in_other_package_not_flagged(self):
        # 'svg' as a substring of an unrelated package name must not trigger
        # the Inkscape-specific error.
        files = {
            'main.tex': r'\documentclass{article}\usepackage{notsvgpkg}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert not any('Inkscape' in e for e in issues.errors)

    def test_pst_pdf_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{pst-pdf}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('pst-pdf' in e for e in issues.errors)

    def test_auto_pst_pdf_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{auto-pst-pdf}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('auto-pst-pdf' in e for e in issues.errors)

    def test_auto_pst_pdf_does_not_double_flag(self):
        # 'pst-pdf' is a substring of 'auto-pst-pdf'. Longest-first alternation
        # in the regex must match auto-pst-pdf as a single error, not both.
        files = {
            'main.tex': r'\documentclass{article}\usepackage{auto-pst-pdf}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        pst_errors = [e for e in issues.errors if 'pst-pdf' in e]
        assert len(pst_errors) == 1

    def test_tikz_externalize_without_figures_is_error(self):
        files = {
            'main.tex': r'\documentclass{article}\usepackage{tikz}\usetikzlibrary{external}'
                        r'\tikzexternalize\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('tikzexternalize' in e for e in issues.errors)

    def test_tikz_externalize_with_prebuilt_figures_no_error(self):
        # Pre-externalized PDF with the standard '*-figure*.pdf' name is shipped at root.
        # The image is referenced via \includegraphics so it survives whitelisting.
        files = {
            'main.tex': r'\documentclass{article}\usepackage{tikz}\usetikzlibrary{external}'
                        r'\tikzexternalize\begin{document}\includegraphics{main-figure0}\end{document}',
            'main-figure0.pdf': b'%PDF-1.4 fake',
        }
        issues, _ = self._run(files)
        assert not any('tikzexternalize' in e for e in issues.errors)

    def test_tikz_without_externalize_no_error(self):
        # Plain tikz usage without externalization — no error.
        files = {
            'main.tex': r'\documentclass{article}\usepackage{tikz}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert not any('tikzexternalize' in e for e in issues.errors)

    # ── Absolute-path warnings ────────────────────────────────────────────────

    def test_absolute_path_in_input_warns(self):
        files = {
            'main.tex': "\\documentclass{article}\n\\input{/abs/extra}\n"
                        "\\begin{document}hi\\end{document}",
        }
        issues, _ = self._run(files)
        assert any('absolute path' in w for w in issues.warnings)

    def test_absolute_path_in_includegraphics_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics{/abs/fig}\end{document}',
        }
        issues, _ = self._run(files)
        assert any('absolute path' in w for w in issues.warnings)

    def test_absolute_path_with_options_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics[width=5cm]{/abs/fig}\end{document}',
        }
        issues, _ = self._run(files)
        assert any('absolute path' in w for w in issues.warnings)

    def test_windows_drive_path_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics{C:/figs/x}\end{document}',
        }
        issues, _ = self._run(files)
        assert any('absolute path' in w for w in issues.warnings)

    def test_relative_path_does_not_warn(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics{figs/x}\end{document}',
            'figs/x.png': b'PNG',
        }
        issues, _ = self._run(files)
        assert not any('absolute path' in w for w in issues.warnings)

    def test_commented_absolute_path_not_flagged(self):
        files = {
            'main.tex': "\\documentclass{article}\n% \\input{/abs/extra}\n"
                        "\\begin{document}hi\\end{document}",
        }
        issues, _ = self._run(files)
        assert not any('absolute path' in w for w in issues.warnings)

    # ── Directory-name checks ─────────────────────────────────────────────────

    def test_directory_with_spaces_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics{my dir/fig}\end{document}',
            'my dir/fig.png': b'PNG',
        }
        issues, _ = self._run(files)
        assert any('directory' in w and 'spaces' in w for w in issues.warnings)

    def test_directory_with_non_ascii_warns(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics{café/fig}\end{document}',
            'café/fig.png': b'PNG',
        }
        issues, _ = self._run(files)
        assert any('directory' in w and 'non-ASCII' in w for w in issues.warnings)

    def test_clean_directory_names_no_warn(self):
        files = {
            'main.tex': r'\documentclass{article}\begin{document}\includegraphics{figures/fig}\end{document}',
            'figures/fig.png': b'PNG',
        }
        issues, _ = self._run(files)
        assert not any('directory name' in w for w in issues.warnings)

    def test_directory_warning_deduped(self):
        # Multiple files inside the same bad directory should only emit one
        # directory warning, not one per file.
        files = {
            'main.tex': r'\documentclass{article}\begin{document}'
                        r'\includegraphics{my dir/a}\includegraphics{my dir/b}'
                        r'\end{document}',
            'my dir/a.png': b'PNG',
            'my dir/b.png': b'PNG',
        }
        issues, _ = self._run(files)
        dir_space_warns = [w for w in issues.warnings
                           if 'directory' in w and 'spaces' in w]
        assert len(dir_space_warns) == 1

    # ── Uncompressed total-size warning ───────────────────────────────────────

    def test_uncompressed_size_warns(self, monkeypatch):
        import converter
        monkeypatch.setattr(converter, 'SIZE_WARN_MB', 0)
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert any('uncompressed project size' in w for w in issues.warnings)

    def test_uncompressed_size_silent_when_under_threshold(self):
        # The default 50 MB threshold is far above this tiny fixture.
        files = {
            'main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
        }
        issues, _ = self._run(files)
        assert not any('uncompressed project size' in w for w in issues.warnings)

    # ── Stricter non-UTF-8 detection ──────────────────────────────────────────

    def test_non_utf8_detected_via_strict_decode(self):
        # 0xFF is invalid UTF-8 anywhere; strict decode must catch it.
        files = {
            'main.tex': b'\\documentclass{article}\n\\begin{document}\xffhi\\end{document}',
        }
        issues, _ = self._run(files)
        assert any('not valid UTF-8' in w for w in issues.warnings)

    def test_utf8_with_bom_does_not_warn(self):
        # BOM-prefixed UTF-8 is technically valid UTF-8 (decodes to U+FEFF).
        files = {
            'main.tex': b'\xef\xbb\xbf\\documentclass{article}\n\\begin{document}hi\\end{document}',
        }
        issues, _ = self._run(files)
        assert not any('not valid UTF-8' in w for w in issues.warnings)


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


class TestFormatPdflatexErrors:
    """The contract: each error becomes a 3-line block of '! line' + 'l.NN line'
    + '<suffix line>'. Tests assert exact output shape rather than substring
    containment, so the contract is locked in."""

    def test_single_error_yields_exact_three_line_block(self):
        from converter import _format_pdflatex_errors
        stdout = (
            "This is pdfTeX, Version 3.141592653 ...\n"
            "(./main.tex\n"
            "! Undefined control sequence.\n"
            "l.42 \\frobnicate\n"
            "                {arg}\n"
            "?\n"
        )
        expected = (
            "! Undefined control sequence.\n"
            "l.42 \\frobnicate\n"
            "                {arg}"
        )
        assert _format_pdflatex_errors(stdout) == expected

    def test_multiple_errors_separated_by_blank_line(self):
        from converter import _format_pdflatex_errors
        stdout = (
            "! Undefined control sequence.\n"
            "l.42 \\frobnicate\n"
            "                {arg}\n"
            "(some intermediate output)\n"
            "! Missing $ inserted.\n"
            "l.78 see Eq.\n"
            "              \\eqref{wrong}\n"
        )
        expected = (
            "! Undefined control sequence.\n"
            "l.42 \\frobnicate\n"
            "                {arg}"
            "\n\n"
            "! Missing $ inserted.\n"
            "l.78 see Eq.\n"
            "              \\eqref{wrong}"
        )
        assert _format_pdflatex_errors(stdout) == expected

    def test_error_without_line_marker_yields_just_bang_line(self):
        from converter import _format_pdflatex_errors
        stdout = "! Fatal error occurred, no output PDF file produced!\n"
        assert _format_pdflatex_errors(stdout) == "! Fatal error occurred, no output PDF file produced!"

    def test_no_errors_returns_empty_string(self):
        from converter import _format_pdflatex_errors
        assert _format_pdflatex_errors("") == ""
        assert _format_pdflatex_errors("This is pdfTeX...\nOutput written.\n") == ""

    def test_caps_at_max_errors(self):
        from converter import _format_pdflatex_errors
        stdout = "\n".join(f"! error number {i}" for i in range(10))
        result = _format_pdflatex_errors(stdout, max_errors=3)
        assert result.count("! error") == 3
        # And the output is exactly 3 blocks separated by blank lines:
        assert result == "! error number 0\n\n! error number 1\n\n! error number 2"

    def test_cascading_bang_before_line_marker_isolates_each(self):
        # The lookahead must stop at the next '!', not borrow the later l.NN.
        from converter import _format_pdflatex_errors
        stdout = (
            "! First error.\n"
            "! Second error.\n"
            "l.42 something\n"
            "                ctx\n"
        )
        expected = (
            "! First error."
            "\n\n"
            "! Second error.\n"
            "l.42 something\n"
            "                ctx"
        )
        assert _format_pdflatex_errors(stdout) == expected

    def test_lookahead_window_bounded_at_six_lines(self):
        # If l.NN is >6 lines after '!', it's outside the window — yield only the '!' line.
        from converter import _format_pdflatex_errors
        stdout = (
            "! Boundary test.\n"
            "filler 1\n"
            "filler 2\n"
            "filler 3\n"
            "filler 4\n"
            "filler 5\n"
            "filler 6\n"
            "l.99 too far\n"
            "                ctx\n"
        )
        assert _format_pdflatex_errors(stdout) == "! Boundary test."


class TestCompileMissingTools:
    """When pdflatex / biber / bibtex aren't installed, --compile must surface
    a clear actionable message rather than a Python traceback. Verified by
    monkey-patching subprocess.run to raise FileNotFoundError."""

    def _build_zip(self, files: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_pdflatex_not_found_prints_clear_message(self, monkeypatch, tmp_path, capsys):
        import subprocess
        def raise_fnfe(*args, **kwargs):
            raise FileNotFoundError(2, "No such file or directory: 'pdflatex'")
        monkeypatch.setattr(subprocess, 'run', raise_fnfe)
        # Block the PDF auto-open in case execution somehow gets that far.
        import converter as _conv
        monkeypatch.setattr(_conv, '_open_file', lambda p: None)

        from converter import convert
        inp = tmp_path / 'in.zip'
        inp.write_bytes(self._build_zip({
            'main.tex': r'\documentclass{article}\begin{document}hi\end{document}',
        }))
        out = tmp_path / 'out.zip'
        # Should complete without raising.
        convert(inp, out, compile_pdf=True)

        captured = capsys.readouterr().out
        assert 'pdflatex not found' in captured
        assert 'TeX Live' in captured  # message points at the install path
        # Early-return ensures the same error isn't printed three times.
        assert captured.count('pdflatex not found') == 1


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


# ── Input resolution (directory / git URL) ────────────────────────────────────

class TestInputResolution:
    """Tests for _is_git_url, _zip_directory, and _resolve_input."""

    def test_is_git_url_https(self):
        from converter import _is_git_url
        assert _is_git_url('https://github.com/user/repo.git')
        assert _is_git_url('https://github.com/user/repo')

    def test_is_git_url_ssh(self):
        from converter import _is_git_url
        assert _is_git_url('git@github.com:user/repo.git')

    def test_is_git_url_git_protocol(self):
        from converter import _is_git_url
        assert _is_git_url('git://github.com/user/repo.git')

    def test_is_git_url_plain_path(self):
        from converter import _is_git_url
        assert not _is_git_url('paper.zip')
        assert not _is_git_url('/home/user/paper/')
        assert not _is_git_url('./my-project.git')  # local bare repo, not a URL

    def test_output_name_from_https_url(self):
        """Verify repo name derivation for https URLs."""
        url = 'https://github.com/user/my-paper.git'
        name_part = url.rstrip('/').rsplit('/', 1)[-1]
        if ':' in name_part:
            name_part = name_part.rsplit(':', 1)[-1].rsplit('/', 1)[-1]
        repo_name = name_part.removesuffix('.git')
        assert repo_name == 'my-paper'

    def test_output_name_from_ssh_url(self):
        """Verify repo name derivation for git@host:user/repo style URLs."""
        url = 'git@github.com:user/my-paper.git'
        name_part = url.rstrip('/').rsplit('/', 1)[-1]
        if ':' in name_part:
            name_part = name_part.rsplit(':', 1)[-1].rsplit('/', 1)[-1]
        repo_name = name_part.removesuffix('.git')
        assert repo_name == 'my-paper'

    def test_zip_directory(self, tmp_path):
        from converter import _zip_directory
        # Create a small directory with a .tex file
        (tmp_path / 'main.tex').write_text(r'\documentclass{article}\begin{document}hi\end{document}')
        (tmp_path / 'fig.png').write_bytes(b'PNG')
        (tmp_path / '.git').mkdir()
        (tmp_path / '.git' / 'config').write_text('gitconfig')

        cleanup = []
        zip_path = _zip_directory(tmp_path, cleanup)
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert 'main.tex' in names
        assert 'fig.png' in names
        # .git should be excluded
        assert not any('.git' in n for n in names)
        # Cleanup
        for d in cleanup:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_zip_directory_excludes_external_symlinks(self, tmp_path):
        from converter import _zip_directory
        (tmp_path / 'main.tex').write_text(r'\documentclass{article}\begin{document}hi\end{document}')
        # External symlink — should be excluded
        (tmp_path / 'external.txt').symlink_to('/etc/hosts')
        # In-project symlink — should be included
        (tmp_path / 'fig.png').write_bytes(b'PNG')
        (tmp_path / 'link_fig.png').symlink_to(tmp_path / 'fig.png')

        cleanup = []
        zip_path = _zip_directory(tmp_path, cleanup)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert 'main.tex' in names
        assert 'link_fig.png' in names  # in-project symlink kept
        assert 'external.txt' not in names  # external symlink excluded
        for d in cleanup:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_zip_directory_excludes_junk(self, tmp_path):
        from converter import _zip_directory
        (tmp_path / 'main.tex').write_text(r'\documentclass{article}\begin{document}hi\end{document}')
        (tmp_path / '__pycache__').mkdir()
        (tmp_path / '__pycache__' / 'mod.cpython-313.pyc').write_bytes(b'\x00')
        (tmp_path / '.DS_Store').write_bytes(b'\x00')
        (tmp_path / 'Thumbs.db').write_bytes(b'\x00')
        (tmp_path / 'helper.pyc').write_bytes(b'\x00')

        cleanup = []
        zip_path = _zip_directory(tmp_path, cleanup)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert 'main.tex' in names
        assert not any('__pycache__' in n for n in names)
        assert '.DS_Store' not in names
        assert 'Thumbs.db' not in names
        assert 'helper.pyc' not in names
        for d in cleanup:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_resolve_input_directory(self, tmp_path):
        from converter import _resolve_input
        (tmp_path / 'main.tex').write_text(r'\documentclass{article}\begin{document}hi\end{document}')
        cleanup = []
        result = _resolve_input(str(tmp_path), cleanup)
        assert result.exists()
        assert result.suffix == '.zip'
        for d in cleanup:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_resolve_input_zip(self, tmp_path):
        from converter import _resolve_input
        zip_path = tmp_path / 'paper.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('main.tex', r'\documentclass{article}\begin{document}hi\end{document}')
        cleanup = []
        result = _resolve_input(str(zip_path), cleanup)
        assert result == zip_path
        assert cleanup == []

    def test_directory_input_full_pipeline(self, tmp_path):
        """End-to-end: convert() works on a zip produced from a directory."""
        from converter import convert, _zip_directory
        # Set up a directory
        src = tmp_path / 'project'
        src.mkdir()
        (src / 'main.tex').write_text(
            r'\documentclass{article}\begin{document}\includegraphics{fig}\end{document}'
        )
        (src / 'fig.png').write_bytes(b'PNG')
        (src / 'unused.png').write_bytes(b'PNG')

        cleanup = []
        zip_path = _zip_directory(src, cleanup)
        out = tmp_path / 'out.zip'
        convert(zip_path, out)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        assert 'main.tex' in names
        assert 'fig.png' in names
        assert 'unused.png' not in names
        for d in cleanup:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
