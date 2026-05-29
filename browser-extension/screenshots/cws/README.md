# Chrome Web Store screenshots

The three PNGs in this directory are the listing screenshots uploaded to the
Chrome Web Store for `latex2arxiv for Overleaf`. They are checked in so the
listing can be reproduced from the repository on a fresh machine.

| File | Aspect | Shows |
|---|---|---|
| `setup1-1280.png` | 1280 × 800 | Validate run: red diagnostics, main override field, output filename |
| `setup2-1280.png` | 1280 × 800 | Clean for arXiv success: green "Upload guide ready" row, Save .txt button, size delta |
| `setup3-1280.png` | 1280 × 800 | Pill collapsed: panel docked to right edge, full editor visible |

Recommended display order in the Web Store carousel: 1 → 2 → 3 (validate
surfaces the immediate value, clean shows the headline action, pill shows
the unobtrusive resting state).

## Reproducing

Source PNGs (3248 × 2122 macOS window captures, ~1.5 MB each) are gitignored.
To regenerate from a fresh capture:

1. Set Chrome window to ~1290 × 800 logical pixels (DevTools device toolbar).
2. Open the Overleaf demo project; reload the extension at `chrome://extensions`.
3. Reproduce each state listed above.
4. Capture each window with `Cmd+Shift+4 → Space → click the Chrome window`.
5. Save under `browser-extension/screenshots/setup<N>-screenshot.png`.
6. Run the resize script:

```bash
.venv/latex2arxiv/bin/python <<'PY'
from PIL import Image
from pathlib import Path
src_dir = Path("browser-extension/screenshots")
out_dir = src_dir / "cws"
out_dir.mkdir(exist_ok=True)
for src in sorted(src_dir.glob("setup*.png")):
    img = Image.open(src)
    w, h = img.size
    target_h = int(w / 1.6)
    if target_h < h:
        img = img.crop((0, 0, w, target_h))
    elif target_h > h:
        target_w = int(h * 1.6)
        left = (w - target_w) // 2
        img = img.crop((left, 0, left + target_w, h))
    img.resize((1280, 800), Image.LANCZOS).save(
        out_dir / src.name.replace("-screenshot", "-1280"), "PNG", optimize=True
    )
PY
```

The crop trims the top-aligned content so the panel stays visible after the
1.53 → 1.60 aspect-ratio correction.
