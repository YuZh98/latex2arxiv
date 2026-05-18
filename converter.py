#!/usr/bin/env python3
"""
latex_arxiv_converter — convert a LaTeX .zip to an arXiv-ready .zip

Usage:
    python3 converter.py input.zip [output.zip] [--main MAIN_TEX]
"""

import io
import json
import re
import sys
import argparse
import zipfile
import tempfile
import shutil
from pathlib import Path
from importlib import resources
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from pipeline.types import Issues, ConverterError
from pipeline.tex import (
    strip_comments,
    remove_draft_annotations,
    remove_draft_packages,
    remove_comment_environments,
    ensure_pdfoutput,
)
from pipeline.bibtex import normalize_bibtex
from pipeline.deps import (
    find_included_tex,
    find_used_images,
    find_used_bib_files,
    find_used_style_files,
    find_cited_keys,
)
from pipeline.config import load_config, apply_config
from pipeline.images import resize_image, DEFAULT_MAX_PX
from pipeline.flatten import flatten_tex
from pipeline.guide import extract_metadata, count_stats, format_summary, format_guide, _count_pages

from pipeline.preflight import (
    _check_compliance,
    _check_files,
    _check_output_size,
    _check_uncompressed_size,
)
from pipeline.build import _compile

from pipeline.resolve import (
    find_main_tex,
    _is_git_url,
    _resolve_input,
)

__all__ = ["Issues", "ConverterError", "convert"]


def _get_version() -> str:
    try:
        return _pkg_version("latex2arxiv")
    except PackageNotFoundError:
        return "0.0.0+unknown"


IMAGE_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg", ".tikz"}

# Output zip size threshold for advisory warning (MB).
SIZE_WARN_MB = 50

# Maximum total uncompressed size accepted from the input zip (zip-bomb guard).
_MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _print_summary(removed: int, kept: int, issues: Issues, input_zip: Path, output_zip: Path | None) -> None:
    """One-line conversion summary. Skips size segment in dry-run (no output_zip)."""
    parts = [f"Summary: {removed} removed, {kept} kept"]
    if output_zip is not None:
        in_mb = input_zip.stat().st_size / (1024 * 1024)
        out_mb = output_zip.stat().st_size / (1024 * 1024)
        parts.append(f"{in_mb:.1f} MB → {out_mb:.1f} MB")
    parts.append(f"{_plural(len(issues.errors), 'error')}, {_plural(len(issues.warnings), 'warning')}")
    print(" | ".join(parts))


def convert(
    input_zip: Path,
    output_zip: Path,
    main_hint: str | None = None,
    compile_pdf: bool = False,
    resize: int | None = None,
    config_path: Path | None = None,
    dry_run: bool = False,
    flatten: bool = False,
    guide: bool = False,
) -> Issues:
    issues = Issues()
    issues.flatten = flatten
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # 1. Extract — validate member paths first (zip-slip protection).
        # Aborts before any disk write if a member would escape the temp root
        # via .. or absolute-style paths.
        if not Path(input_zip).exists():
            raise ConverterError(f"{input_zip} not found")
        with zipfile.ZipFile(input_zip) as zf:
            total_size = sum(m.file_size for m in zf.infolist())
            if total_size > _MAX_UNCOMPRESSED_BYTES:
                raise ConverterError(
                    f"refusing to extract — uncompressed size "
                    f"({total_size / (1024 * 1024):.0f} MB) exceeds the "
                    f"{_MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB safety cap"
                )
            root_abs = root.resolve()
            for name in zf.namelist():
                target = (root / name).resolve()
                try:
                    target.relative_to(root_abs)
                except ValueError:
                    raise ConverterError(
                        f"refusing to extract — zip contains a path that escapes the extraction root: {name!r}"
                    )
            zf.extractall(root)

        # Unwrap single top-level directory if present.
        # Ignore macOS zip noise (__MACOSX/ metadata sibling, .DS_Store file)
        # so a zip created via the macOS Finder still unwraps cleanly.
        entries = [p for p in root.iterdir() if p.name != "__MACOSX" and p.name != ".DS_Store"]
        if len(entries) == 1 and entries[0].is_dir():
            root = entries[0]

        # 2. Find main .tex and all included .tex files
        if main_hint:
            main_tex = next((p for p in root.rglob("*.tex") if p.name == main_hint), None)
            if main_tex is None:
                raise ConverterError(f"--main '{main_hint}' not found in archive")
        else:
            main_tex = find_main_tex(root)
        if main_tex is None:
            raise ConverterError("no .tex file found in archive")
        print(f"  main tex: {main_tex.relative_to(root)}")
        issues.main_tex = str(main_tex.relative_to(root))

        all_tex_files = {main_tex}
        main_source = main_tex.read_text(encoding="utf-8", errors="replace")
        all_tex_files |= find_included_tex(main_source, main_tex.parent, root, {main_tex})

        # 2b. Optional flatten: inline every \input/\include/\subfile into
        # main.tex, then drop the fragment files from the kept-files set so
        # the output zip contains a single .tex.
        if flatten:
            flattened, inlined_paths = flatten_tex(main_tex, root, issues)
            main_tex.write_text(flattened, encoding="utf-8")
            _root_resolved = root.resolve()
            issues.inlined_files = sorted(str(p.relative_to(_root_resolved)) for p in inlined_paths if p.exists())
            # After flatten, the only .tex left in the dependency set is the
            # main file; the fragments will be pruned from the output zip.
            all_tex_files = {main_tex}
            main_source = flattened

        # Collect sources + their directories for image resolution
        tex_files_list = [p for p in all_tex_files if p.exists()]
        all_sources = [p.read_text(encoding="utf-8", errors="replace") for p in tex_files_list]
        tex_dirs = [p.parent for p in tex_files_list]

        # Encoding warn: re-read bytes and try strict UTF-8 decoding so we surface
        # exactly the files that need to be re-saved. Resolve both sides — on macOS
        # /var/folders is a symlink to /private/var/folders, which would break a
        # naive relative_to.
        _root_abs = root.resolve()
        for tf in tex_files_list:
            try:
                tf.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                issues.warn(
                    f"{tf.resolve().relative_to(_root_abs)} is not valid UTF-8 — "
                    "re-save as UTF-8 to avoid corrupted accented/special "
                    "characters in the output"
                )

        used_image_paths, used_image_refs = find_used_images(all_sources, tex_dirs, root)
        used_bib_files = find_used_bib_files(all_sources)
        used_style_files = find_used_style_files(all_sources)
        cited_keys = find_cited_keys(all_sources)

        # Build whitelist of resolved absolute paths to keep
        whitelist = {p.resolve() for p in all_tex_files if p.exists()}
        whitelist |= used_image_paths
        # Add .bib files — prefer root-level over subdirectory duplicates.
        for bib_name in used_bib_files:
            candidates = [p for p in root.rglob(bib_name) if p.name == bib_name]
            if not candidates:
                continue
            # Prefer the one closest to root (fewest path components).
            best = min(candidates, key=lambda p: len(p.relative_to(root).parts))
            whitelist.add(best.resolve())
        # Add used support files (.cls, .sty) and always-keep types (.bst, .ind, .gls, .nls, .bbl)
        main_stem = main_tex.stem
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            at_root = path.parent == root
            if ext in {".cls", ".sty"} and path.name in used_style_files and at_root:
                whitelist.add(path.resolve())
            elif ext == ".bst" and at_root:
                whitelist.add(path.resolve())
            elif ext == ".bbl" and path.stem == main_stem and at_root:
                whitelist.add(path.resolve())
            elif ext in {".ind", ".gls", ".nls"} and at_root:
                whitelist.add(path.resolve())
            elif at_root and (path.name == "00README" or path.name.startswith("00README.")):
                # arXiv reads 00README / 00README.XXX at root for processor hints,
                # encoding declarations, and aux file lists.
                whitelist.add(path.resolve())

        user_config = load_config(config_path, warn_fn=issues.warn) if config_path else {}
        kept_files: set[Path] = set()
        removed_names: list[str] = []

        # 3. Process each file
        for path in list(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            resolved = path.resolve()

            # Keep only whitelisted files; delete everything else
            if resolved not in whitelist:
                # Second chance for images: match by stem/name in case path resolution failed
                if path.suffix.lower() in IMAGE_EXTS:
                    name, stem = path.name, path.stem
                    if name in used_image_refs or stem in used_image_refs:
                        pass  # keep it
                    else:
                        print(f"  remove: {rel}")
                        removed_names.append(str(rel))
                        if not dry_run:
                            path.unlink()
                        continue
                else:
                    print(f"  remove: {rel}")
                    removed_names.append(str(rel))
                    if not dry_run:
                        path.unlink()
                    continue

            kept_files.add(path)

            # Resize images if requested
            if resize and path.suffix.lower() in IMAGE_EXTS:
                if dry_run:
                    print(f"  would resize: {rel}")
                elif resize_image(path, max_px=resize):
                    print(f"  resized: {rel}")

            # Process .tex files
            if path.suffix == ".tex" and path.resolve() in {p.resolve() for p in all_tex_files}:
                if dry_run:
                    print(f"  would process (tex): {rel}")
                else:
                    src = path.read_text(encoding="utf-8", errors="replace")
                    src = strip_comments(src)
                    src = remove_comment_environments(src)
                    src = remove_draft_annotations(src)
                    src = remove_draft_packages(src)
                    if user_config:
                        src = apply_config(src, user_config, warn_fn=issues.warn)
                    if path == main_tex:
                        src = ensure_pdfoutput(src)
                    path.write_text(src, encoding="utf-8")

            # Process .bib files
            if path.suffix == ".bib" and path.name in used_bib_files:
                if dry_run:
                    print(f"  would process (bib): {rel}")
                else:
                    src = path.read_text(encoding="utf-8", errors="replace")
                    src = normalize_bibtex(src, cited_keys=cited_keys, warn_fn=issues.warn)
                    path.write_text(src, encoding="utf-8")

        # 3b. Compliance + pre-flight checks
        _check_compliance(main_tex, all_sources, root, tex_files=tex_files_list, main_stem=main_stem, issues=issues)
        _check_files(root, kept_files, issues)
        _check_uncompressed_size(kept_files, issues)

        # Check for undefined citations in cleaned output
        cleaned_sources = []
        for path in kept_files:
            if path.suffix == ".tex":
                try:
                    cleaned_sources.append(path.read_text(encoding="utf-8", errors="replace"))
                except Exception:
                    pass
        if cleaned_sources:
            final_cited = find_cited_keys(cleaned_sources)
            defined_keys = set()
            for path in kept_files:
                if path.suffix == ".bib":
                    try:
                        bib_content = path.read_text(encoding="utf-8", errors="replace")
                        for m in re.finditer(r"@\w+\{\s*([^,\s]+)", bib_content):
                            defined_keys.add(m.group(1).strip())
                    except Exception:
                        pass
            for path in kept_files:
                if path.suffix == ".bbl":
                    try:
                        bbl_content = path.read_text(encoding="utf-8", errors="replace")
                        for m in re.finditer(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", bbl_content):
                            defined_keys.add(m.group(1).strip())
                    except Exception:
                        pass
            if defined_keys:
                undefined = final_cited - defined_keys
                if undefined:
                    sample = sorted(undefined)[:5]
                    more = f" (and {len(undefined) - 5} more)" if len(undefined) > 5 else ""
                    issues.warn(
                        f"{len(undefined)} undefined citation(s): {', '.join(sample)}{more} — "
                        "ensure all cited references exist in your .bib or .bbl file"
                    )

        # Advisory: custom style/class files
        for path in kept_files:
            if path.suffix.lower() in {".cls", ".sty"}:
                issues.warn(
                    f"custom style file kept: {path.relative_to(root)} — "
                    "arXiv may suggest removing this; ignore that warning, "
                    "the file is required for compilation"
                )

        # Populate JSON-payload fields on the Issues object so --json mode has
        # everything it needs without re-scanning the (possibly cleaned-up)
        # temp dir later.
        issues.input_path = str(input_zip)
        issues.dry_run = dry_run
        issues.kept_files = sorted(str(p.relative_to(root)) for p in kept_files)
        issues.removed_files = removed_names
        try:
            issues.sizes_input = input_zip.stat().st_size if input_zip.is_file() else None
        except OSError:
            issues.sizes_input = None
        issues.sizes_uncompressed = sum(p.stat().st_size for p in kept_files if p.is_file())

        # 4. Repack
        if dry_run:
            print(f"\n[dry-run] No output written. Would have created: {output_zip}")
            _print_summary(len(removed_names), len(kept_files), issues, input_zip, None)
            issues.output_path = None
            issues.sizes_output = None
            return issues

        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(root))

        _check_output_size(output_zip, issues)
        print(f"\nDone → {output_zip}")
        _print_summary(len(removed_names), len(kept_files), issues, input_zip, output_zip)
        if issues.errors:
            print(f"  {len(issues.errors)} pre-flight error(s) — fix before submitting to arXiv")
        issues.output_path = str(output_zip)
        issues.sizes_output = output_zip.stat().st_size if output_zip.exists() else None

        # Read cleaned main tex for metadata extraction
        try:
            with zipfile.ZipFile(output_zip) as zf:
                main_tex_content = zf.read(issues.main_tex).decode("utf-8", errors="replace")
                # Count figures/tables across ALL tex files in the zip
                all_tex_content = "\n".join(
                    zf.read(n).decode("utf-8", errors="replace") for n in zf.namelist() if n.endswith(".tex")
                )

            metadata = extract_metadata(main_tex_content)
            pdf_path = None  # will be set after compile if applicable
            stats = count_stats(all_tex_content, pdf_path)

            out_size_mb = output_zip.stat().st_size / (1024 * 1024)
            print()
            print(format_summary(metadata, stats, str(output_zip), out_size_mb))

            if guide:
                guide_path = output_zip.with_name(output_zip.stem + "_UPLOAD_GUIDE.txt")
                guide_text = format_guide(
                    metadata, stats, str(output_zip), out_size_mb, issues.kept_files, issues.main_tex or ""
                )
                guide_path.write_text(guide_text, encoding="utf-8")
                print(f"  Upload guide → {guide_path}")

            # Store metadata on issues for JSON output
            issues.metadata = {**metadata, "stats": stats}
        except Exception as exc:
            print(f"  [warn] could not generate upload summary: {exc}")

    if compile_pdf:
        _compile(output_zip, main_hint)
        # Update guide with page count from compiled PDF
        compiled_pdf = output_zip.with_suffix(".pdf")
        if compiled_pdf.exists() and hasattr(issues, "metadata") and issues.metadata:
            pages = _count_pages(str(compiled_pdf))
            if pages:
                stats = issues.metadata.get("stats", {})
                stats["pages"] = pages
                issues.metadata["stats"] = stats
                print(f"  Pages: {pages}")
                if guide:
                    guide_path = output_zip.with_name(output_zip.stem + "_UPLOAD_GUIDE.txt")
                    if guide_path.exists():
                        out_size_mb = output_zip.stat().st_size / (1024 * 1024)
                        meta = {k: v for k, v in issues.metadata.items() if k != "stats"}
                        guide_text = format_guide(
                            meta, stats, str(output_zip), out_size_mb, issues.kept_files, issues.main_tex or ""
                        )
                        guide_path.write_text(guide_text, encoding="utf-8")
    return issues


def _emit_json(issues: Issues) -> None:
    """Write the v1 schema JSON payload for this run to sys.stdout (real stdout
    — caller must have restored it before invoking us)."""
    payload = {
        "version": _get_version(),
        "schema_version": 1,
        "input": issues.input_path,
        "output": issues.output_path,
        "main_tex": issues.main_tex,
        "dry_run": issues.dry_run,
        "removed_files": issues.removed_files,
        "kept_files": issues.kept_files,
        "errors": issues.errors,
        "warnings": issues.warnings,
        "counts": {
            "removed": len(issues.removed_files),
            "kept": len(issues.kept_files),
            "errors": len(issues.errors),
            "warnings": len(issues.warnings),
        },
        "sizes": {
            "input_bytes": issues.sizes_input,
            "output_bytes": issues.sizes_output,
            "uncompressed_bytes": issues.sizes_uncompressed,
        },
        "compile": issues.compile_result,
        "flatten": issues.flatten,
        "inlined_files": issues.inlined_files,
        "metadata": issues.metadata,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _do_convert(args: argparse.Namespace, cleanup_tmp: list[str]) -> Issues:
    """Run the demo or the regular conversion path. Returns the Issues object
    populated by convert(). Raises ConverterError on fatal failures."""
    if args.demo:
        try:
            import pipeline as _pipeline_mod

            ref = resources.files(_pipeline_mod).joinpath("demo_project.zip")
            demo_zip = Path(str(ref))
        except Exception:
            demo_zip = Path(__file__).parent / "demo_project.zip"
        if not demo_zip.exists():
            raise ConverterError("demo_project.zip not found in package")
        out = Path("demo_project_arxiv.zip")
        print(f"Running demo: {demo_zip} → {out}\n")
        with tempfile.TemporaryDirectory() as cfg_tmp:
            demo_config: Path | None = None
            with zipfile.ZipFile(demo_zip) as zf:
                cfg_name = next(
                    (n for n in zf.namelist() if Path(n).name == "arxiv_config.yaml"),
                    None,
                )
                if cfg_name is not None:
                    demo_config = Path(cfg_tmp) / "arxiv_config.yaml"
                    demo_config.write_bytes(zf.read(cfg_name))
            return convert(
                demo_zip,
                out,
                compile_pdf=args.compile,
                config_path=demo_config,
                dry_run=args.dry_run,
                flatten=args.flatten,
                guide=args.guide,
            )

    inp_raw = args.input
    inp = _resolve_input(inp_raw, cleanup_tmp)
    if args.output:
        out = Path(args.output)
    elif _is_git_url(inp_raw):
        name_part = inp_raw.rstrip("/").rsplit("/", 1)[-1]
        if ":" in name_part:
            name_part = name_part.rsplit(":", 1)[-1].rsplit("/", 1)[-1]
        repo_name = name_part.removesuffix(".git")
        out = Path(f"{repo_name}_arxiv.zip")
    elif Path(inp_raw).is_dir():
        out = Path(f"{Path(inp_raw).name}_arxiv.zip")
    else:
        out = inp.with_stem(inp.stem + "_arxiv")
    config_path = Path(args.config) if args.config else None
    print(f"Converting {inp_raw} → {out}\n")
    return convert(
        inp,
        out,
        main_hint=args.main,
        compile_pdf=args.compile,
        resize=args.resize,
        config_path=config_path,
        dry_run=args.dry_run,
        flatten=args.flatten,
        guide=args.guide,
    )


def main():
    parser = argparse.ArgumentParser(description="Convert LaTeX zip to arXiv-ready zip")
    parser.add_argument("--version", action="version", version=f"latex2arxiv {_get_version()}")
    parser.add_argument("input", nargs="?", help="Input .zip file, directory, or git URL")
    parser.add_argument("output", nargs="?", help="Output .zip file (default: input_arxiv.zip)")
    parser.add_argument("--main", help="Filename of the main .tex file (e.g. JASA_main.tex)")
    parser.add_argument("--compile", action="store_true", help="Compile output with pdflatex and open PDF")
    parser.add_argument(
        "--resize",
        nargs="?",
        const=DEFAULT_MAX_PX,
        type=int,
        metavar="PX",
        help=f"Resize images so longest side <= PX pixels (default: {DEFAULT_MAX_PX} if given without a value)",
    )
    parser.add_argument("--config", metavar="FILE", help="YAML config for custom removal rules (see arxiv_config.yaml)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview what would be removed/processed without writing any output"
    )
    parser.add_argument("--demo", action="store_true", help="Run the built-in demo project (no input file needed)")
    parser.add_argument(
        "--json", action="store_true", help="Emit a machine-readable JSON summary on stdout; route progress to stderr"
    )
    parser.add_argument(
        "--flatten", action="store_true", help="Inline every \\input / \\include / \\subfile into the main .tex"
    )
    parser.add_argument(
        "--guide", action="store_true", help="Write a detailed arXiv upload guide to a text file alongside the output"
    )
    args = parser.parse_args()

    # argparse-level validation. Fail fast before setting up stdout capture —
    # these errors are not part of the JSON envelope contract.
    if not args.demo and not args.input:
        parser.error("the following arguments are required: input")

    # Under --json, capture stdout into a buffer so progress lines don't pollute
    # the JSON payload. The capture is restored in `finally` and the captured
    # text is forwarded to stderr for visibility.
    real_stdout = sys.stdout
    capture_buf: io.StringIO | None = None
    if args.json:
        capture_buf = io.StringIO()
        sys.stdout = capture_buf

    issues: Issues | None = None
    exit_code = 0
    cleanup_tmp: list[str] = []
    try:
        issues = _do_convert(args, cleanup_tmp)
        if issues.errors:
            exit_code = 1
    except ConverterError as e:
        if issues is None:
            issues = Issues()
        # Surface the as-passed input path and its on-disk size even on fatal
        # early-exit so the JSON envelope has something useful for debugging
        # instead of `null` for every field.
        if issues.input_path is None and getattr(args, "input", None):
            issues.input_path = args.input
        if issues.sizes_input is None and issues.input_path:
            try:
                p = Path(issues.input_path)
                if p.is_file():
                    issues.sizes_input = p.stat().st_size
            except (OSError, ValueError):
                pass
        issues.error(str(e))
        exit_code = 1
    finally:
        for d in cleanup_tmp:
            shutil.rmtree(d, ignore_errors=True)
        if args.json:
            sys.stdout = real_stdout
            if capture_buf is not None and capture_buf.getvalue():
                sys.stderr.write(capture_buf.getvalue())
            if issues is None:
                issues = Issues()
            _emit_json(issues)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
