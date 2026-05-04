# latex2arxiv

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/latex2arxiv.svg)](https://pypi.org/project/latex2arxiv/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Validates arXiv compatibility and cleans your LaTeX project in one command.** Built for the Overleaf-export workflow: drop in a `.zip`, get an arXiv-ready `.zip` back, with pre-flight checks that catch submission-blocking issues before you upload.

```bash
latex2arxiv paper.zip --compile
```

📄 **See what the cleaned output looks like** — the bundled demo's compiled PDF is attached to every [GitHub Release](https://github.com/YuZh98/latex2arxiv/releases/latest) (`demo_project_arxiv.pdf`). One click, no install.

---

> 🚀 **Try it in 30 seconds** — a self-documenting demo is included:
> ```bash
> pip install latex2arxiv
> latex2arxiv --demo --compile
> ```
> This opens a PDF that explains exactly what the converter does and shows the cleaned output.

---

## What it does

| Stage | Action |
|---|---|
| **File pruning** | Removes unused `.tex`, `.bib`, image, and all non-essential files (build artifacts, editor files, cover letters, etc.) |
| **Comment stripping** | Removes `% ...` comments from all `.tex` files |
| **Draft cleanup** | Removes `\todo{}`, `\hl{}`, `\note{}`, `\fixme{}`, `\begin{comment}` blocks, `\iffalse...\fi` blocks, and draft-only packages |
| **BibTeX normalization** | Canonical field ordering, deduplication, private field removal |
| **`\pdfoutput=1`** | Injected before `\documentclass` if missing (required by arXiv) |
| **Image resizing** | Optional: resize images so longest side ≤ N pixels (helps keep submission size manageable) |
| **Custom rules** | Optional: remove or unwrap user-defined commands via a config file |
| **Pre-flight checks** | Flags arXiv compatibility issues: shell-escape packages (`minted`, `pythontex`) as errors; biblatex without `.bbl`, output > 50 MB, and problematic filenames as warnings |
| **Compile check** | Optional: compiles with `pdflatex` and opens the PDF for review |

Dependency tracking respects `\input`, `\include`, `\subfile`, `\includegraphics`, `\begin{overpic}`, and `\bibliography`. Commented-out commands are ignored.

**Real-world results on a statistics paper:**
- 950 files → 40 files
- 82 MB → 3 MB

## How does this compare to `arxiv_latex_cleaner`?

[`arxiv_latex_cleaner`](https://github.com/google-research/arxiv-latex-cleaner) is the established tool in this space. It's been around for years, is Google-backed, and has thousands of stars. If maturity and community size are your top priorities, use it.

`latex2arxiv` is newer (just released) and overlaps in scope, but takes a different stance: **submission validation first, cleanup second.** The differences below are the ones a researcher about to upload to arXiv tonight is most likely to feel.

| | `latex2arxiv` | `arxiv_latex_cleaner` |
|---|---|---|
| **Maturity** | New (0.5.0) | Years of usage, ~5k★ |
| **Output** | `.zip` in → `.zip` out | Cleaned directory (you zip yourself) |
| **Pre-flight checks** | `[error]` and `[warn]` severity, non-zero exit on errors | None |
| **Compile preview** (`--compile`) | Runs `pdflatex` and opens the PDF | Not built in |
| **Auto-detect main `.tex`** | Yes (with `--main` override) | Specify input folder manually |
| **Brace-balanced config matcher** | Handles `\deleted{see \cite{x}}` correctly | Regex-based |
| **BibTeX normalization** | Field ordering, dedup, private-field strip | Preserves or deletes `.bib` |
| **`\pdfoutput=1` auto-injection** | Yes | No |
| **`--dry-run` preview** | Yes | No |
| **Built-in demo** (`--demo`) | Yes — `latex2arxiv --demo --compile` | No |
| **Image resizing** | Yes (Pillow) | Yes (Pillow); also PDF compression via Ghostscript |
| **PDF/Ghostscript compression** | No | Yes |
| **PNG → JPG conversion** | No | Yes |

When to pick `arxiv_latex_cleaner` instead: you need PDF compression via Ghostscript, PNG→JPG conversion, or you want the most battle-tested option.

When to pick `latex2arxiv`: you want pre-flight errors that block submission to fail your CI, you want a one-command zip-in/zip-out workflow, or you submit revisions with `\deleted{}` / `\added{}` markup that needs nested-brace handling.

## Installation

```bash
pip install latex2arxiv
```

On macOS, if you get an `externally-managed-environment` error, use [`pipx`](https://pipx.pypa.io/) instead:

```bash
brew install pipx
pipx install latex2arxiv
```

Or from source:

```bash
git clone https://github.com/YuZh98/latex2arxiv
cd latex2arxiv
pip install .
```

`pdflatex` is required only for the `--compile` flag (install via [TeX Live](https://tug.org/texlive/) or [MacTeX](https://tug.org/mactex/)).

## Usage

```bash
latex2arxiv input.zip [output.zip] [--main MAIN_TEX] [--resize PX] [--config FILE] [--compile]
```

| Flag | Description |
|---|---|
| `--main FILENAME` | Specify the main `.tex` file (e.g. `JASA_main.tex`). Auto-detected via `\documentclass` if omitted. |
| `--resize PX` | Resize images so longest side ≤ PX pixels (e.g. `--resize 1600`). Requires `Pillow`. |
| `--config FILE` | YAML config file for custom removal rules (see below). |
| `--compile` | Run `pdflatex` on the output and open the resulting PDF. |
| `--dry-run` | Preview what would be removed/processed without writing any output. |
| `--demo` | Run the built-in demo project (no input file needed). |

**Examples**

```bash
# Basic conversion (auto-detect main file)
latex2arxiv paper.zip

# Specify main file and compile for review
latex2arxiv paper.zip arxiv_ready.zip --main main.tex --compile

# Resize large images to reduce submission size
latex2arxiv paper.zip --resize 1600 --compile

# Apply custom removal rules
latex2arxiv paper.zip --config arxiv_config.yaml --compile

# Preview what would be removed without writing any output
latex2arxiv paper.zip --dry-run

# Run the built-in demo (no input file needed)
latex2arxiv --demo --compile
```

The tool exits non-zero if any pre-flight error fires (e.g. `\usepackage{minted}` detected) — useful for CI gating. Warnings do not affect the exit code.

## Custom removal rules (`--config`)

For revision markup and other project-specific cleanup, create a YAML config file.
A template is provided in [`arxiv_config.yaml`](arxiv_config.yaml).

```yaml
# Remove command AND its argument (text is lost)
commands_to_delete:
  - \deleted
  - \revision

# Remove command but KEEP its argument text
commands_to_unwrap:
  - \color{red}       # \color{red}text → text
  - \textcolor{red}   # \textcolor{red}{text} → text
  - \added            # \added{new text} → new text

# Remove entire environments
environments_to_delete:
  - response

# Raw regex replacements
replacements:
  - pattern: '\\added\{([^}]*)\}'
    replacement: '\1'
```

No extra dependencies required — the config parser is built in.

## Caveats

**Dynamically constructed filenames** — if your code uses a macro for an image path (e.g. `\includegraphics{\figpath/fig1}`), the tool cannot resolve it statically and will delete the image. Expand macros before running the converter.

**Custom verbatim environments** — comments inside standard `verbatim`, `lstlisting`, and `minted` blocks are preserved. Non-standard verbatim-like environments may not be protected.

**`\subfile` vs `\input` path resolution** — image paths in `\input`/`\include`d files are resolved relative to the project root (how LaTeX works). Paths in `\subfile` documents are resolved relative to the subfile's own directory. Unusual nested path setups may cause images to be incorrectly pruned; use `--compile` to verify.

**BibTeX normalization requires `bibtexparser`** — install with `pip install bibtexparser`. If not installed, the `.bib` file is passed through unchanged.

**`--compile` is a local sanity check** — a successful local compile does not guarantee arXiv will compile it. arXiv uses specific TeX Live versions with fixed package sets. Always check the [arXiv submission preview](https://arxiv.org/help/submit) after uploading.

**Custom style/class files** — if your project includes a `.cls` or `.sty` file, the tool keeps it and warns you. Verify it is not already provided by TeX Live; if it is, remove it from your submission to avoid conflicts.

**Double-spaced / referee mode** — the tool warns if it detects `referee`, `doublespace`, or `\doublespacing` in your source. arXiv requires single-spaced submissions.

**`\today` in `\date`** — arXiv occasionally rebuilds PDFs, which will change the displayed date. The tool warns if it detects `\today` in `\date`.

## Project structure

```
converter.py        # CLI entry point
pipeline/
    tex.py          # Comment stripping, draft annotation removal
    bibtex.py       # BibTeX normalization
    deps.py         # Dependency graph (tex includes, images, bib files)
    images.py       # Image resizing
    config.py       # User-defined removal rules
arxiv_config.yaml   # Sample config file
```
