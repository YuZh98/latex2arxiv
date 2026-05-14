"""Tests for pipeline/guide.py — metadata extraction, stats, and formatting."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.guide import (
    extract_metadata, count_stats, format_summary, format_guide,
    _extract_braced, _count_pages,
)


class TestExtractTitle:
    def test_extract_title_simple(self):
        tex = r"\title{Some Title}"
        assert extract_metadata(tex)["title"] == "Some Title"

    def test_extract_title_multiline(self):
        tex = "\\title{A Very Long\n  Title Spanning\n  Multiple Lines}"
        assert extract_metadata(tex)["title"] == "A Very Long Title Spanning Multiple Lines"

    def test_extract_title_with_math(self):
        tex = r"\title{A $\beta$-divergence approach}"
        assert extract_metadata(tex)["title"] == r"A $\beta$-divergence approach"

    def test_extract_title_not_found(self):
        tex = r"\author{Someone}"
        assert extract_metadata(tex)["title"] is None


class TestExtractAuthors:
    def test_extract_authors_ims_format(self):
        tex = r"\fnms{Yu}~\snm{Zheng}"
        assert extract_metadata(tex)["authors"] == "Yu Zheng"

    def test_extract_authors_standard(self):
        tex = r"\author{John Smith}"
        assert extract_metadata(tex)["authors"] == "John Smith"

    def test_extract_authors_and_separated(self):
        tex = r"\author{Alice \and Bob \and Carol}"
        assert extract_metadata(tex)["authors"] == "Alice, Bob, Carol"

    def test_extract_authors_with_affiliations(self):
        tex = r"\author{Alice \\ Department of Statistics \\ and \\ Bob \\ Department of Math}"
        assert extract_metadata(tex)["authors"] == "Alice, Bob"

    def test_extract_authors_multiple_commands(self):
        tex = r"\author{Alice}\author{Bob}"
        assert extract_metadata(tex)["authors"] == "Alice, Bob"

    def test_extract_authors_multiple(self):
        tex = r"\fnms{Alice}~\snm{One}" "\n" r"\fnms{Bob}~\snm{Two}"
        assert extract_metadata(tex)["authors"] == "Alice One, Bob Two"

    def test_extract_authors_not_found(self):
        tex = r"\title{No Authors Here}"
        assert extract_metadata(tex)["authors"] is None


class TestExtractAbstract:
    def test_extract_abstract_simple(self):
        tex = "\\begin{abstract}\nThis is the abstract.\n\\end{abstract}"
        assert extract_metadata(tex)["abstract"] == "This is the abstract."

    def test_extract_abstract_not_found(self):
        tex = r"\title{No Abstract}"
        assert extract_metadata(tex)["abstract"] is None


class TestCountStats:
    def test_count_figures(self):
        tex = "\\begin{figure}\n\\end{figure}\n\\begin{figure}\n\\end{figure}"
        stats = count_stats(tex)
        assert stats["figures"] == 2

    def test_count_tables(self):
        tex = "\\begin{table}\n\\end{table}\n\\begin{table}\n\\end{table}"
        stats = count_stats(tex)
        assert stats["tables"] == 2

    def test_count_ignores_comments(self):
        tex = "% \\begin{figure}\n\\begin{figure}\n% \\begin{table}\n"
        stats = count_stats(tex)
        assert stats["figures"] == 1
        assert stats["tables"] == 0

    def test_count_starred_environments(self):
        tex = "\\begin{figure*}\n\\end{figure*}\n\\begin{table*}\n\\end{table*}\n\\begin{figure}\n\\end{figure}"
        stats = count_stats(tex)
        assert stats["figures"] == 2
        assert stats["tables"] == 1

    def test_count_pages_no_pdf(self):
        stats = count_stats("some tex", pdf_path=None)
        assert stats["pages"] is None


class TestFormatSummary:
    def test_format_summary_complete(self):
        meta = {"title": "My Paper", "authors": "Alice, Bob", "abstract": "We study X."}
        stats = {"figures": 3, "tables": 1, "pages": 12}
        result = format_summary(meta, stats, "/tmp/out.zip", 2.5)
        assert "My Paper" in result
        assert "Alice, Bob" in result
        assert "We study X." in result
        assert "12 pages" in result
        assert "3 figures" in result
        assert "1 tables" in result
        assert "out.zip (2.5 MB)" in result

    def test_format_summary_missing_fields(self):
        meta = {"title": None, "authors": None, "abstract": None}
        stats = {"figures": 0, "tables": 0, "pages": None}
        result = format_summary(meta, stats, "/tmp/out.zip", 1.0)
        assert "(could not extract" in result


class TestFormatGuide:
    def _make_guide(self, **kwargs):
        defaults = {
            "metadata": {"title": "T", "authors": "A", "abstract": "Ab"},
            "stats": {"figures": 2, "tables": 1, "pages": 10},
            "output_path": "/tmp/paper.zip",
            "output_size_mb": 3.0,
            "kept_files": ["main.tex", "fig1.pdf", "ref.bib"],
            "main_tex": "main.tex",
        }
        defaults.update(kwargs)
        return format_guide(**defaults)

    def test_format_guide_contains_disclaimer(self):
        guide = self._make_guide()
        assert "Reference only" in guide
        assert "info.arxiv.org/help/submit_tex.html" in guide

    def test_format_guide_contains_steps(self):
        guide = self._make_guide()
        for i in range(1, 8):
            assert f"Step {i}:" in guide

    def test_format_guide_contains_file_manifest(self):
        guide = self._make_guide()
        assert "fig1.pdf" in guide
        assert "main.tex" in guide
        assert "ref.bib" in guide
        assert "← main file" in guide

    def test_format_guide_sty_warning(self):
        guide = self._make_guide()
        assert ".sty" in guide
        assert "IGNORE" in guide


class TestExtractBracedEdgeCases:
    def test_escaped_brace_skipped(self):
        # \{ and \} inside braces must not be counted as depth changes
        result = _extract_braced(r"{\{escaped\}}", 0)
        assert result == r"\{escaped\}"

    def test_unclosed_brace_returns_none(self):
        assert _extract_braced("{unclosed", 0) is None

    def test_not_starting_at_brace_returns_none(self):
        assert _extract_braced("hello{world}", 0) is None

    def test_past_end_returns_none(self):
        assert _extract_braced("hi", 10) is None


class TestAuthorsWithThanks:
    def test_thanks_stripped(self):
        tex = r"\author{Alice Smith\thanks{Supported by NSF grant}}"
        result = extract_metadata(tex)["authors"]
        assert result is not None
        assert "Alice" in result
        assert "NSF" not in result

    def test_affiliation_line_skipped(self):
        tex = r"\author{Alice Smith \\ University of Excellence}"
        result = extract_metadata(tex)["authors"]
        assert result is not None
        assert "Alice Smith" in result
        assert "University" not in result

    def test_command_only_split_segment_skipped(self):
        # A \\ split segment that reduces to empty after LaTeX command removal
        # should be silently skipped rather than emitting a blank name
        tex = r"\author{Alice Smith \\ \footnote{hidden note} \\ MIT}"
        result = extract_metadata(tex)["authors"]
        assert result is not None
        assert "Alice" in result

    def test_thanks_without_brace_does_not_loop_forever(self):
        # \thanksNote contains the substring \thanks but has no { after it;
        # must not infinite-loop
        tex = r"\author{Alice Smith\thanksNote}"
        result = extract_metadata(tex)["authors"]
        assert result is not None


class TestFormatSummaryTruncation:
    def test_long_title_capped_at_70_chars(self):
        long_title = "A" * 80
        meta = {"title": long_title, "authors": "A", "abstract": "Ab"}
        out = format_summary(meta, {}, "out.zip", 0.1)
        assert "..." in out

    def test_long_abstract_capped_at_150_chars(self):
        long_abstract = "B" * 200
        meta = {"title": "T", "authors": "A", "abstract": long_abstract}
        out = format_summary(meta, {}, "out.zip", 0.1)
        assert "..." in out


class TestCountPages:
    def test_nonexistent_path_returns_none(self):
        assert _count_pages("/no/such/file.pdf") is None

    def test_empty_path_returns_none(self):
        assert _count_pages("") is None

    def test_pdfinfo_output_parsed(self, tmp_path):
        fake = tmp_path / "x.pdf"
        fake.write_bytes(b"%PDF")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Pages:   7\n")
            result = _count_pages(str(fake))
        assert result == 7

    def test_pdfinfo_no_pages_line_falls_back_to_binary(self, tmp_path):
        fake = tmp_path / "x.pdf"
        fake.write_bytes(b"/Type /Page /Type /Page /Type /Pages")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Other: value\n")
            result = _count_pages(str(fake))
        assert result == 2

    def test_pdfinfo_unavailable_uses_binary_fallback(self, tmp_path):
        fake = tmp_path / "x.pdf"
        fake.write_bytes(b"/Type /Page")
        with patch("subprocess.run", side_effect=Exception("no pdfinfo")):
            result = _count_pages(str(fake))
        assert result == 1

    def test_count_stats_includes_page_count_when_pdf_given(self, tmp_path):
        fake = tmp_path / "x.pdf"
        fake.write_bytes(b"/Type /Page")
        with patch("subprocess.run", side_effect=Exception("no pdfinfo")):
            stats = count_stats("some tex", pdf_path=str(fake))
        assert stats["pages"] == 1
