"""Tests for pipeline/images.py — resize_image and DEFAULT_MAX_PX."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.images import resize_image, DEFAULT_MAX_PX

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
class TestResizeImage:
    def _make_png(self, path: Path, width: int, height: int) -> Path:
        img = Image.new("RGB", (width, height), color=(128, 0, 0))
        img.save(path, "PNG")
        return path

    def test_large_image_is_resized(self, tmp_path):
        p = self._make_png(tmp_path / "big.png", 3200, 2400)
        resized = resize_image(p, max_px=DEFAULT_MAX_PX)
        assert resized is True
        with Image.open(p) as img:
            assert max(img.size) <= DEFAULT_MAX_PX

    def test_small_image_is_not_resized(self, tmp_path):
        p = self._make_png(tmp_path / "small.png", 800, 600)
        resized = resize_image(p, max_px=DEFAULT_MAX_PX)
        assert resized is False
        with Image.open(p) as img:
            assert img.size == (800, 600)

    def test_exact_boundary_not_resized(self, tmp_path):
        p = self._make_png(tmp_path / "exact.png", DEFAULT_MAX_PX, 400)
        resized = resize_image(p, max_px=DEFAULT_MAX_PX)
        assert resized is False

    def test_aspect_ratio_preserved(self, tmp_path):
        p = self._make_png(tmp_path / "wide.png", 3200, 800)
        resize_image(p, max_px=1600)
        with Image.open(p) as img:
            w, h = img.size
        assert abs(w / h - 4.0) < 0.05

    def test_custom_max_px(self, tmp_path):
        p = self._make_png(tmp_path / "img.png", 1000, 1000)
        resized = resize_image(p, max_px=500)
        assert resized is True
        with Image.open(p) as img:
            assert max(img.size) <= 500

    def test_unsupported_extension_skipped(self, tmp_path):
        """Non-image extensions (e.g. .eps) should return False without error."""
        p = tmp_path / "figure.eps"
        p.write_bytes(b"%!PS fake eps content")
        result = resize_image(p, max_px=DEFAULT_MAX_PX)
        assert result is False


def test_default_max_px_constant():
    assert DEFAULT_MAX_PX == 1600


class TestResizeImageNoPIL:
    def test_returns_false_when_no_pil(self, monkeypatch, tmp_path):
        """resize_image returns False when Pillow is unavailable."""
        import pipeline.images as img_mod

        monkeypatch.setattr(img_mod, "HAS_PIL", False)
        p = tmp_path / "img.png"
        p.write_bytes(b"fake")
        result = img_mod.resize_image(p)
        assert result is False

    def test_exception_in_open_returns_false(self, tmp_path):
        """Corrupt image file returns False without raising."""
        p = tmp_path / "corrupt.png"
        p.write_bytes(b"this is not a valid PNG")
        result = resize_image(p)
        assert result is False
