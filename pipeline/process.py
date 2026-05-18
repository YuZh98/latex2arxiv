"""Per-file processing pass over the extracted tree.

Walks `ctx.root`, prunes non-whitelisted files (with a stem/name fallback for
images so resolve-failures don't drop referenced figures), normalizes kept
`.tex` and `.bib` content, and resizes images when requested. Returns the set
of kept paths plus the list of removed-file display names (used by --json and
the summary line).

Progress output is emitted via the `log` callable rather than `print` directly
so the orchestrator can route it (currently `print`; future: logging /
reporter callback).
"""

from pathlib import Path
from typing import Callable

from pipeline.bibtex import normalize_bibtex
from pipeline.config import apply_config
from pipeline.images import resize_image
from pipeline.tex import (
    ensure_pdfoutput,
    remove_comment_environments,
    remove_draft_annotations,
    remove_draft_packages,
    strip_comments,
)
from pipeline.types import ConvertContext, Issues

# File extensions treated as images: subject to the stem/name fallback when a
# direct whitelist miss happens, and the only types eligible for --resize.
IMAGE_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg", ".tikz"}


def _process_files(
    ctx: ConvertContext,
    *,
    used_image_refs: set[str],
    used_bib_files: set[str],
    cited_keys: set[str],
    resize: int | None,
    dry_run: bool,
    issues: Issues,
    log: Callable[[str], None],
) -> tuple[set[Path], list[str]]:
    """Walk `ctx.root`, prune by whitelist, normalize kept files. Returns
    `(kept_files, removed_names)` so the orchestrator can hand them to the
    pre-flight checks and the JSON envelope. `log` receives progress lines."""
    kept_files: set[Path] = set()
    removed_names: list[str] = []
    all_tex_resolved = {p.resolve() for p in ctx.all_tex_files}

    for path in list(ctx.root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ctx.root)
        resolved = path.resolve()

        # Keep only whitelisted files; delete everything else
        if resolved not in ctx.whitelist:
            # Second chance for images: match by stem/name in case path resolution failed
            if path.suffix.lower() in IMAGE_EXTS:
                name, stem = path.name, path.stem
                if name in used_image_refs or stem in used_image_refs:
                    pass  # keep it
                else:
                    log(f"  remove: {rel}")
                    removed_names.append(str(rel))
                    if not dry_run:
                        path.unlink()
                    continue
            else:
                log(f"  remove: {rel}")
                removed_names.append(str(rel))
                if not dry_run:
                    path.unlink()
                continue

        kept_files.add(path)

        # Resize images if requested
        if resize and path.suffix.lower() in IMAGE_EXTS:
            if dry_run:
                log(f"  would resize: {rel}")
            elif resize_image(path, max_px=resize):
                log(f"  resized: {rel}")

        # Process .tex files
        if path.suffix == ".tex" and resolved in all_tex_resolved:
            if dry_run:
                log(f"  would process (tex): {rel}")
            else:
                src = path.read_text(encoding="utf-8", errors="replace")
                src = strip_comments(src)
                src = remove_comment_environments(src)
                src = remove_draft_annotations(src)
                src = remove_draft_packages(src)
                if ctx.user_config:
                    src = apply_config(src, ctx.user_config, warn_fn=issues.warn)
                if path == ctx.main_tex:
                    src = ensure_pdfoutput(src)
                path.write_text(src, encoding="utf-8")

        # Process .bib files
        if path.suffix == ".bib" and path.name in used_bib_files:
            if dry_run:
                log(f"  would process (bib): {rel}")
            else:
                src = path.read_text(encoding="utf-8", errors="replace")
                src = normalize_bibtex(src, cited_keys=cited_keys, warn_fn=issues.warn)
                path.write_text(src, encoding="utf-8")

    return kept_files, removed_names
