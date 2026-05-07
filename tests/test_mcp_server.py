"""Tests for the MCP server tools."""

import zipfile
from pathlib import Path

import pytest

mcp_available = pytest.importorskip("mcp", reason="mcp not installed (install with latex2arxiv[mcp])")

from mcp_server import validate_submission, clean_submission  # noqa: E402


def _make_zip(files: dict, dest: Path):
    with zipfile.ZipFile(dest, 'w') as zf:
        for name, content in files.items():
            zf.writestr(name, content if isinstance(content, str) else content)


class TestValidateSubmission:
    def test_clean_project_returns_success(self, tmp_path):
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\begin{document}hi\end{document}'}, z)
        result = validate_submission(str(z))
        assert result['success'] is True
        assert result['errors'] == []

    def test_minted_returns_error(self, tmp_path):
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\usepackage{minted}\begin{document}hi\end{document}'}, z)
        result = validate_submission(str(z))
        assert result['success'] is False
        assert any('minted' in e for e in result['errors'])

    def test_nonexistent_path_returns_error(self):
        result = validate_submission('/nonexistent/path.zip')
        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    def test_directory_input(self, tmp_path):
        d = tmp_path / 'project'
        d.mkdir()
        (d / 'main.tex').write_text(r'\documentclass{article}\begin{document}hi\end{document}')
        result = validate_submission(str(d))
        assert result['success'] is True

    def test_main_tex_hint(self, tmp_path):
        z = tmp_path / 'paper.zip'
        _make_zip({
            'paper.tex': r'\documentclass{article}\begin{document}hi\end{document}',
            'response.tex': r'\documentclass{article}\begin{document}response\end{document}',
        }, z)
        result = validate_submission(str(z), main_tex='paper.tex')
        assert result['success'] is True


class TestCleanSubmission:
    def test_produces_output_zip(self, tmp_path):
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\begin{document}hi\end{document}'}, z)
        result = clean_submission(str(z))
        assert result['success'] is True
        assert 'output_zip' in result
        out = Path(result['output_zip'])
        assert out.exists()
        out.unlink()

    def test_output_zip_contains_cleaned_tex(self, tmp_path):
        z = tmp_path / 'paper.zip'
        _make_zip({
            'main.tex': r'\documentclass{article}\begin{document}hi % comment\end{document}',
        }, z)
        result = clean_submission(str(z))
        out = Path(result['output_zip'])
        with zipfile.ZipFile(out) as zf:
            content = zf.read('main.tex').decode()
        assert '% comment' not in content
        out.unlink()

    def test_error_project_still_reports_errors(self, tmp_path):
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\usepackage{minted}\begin{document}hi\end{document}'}, z)
        result = clean_submission(str(z))
        assert result['success'] is False
        assert any('minted' in e for e in result['errors'])
        # Still produces output even with errors
        if 'output_zip' in result:
            Path(result['output_zip']).unlink(missing_ok=True)
