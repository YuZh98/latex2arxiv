"""Manifest-level assertions on fixture outputs.

These tests run convert() against the on-disk fixture directories and assert
which files ARE and are NOT present in the output zip. They catch silent
pruning regressions that error/warning counts alone cannot detect.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from converter import convert


def _zip_fixture(name: str) -> bytes:
    """Zip a fixture directory, skipping hidden files and .git."""
    fixture_dir = Path(__file__).parent / 'fixtures' / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(fixture_dir.rglob('*')):
            if not f.is_file():
                continue
            rel = f.relative_to(fixture_dir)
            if any(p.startswith('.') or p in {'__pycache__', '.git'} for p in rel.parts):
                continue
            zf.write(f, rel)
    return buf.getvalue()


def _run(zip_bytes: bytes, tmp_path: Path, **kwargs) -> list[str]:
    """Write zip to tmp_path, run convert(), return output namelist."""
    inp = tmp_path / 'in.zip'
    out = tmp_path / 'out.zip'
    inp.write_bytes(zip_bytes)
    convert(inp, out, **kwargs)
    with zipfile.ZipFile(out) as zf:
        return zf.namelist()


class TestFixtureManifests:
    def test_fixture_01_minimal_keeps_main(self, tmp_path):
        names = _run(_zip_fixture('01-minimal'), tmp_path)
        assert 'main.tex' in names

    def test_fixture_04_prunes_backup_response_and_supplement(self, tmp_path):
        """Unused standalone .tex files with \\documentclass must be pruned."""
        names = _run(_zip_fixture('04-multi-documentclass'), tmp_path)
        assert 'main.tex' in names
        assert 'main_backup.tex' not in names
        assert 'response.tex' not in names
        assert 'Supplementary_Materials.tex' not in names

    def test_fixture_08_keeps_input_fragments_in_normal_mode(self, tmp_path):
        """\\input / \\include fragments must be kept in the output zip (non-flatten)."""
        names = _run(_zip_fixture('08-flatten-basic'), tmp_path)
        assert 'main.tex' in names
        assert 'intro.tex' in names
        assert 'conclusion.tex' in names

    def test_fixture_09_keeps_subfile_fragments_in_normal_mode(self, tmp_path):
        """\\subfile fragments in subdirectories must be kept (non-flatten)."""
        names = _run(_zip_fixture('09-flatten-subfile'), tmp_path)
        assert 'main.tex' in names
        assert 'ch2.tex' in names
        assert 'chapters/ch1.tex' in names


class TestOverleafZipHandling:
    def test_macosx_entries_excluded_from_output(self, tmp_path):
        """__MACOSX/ Apple metadata and .DS_Store must not appear in the cleaned zip."""
        main_tex = r'\documentclass{article}\begin{document}Hello world.\end{document}'
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('main.tex', main_tex)
            zf.writestr('__MACOSX/._main.tex', b'\x00\x05\x16\x07')
            zf.writestr('__MACOSX/._fig.png', b'\x00\x05\x16\x07')
            zf.writestr('.DS_Store', b'\x00' * 32)
        inp = tmp_path / 'overleaf.zip'
        out = tmp_path / 'out.zip'
        inp.write_bytes(buf.getvalue())
        convert(inp, out)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        assert 'main.tex' in names
        assert not any('__MACOSX' in n for n in names)
        assert '.DS_Store' not in names

    def test_wrapper_directory_zip_converts_without_error(self, tmp_path):
        """Overleaf sometimes wraps all files in a top-level directory inside the zip."""
        main_tex = r'\documentclass{article}\begin{document}Hello world.\end{document}'
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('MyPaper/main.tex', main_tex)
            zf.writestr('MyPaper/fig.png', b'PNG')
            zf.writestr('MyPaper/__MACOSX/._main.tex', b'\x00')
        inp = tmp_path / 'overleaf_wrapped.zip'
        out = tmp_path / 'out.zip'
        inp.write_bytes(buf.getvalue())
        issues = convert(inp, out)
        assert len(issues.errors) == 0
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        assert any('main.tex' in n for n in names)
        assert not any('__MACOSX' in n for n in names)
