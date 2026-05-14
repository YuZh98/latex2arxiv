"""Tests for path-traversal boundary checks in flatten.py and deps.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from converter import Issues
from pipeline.flatten import flatten_tex
from pipeline.deps import find_included_tex, find_used_images


# ── flatten.py boundary checks ────────────────────────────────────────────────

class TestFlattenTraversal:
    def _make_project(self, tmp_path: Path, files: dict[str, str]) -> Path:
        proj = tmp_path / "proj"
        proj.mkdir()
        for rel, content in files.items():
            p = proj / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return proj

    def test_traversal_input_is_rejected(self, tmp_path):
        """\\input pointing outside the project root must not be inlined."""
        outside = tmp_path / "secret.tex"
        outside.write_text("TOP SECRET CONTENT", encoding="utf-8")

        proj = self._make_project(tmp_path, {
            "main.tex": r"""\documentclass{article}
\begin{document}
\input{../secret}
\end{document}""",
        })

        issues = Issues()
        src, inlined = flatten_tex(proj / "main.tex", proj, issues)

        assert "TOP SECRET CONTENT" not in src
        assert not any(p == outside.resolve() for p in inlined)
        assert any("escapes the project root" in w for w in issues.warnings)

    def test_legitimate_input_is_inlined(self, tmp_path):
        """A well-formed \\input within the project root must be inlined."""
        proj = self._make_project(tmp_path, {
            "main.tex": r"""\documentclass{article}
\begin{document}
\input{sections/intro}
\end{document}""",
            "sections/intro.tex": "Introduction text.",
        })

        issues = Issues()
        src, inlined = flatten_tex(proj / "main.tex", proj, issues)

        assert "Introduction text." in src
        assert r"\input{sections/intro}" not in src
        assert not any("escapes the project root" in w for w in issues.warnings)

    def test_traversal_subfile_is_rejected(self, tmp_path):
        """\\subfile pointing outside the project root must not be inlined."""
        outside = tmp_path / "secret.tex"
        outside.write_text(
            r"""\documentclass[main]{subfiles}
\begin{document}
OUTSIDE SUBFILE
\end{document}""",
            encoding="utf-8",
        )

        proj = self._make_project(tmp_path, {
            "main.tex": r"""\documentclass{article}
\begin{document}
\subfile{../secret}
\end{document}""",
        })

        issues = Issues()
        src, inlined = flatten_tex(proj / "main.tex", proj, issues)

        assert "OUTSIDE SUBFILE" not in src
        assert any("escapes the project root" in w for w in issues.warnings)


# ── deps.py boundary checks ───────────────────────────────────────────────────

class TestFindIncludedTexTraversal:
    def test_traversal_tex_include_is_excluded(self, tmp_path):
        """\\input pointing outside root must not appear in the found set."""
        outside = tmp_path / "outside.tex"
        outside.write_text("Outside content.", encoding="utf-8")

        root = tmp_path / "proj"
        root.mkdir()

        source = r"\input{../outside}"
        found = find_included_tex(source, root, root, set())

        assert outside.resolve() not in found

    def test_legitimate_tex_include_is_found(self, tmp_path):
        """\\input within root must appear in the found set."""
        root = tmp_path / "proj"
        root.mkdir()
        child = root / "child.tex"
        child.write_text("", encoding="utf-8")

        source = r"\input{child}"
        found = find_included_tex(source, root, root, set())

        assert child.resolve() in found


class TestFindUsedImagesTraversal:
    def test_traversal_image_is_excluded(self, tmp_path):
        """\\includegraphics pointing outside root must not appear in used paths."""
        outside_img = tmp_path / "secret.png"
        outside_img.write_bytes(b"PNG")

        root = tmp_path / "proj"
        root.mkdir()

        # The tex file lives at root; ../secret.png resolves outside root.
        source = r"\includegraphics{../secret}"
        paths, refs = find_used_images([source], [root], root)

        assert outside_img.resolve() not in paths

    def test_legitimate_image_is_found(self, tmp_path):
        """\\includegraphics within root must appear in used paths."""
        root = tmp_path / "proj"
        root.mkdir()
        img = root / "fig.png"
        img.write_bytes(b"PNG")

        source = r"\includegraphics{fig}"
        paths, refs = find_used_images([source], [root], root)

        assert img.resolve() in paths

    def test_traversal_graphicspath_dir_is_excluded(self, tmp_path):
        """\\graphicspath pointing outside root must not be used to resolve images."""
        outside_dir = tmp_path / "outside_figs"
        outside_dir.mkdir()
        outside_img = outside_dir / "secret.png"
        outside_img.write_bytes(b"PNG")

        root = tmp_path / "proj"
        root.mkdir()

        source = r"\graphicspath{{../../outside_figs/}}" + "\n" + r"\includegraphics{secret}"
        paths, refs = find_used_images([source], [root], root)

        assert outside_img.resolve() not in paths
