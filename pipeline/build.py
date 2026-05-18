"""Output compilation: run pdflatex/biber, surface errors, open the PDF.

Used only when the CLI is invoked with `--compile`. Imported by converter.py
and called from convert() at the end of a successful conversion."""

import re
import sys
import shutil
import zipfile
import tempfile
import subprocess
from pathlib import Path

from pipeline.types import ConverterError


def _open_file(path: Path) -> None:
    """Open a file with the OS default viewer, cross-platform."""
    if sys.platform == "win32":
        subprocess.run(["start", str(path)], shell=True)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])


def _format_pdflatex_errors(stdout: str, max_errors: int = 5) -> str:
    """Pair each ``! ...`` error in pdflatex stdout with its file/line context.

    Per error, returns a 3-line block: the ``!`` line, the ``l.NN <prefix>``
    line marker, and the source-line suffix pdflatex prints below it. The
    lookahead from a ``!`` line stops at the next ``!``, the ``l.NN`` line,
    or 6 lines, whichever comes first — so cascading errors with no marker
    yield just their ``!`` line rather than borrowing the next error's marker.
    Capped at ``max_errors`` blocks; blocks are joined by a blank line.
    """
    lines = stdout.splitlines()
    blocks: list[str] = []
    for i, line in enumerate(lines):
        if not line.startswith("!"):
            continue
        block = [line]
        for j in range(i + 1, min(i + 7, len(lines))):
            if lines[j].startswith("!"):
                break
            if lines[j].startswith("l."):
                block.append(lines[j])
                if j + 1 < len(lines):
                    block.append(lines[j + 1])
                break
        blocks.append("\n".join(block))
        if len(blocks) >= max_errors:
            break
    return "\n\n".join(blocks)


def _compile(output_zip: Path, main_hint: str | None):
    """Extract output zip, run pdflatex twice, and open the resulting PDF."""
    with tempfile.TemporaryDirectory() as tmpdir:
        compile_dir = Path(tmpdir)
        with zipfile.ZipFile(output_zip) as zf:
            compile_dir_abs = compile_dir.resolve()
            for name in zf.namelist():
                target = (compile_dir / name).resolve()
                try:
                    target.relative_to(compile_dir_abs)
                except ValueError:
                    raise ConverterError(f"output zip contains a path-traversal member — refusing to compile: {name!r}")
            zf.extractall(compile_dir)

        # Find main tex
        if main_hint:
            main_tex = next((p for p in compile_dir.rglob("*.tex") if p.name == main_hint), None)
        else:
            main_tex = next(
                (
                    p
                    for p in compile_dir.rglob("*.tex")
                    if r"\documentclass" in p.read_text(encoding="utf-8", errors="replace")
                ),
                None,
            )
        if main_tex is None:
            print("  [compile] ERROR: could not find main .tex in output zip")
            return

        print(f"\nCompiling {main_tex.name} ...")
        run_dir = main_tex.parent
        tex_name = main_tex.name
        bib_stem = main_tex.stem

        def run_pdflatex(final=False):
            try:
                result = subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", tex_name], cwd=run_dir, capture_output=True, timeout=300
                )
            except FileNotFoundError:
                print(
                    "  [compile] pdflatex not found — install TeX Live "
                    "(https://tug.org/texlive/) or MacTeX to use --compile."
                )
                return False
            except subprocess.TimeoutExpired:
                print("  [compile] pdflatex timed out after 5 minutes")
                return False
            stdout = result.stdout.decode("utf-8", errors="replace")
            if final and ("! Fatal error" in stdout or ("! " in stdout and "Output written" not in stdout)):
                print("  [compile] pdflatex errors:")
                print(_format_pdflatex_errors(stdout))
                return False
            return True

        if not run_pdflatex():
            # pdflatex not available or timed out — abort early; subsequent calls
            # would repeat the same error.
            return

        # Run biber for biblatex projects, else bibtex.
        bib_files = list(run_dir.rglob("*.bib"))
        if bib_files:
            main_nc = re.sub(r"(?<!\\)%[^\n]*", "", main_tex.read_text(encoding="utf-8", errors="replace"))
            uses_biblatex = bool(
                re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\bbiblatex\b[^}]*\}", main_nc)
                or re.search(r"\\addbibresource\{", main_nc)
            )
            cmd = "biber" if uses_biblatex else "bibtex"
            print(f"  Running {cmd} ...")
            try:
                result = subprocess.run([cmd, bib_stem], cwd=run_dir, capture_output=True, timeout=300)
            except FileNotFoundError:
                print(
                    f"  [compile] {cmd} not found — install it (part of TeX Live) "
                    f"or pre-compile your .bbl and ship it. Continuing without "
                    f"bibliography processing; citations will be unresolved."
                )
                result = None
            except subprocess.TimeoutExpired:
                print(f"  [compile] {cmd} timed out after 5 minutes")
                result = None
            if result is not None and result.returncode != 0:
                # biber emits to stderr; bibtex emits to stdout — pick whichever has content.
                err = result.stderr.decode("utf-8", errors="replace").strip()
                out = result.stdout.decode("utf-8", errors="replace").strip()
                msg = err or out
                if msg:
                    tail = "\n".join(msg.splitlines()[-10:])
                    print(f"  [compile] {cmd} failed (exit {result.returncode}):")
                    print(tail)

        # Second and third pass to resolve references
        run_pdflatex()
        if not run_pdflatex(final=True):
            return

        pdf = main_tex.with_suffix(".pdf")
        if pdf.exists():
            out_pdf = output_zip.with_suffix(".pdf")
            shutil.copy(pdf, out_pdf)
            print(f"  PDF → {out_pdf}")
            _open_file(out_pdf)
        else:
            print("  [compile] PDF not produced")
