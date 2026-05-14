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
    def test_clean_project_returns_success(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\begin{document}hi\end{document}'}, z)
        result = validate_submission(str(z))
        assert result['success'] is True
        assert result['errors'] == []

    def test_minted_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\usepackage{minted}\begin{document}hi\end{document}'}, z)
        result = validate_submission(str(z))
        assert result['success'] is False
        assert any('minted' in e for e in result['errors'])

    def test_absolute_escape_rejected(self, monkeypatch, tmp_path):
        """Absolute paths outside the safe root are rejected before any filesystem access."""
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        result = validate_submission('/nonexistent/path.zip')
        assert result['success'] is False
        assert any('outside allowed base directory' in e for e in result['errors'])

    def test_nonexistent_in_root_returns_not_found(self, tmp_path, monkeypatch):
        """A missing path that is inside the safe root returns a 'not found' error."""
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        result = validate_submission(str(tmp_path / 'missing.zip'))
        assert result['success'] is False
        assert any('not found' in e.lower() for e in result['errors'])

    def test_directory_input(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        d = tmp_path / 'project'
        d.mkdir()
        (d / 'main.tex').write_text(r'\documentclass{article}\begin{document}hi\end{document}')
        result = validate_submission(str(d))
        assert result['success'] is True

    def test_main_tex_hint(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        z = tmp_path / 'paper.zip'
        _make_zip({
            'paper.tex': r'\documentclass{article}\begin{document}hi\end{document}',
            'response.tex': r'\documentclass{article}\begin{document}response\end{document}',
        }, z)
        result = validate_submission(str(z), main_tex='paper.tex')
        assert result['success'] is True


class TestCleanSubmission:
    def test_produces_output_zip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\begin{document}hi\end{document}'}, z)
        result = clean_submission(str(z))
        assert result['success'] is True
        assert 'output_zip' in result
        out = Path(result['output_zip'])
        assert out.exists()
        out.unlink()

    def test_output_zip_contains_cleaned_tex(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
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

    def test_error_project_still_reports_errors(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\usepackage{minted}\begin{document}hi\end{document}'}, z)
        result = clean_submission(str(z))
        assert result['success'] is False
        assert any('minted' in e for e in result['errors'])
        # Still produces output even with errors
        if 'output_zip' in result:
            Path(result['output_zip']).unlink(missing_ok=True)


class TestPathSecurity:
    """Verify that the MCP tools reject paths outside the declared safe root."""

    def test_tilde_ssh_key_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        result = validate_submission("~/.ssh/id_rsa")
        assert result['success'] is False
        assert any('outside allowed base directory' in e for e in result['errors'])

    def test_tilde_expansion_rejected_clean(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        result = clean_submission("~/.ssh/id_rsa")
        assert result['success'] is False
        assert any('outside allowed base directory' in e for e in result['errors'])

    def test_absolute_path_outside_root_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        result = validate_submission('/etc/passwd')
        assert result['success'] is False
        assert any('outside allowed base directory' in e for e in result['errors'])

    def test_dotdot_traversal_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        # Construct a path that starts inside tmp_path but walks out via ..
        traversal = str(tmp_path / '..' / 'escape.zip')
        result = validate_submission(traversal)
        assert result['success'] is False
        assert any('outside allowed base directory' in e for e in result['errors'])

    def test_config_absolute_escape_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\begin{document}hi\end{document}'}, z)
        result = validate_submission(str(z), config='/etc/passwd')
        assert result['success'] is False
        assert any('outside allowed base directory' in e for e in result['errors'])

    def test_config_tilde_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\begin{document}hi\end{document}'}, z)
        result = validate_submission(str(z), config='~/.config/evil.yaml')
        assert result['success'] is False
        assert any('outside allowed base directory' in e for e in result['errors'])

    def test_legitimate_relative_path_accepted(self, tmp_path, monkeypatch):
        """A cwd-relative path that resolves inside the safe root is accepted."""
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        z = tmp_path / 'paper.zip'
        _make_zip({'main.tex': r'\documentclass{article}\begin{document}hi\end{document}'}, z)
        result = validate_submission('paper.zip')
        assert result['success'] is True


class TestDirectoryZip:
    def test_pycache_excluded_from_directory_input(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "main.tex").write_text(
            r"\documentclass{article}\begin{document}Hi\end{document}",
            encoding="utf-8",
        )
        pycache = proj / "__pycache__"
        pycache.mkdir()
        (pycache / "module.cpython-312.pyc").write_bytes(b"fake")
        result = validate_submission(str(proj))
        # __pycache__ file must not enter the zip at all — if it did,
        # the converter would log "remove: __pycache__/..." before dropping it.
        assert "__pycache__" not in result.get("log", "")

    def test_pyc_file_at_root_excluded_from_directory_input(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "main.tex").write_text(
            r"\documentclass{article}\begin{document}Hi\end{document}",
            encoding="utf-8",
        )
        (proj / "helper.pyc").write_bytes(b"fake")
        result = validate_submission(str(proj))
        assert "helper.pyc" not in result.get("log", "")

    def test_symlink_escaping_root_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "main.tex").write_text(
            r"\documentclass{article}\begin{document}Hi\end{document}",
            encoding="utf-8",
        )
        # Create a file outside the project root and symlink to it from inside
        outside = tmp_path / "outside_secret.tex"
        outside.write_text("secret content", encoding="utf-8")
        (proj / "evil_link.tex").symlink_to(outside)
        result = validate_submission(str(proj))
        # The outside file must not appear in the converter log at all
        assert "evil_link" not in result.get("log", "")


class TestErrorEnvelope:
    def test_path_not_found_has_errors_list(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        result = validate_submission(str(tmp_path / "nonexistent.zip"))
        assert "errors" in result
        assert isinstance(result["errors"], list)
        assert result["success"] is False

    def test_path_outside_root_has_errors_list(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        result = validate_submission("/etc/passwd")
        assert "errors" in result
        assert isinstance(result["errors"], list)
        assert result["success"] is False

    def test_success_path_has_errors_list(self, tmp_path, monkeypatch):
        """Success result must also carry 'errors' key (not just 'error')."""
        monkeypatch.setenv("LATEX2ARXIV_MCP_BASE_DIR", str(tmp_path))
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "main.tex").write_text(
            r"\documentclass{article}\begin{document}Hi\end{document}",
            encoding="utf-8",
        )
        result = validate_submission(str(proj))
        assert "errors" in result
        assert "warnings" in result
        assert "error" not in result  # singular key must be gone
