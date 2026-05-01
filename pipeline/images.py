try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# arXiv recommends keeping submissions under 50MB; resize large images by default
DEFAULT_MAX_PX = 1600  # longest side in pixels


def resize_image(path, max_px: int = DEFAULT_MAX_PX) -> bool:
    """Resize image in-place if its longest side exceeds max_px. Returns True if resized."""
    if not HAS_PIL:
        return False
    if path.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
        return False
    try:
        with Image.open(path) as img:
            w, h = img.size
            if max(w, h) <= max_px:
                return False
            scale = max_px / max(w, h)
            new_size = (int(w * scale), int(h * scale))
            resized = img.resize(new_size, Image.LANCZOS)
            resized.save(path)
            return True
    except Exception:
        return False
