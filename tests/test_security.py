"""Security regression tests: zip-slip (S3), subprocess timeout (S4), zip-bomb (S8)."""

import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import converter
from converter import ConverterError, _compile


# ── S3: zip-slip guard on second extractall() in _compile ────────────────────


class TestS3CompileZipSlip:
    def _make_zip(self, tmp_path: Path, member_name: str, content: bytes = b"evil") -> Path:
        zp = tmp_path / "bad.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr(member_name, content)
        return zp

    def test_slip_path_rejected(self, tmp_path: Path):
        """A zip with a path-traversal member must raise ConverterError."""
        zp = self._make_zip(tmp_path, "../evil.tex")
        with pytest.raises(ConverterError, match="path-traversal member"):
            _compile(zp, None)

    def test_slip_nested_path_rejected(self, tmp_path: Path):
        zp = self._make_zip(tmp_path, "subdir/../../other/evil.tex")
        with pytest.raises(ConverterError, match="path-traversal member"):
            _compile(zp, None)

    def test_normal_zip_passes_guard(self, tmp_path: Path):
        """A well-formed zip must not raise the zip-slip guard error."""
        zp = tmp_path / "ok.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("main.tex", r"\documentclass{article}\begin{document}hi\end{document}")
        try:
            _compile(zp, None)
        except ConverterError as e:
            assert "path-traversal" not in str(e)


# ── S4: subprocess timeout in _compile ───────────────────────────────────────


class TestS4SubprocessTimeout:
    def _make_valid_zip(self, tmp_path: Path) -> Path:
        zp = tmp_path / "proj.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("main.tex", r"\documentclass{article}\begin{document}hi\end{document}")
        return zp

    def test_pdflatex_timeout_handled(self, tmp_path: Path, capsys):
        zp = self._make_valid_zip(tmp_path)

        def _fake_run(cmd, **_kwargs):
            raise subprocess.TimeoutExpired(cmd, 300)

        with patch("subprocess.run", side_effect=_fake_run):
            _compile(zp, None)

        captured = capsys.readouterr().out
        assert "timed out" in captured

    def test_bibtex_timeout_handled(self, tmp_path: Path, capsys):
        """biber/bibtex timeout must be caught and reported, not propagate."""
        zp = tmp_path / "proj.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("main.tex", r"\documentclass{article}\begin{document}hi\end{document}")
            zf.writestr("refs.bib", "@article{a,title={T},author={A},year={2020}}")

        call_count = [0]

        def _fake_run(cmd, **_kwargs):
            call_count[0] += 1
            # First call is pdflatex — let it appear to succeed.
            if cmd[0] == "pdflatex":
                mock = type("R", (), {"returncode": 0, "stdout": b"Output written", "stderr": b""})()
                return mock
            # bibtex/biber call — timeout.
            raise subprocess.TimeoutExpired(cmd, 300)

        with patch("subprocess.run", side_effect=_fake_run):
            _compile(zp, None)

        captured = capsys.readouterr().out
        assert "timed out" in captured


# ── S8: decompression size cap (zip-bomb guard) ───────────────────────────────


class TestS8ZipBombGuard:
    def _make_small_zip(self, tmp_path: Path) -> Path:
        zp = tmp_path / "proj.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("main.tex", r"\documentclass{article}\begin{document}hi\end{document}")
        return zp

    def test_oversized_zip_raises(self, tmp_path: Path, monkeypatch):
        """A zip whose infolist reports total file_size > cap must raise ConverterError."""
        zp = self._make_small_zip(tmp_path)
        out = tmp_path / "out.zip"

        # Fake the infolist to report an enormous uncompressed size.
        big_size = converter._MAX_UNCOMPRESSED_BYTES + 1

        class _FakeInfo(zipfile.ZipInfo):
            def __init__(self, size: int) -> None:
                super().__init__("fake")
                self.file_size = size

        class FakeZipFile(zipfile.ZipFile):
            def infolist(self) -> list[zipfile.ZipInfo]:
                return [_FakeInfo(big_size)]

        monkeypatch.setattr(converter.zipfile, "ZipFile", FakeZipFile)

        with pytest.raises(ConverterError, match="safety cap"):
            converter.convert(zp, out)

    def test_within_cap_passes(self, tmp_path: Path):
        """A zip well within the size cap must not be rejected by the size guard."""
        zp = self._make_small_zip(tmp_path)
        out = tmp_path / "out.zip"
        try:
            converter.convert(zp, out)
        except ConverterError as e:
            assert "safety cap" not in str(e)

    def test_cap_constant_is_reasonable(self):
        assert converter._MAX_UNCOMPRESSED_BYTES == 500 * 1024 * 1024
