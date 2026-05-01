# latex2arxiv

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/latex2arxiv.svg)](https://pypi.org/project/latex2arxiv/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A command-line tool that converts a LaTeX `.zip` project into an arXiv-ready `.zip` in one command.

```bash
latex2arxiv paper.zip --main main.tex --compile
```

Works with any LaTeX `.zip` — including projects exported directly from Overleaf.

---

> 🚀 **Try it in 30 seconds** — a self-documenting demo is included:
> ```bash
> pip install latex2arxiv
> latex2arxiv demo_project.zip --compile
> ```
> This opens a PDF that explains exactly what the converter does and shows the cleaned output.

---


## What it does

| Stage | Action |
|---|---|
| File pruning | Removes unused `.tex`, `.bib`, image, and all non-essential files (build artifacts, editor files, cover letters, etc.) |
| Comment stripping | Removes `% ...` comments from all `.tex` files |
| Draft cleanup | Removes `\todo{}`, `\hl{}`, `\note{}`, `\fixme{}`, `\begin{comment}` blocks, `\iffalse...\fi` blocks, and draft-only packages |
| BibTeX normalization | Canonical field ordering, deduplication, private field removal |
| `\pdfoutput=1` | Injected before `\documentclass` if missing (required by arXiv) |
| Image resizing | Optional: resize images so longest side ≤ N pixels (helps stay under arXiv's 50MB limit) |
| Compile check | Optional: compiles with `pdflatex` and opens the PDF for review |

Dependency tracking respects `\input`, `\include`, `\subfile`, `\includegraphics`, `\begin{overpic}`, and `\bibliography`. Commented-out commands are ignored.

## Installation

```bash
pip install latex2arxiv
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
latex2arxiv input.zip [output.zip] [--main MAIN_TEX] [--resize PX] [--compile]
```

Or without installing:

```bash
python3 converter.py input.zip [output.zip] [--main MAIN_TEX] [--resize PX] [--compile]
```

**Options**

| Flag | Description |
|---|---|
| `--main FILENAME` | Specify the main `.tex` file (e.g. `JASA_main.tex`). Auto-detected via `\documentclass` if omitted. |
| `--resize PX` | Resize images so longest side ≤ PX pixels (e.g. `--resize 1600`). Requires `Pillow`. |
| `--compile` | Run `pdflatex` on the output and open the resulting PDF. |

**Examples**

```bash
# Basic conversion (auto-detect main file)
latex2arxiv paper.zip

# Specify main file and compile for review
latex2arxiv paper.zip arxiv_ready.zip --main main.tex --compile

# Resize large images to stay under arXiv's 50MB limit
latex2arxiv paper.zip --resize 1600 --compile
```

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
```
