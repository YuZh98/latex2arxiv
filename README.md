# latex-arxiv-converter

A command-line tool that converts an Overleaf/LaTeX `.zip` project into an arXiv-ready `.zip`.

## What it does

| Stage | Action |
|---|---|
| File pruning | Removes unused `.tex`, `.bib`, image, and all non-essential files (build artifacts, editor files, cover letters, etc.) |
| Comment stripping | Removes `% ...` comments from all `.tex` files |
| Draft cleanup | Removes `\todo{}`, `\hl{}`, `\note{}`, `\fixme{}` and draft-only packages |
| BibTeX normalization | Canonical field ordering, deduplication, private field removal |
| `\pdfoutput=1` | Injected before `\documentclass` if missing (required by arXiv) |
| Compile check | Optional: compiles with `pdflatex` and opens the PDF for review |

Dependency tracking respects `\input`, `\include`, `\subfile`, `\includegraphics`, `\begin{overpic}`, and `\bibliography`. Commented-out commands are ignored.

## Installation

```bash
pip install -r requirements.txt
```

`pdflatex` is required only for the `--compile` flag (install via [TeX Live](https://tug.org/texlive/) or [MacTeX](https://tug.org/mactex/)).

## Usage

```bash
python3 converter.py input.zip [output.zip] [--main MAIN_TEX] [--compile]
```

**Options**

| Flag | Description |
|---|---|
| `--main FILENAME` | Specify the main `.tex` file (e.g. `JASA_main.tex`). Auto-detected via `\documentclass` if omitted. |
| `--compile` | Run `pdflatex` on the output and open the resulting PDF. |

**Examples**

```bash
# Basic conversion (auto-detect main file)
python3 converter.py paper.zip

# Specify main file and compile for review
python3 converter.py paper.zip arxiv_ready.zip --main main.tex --compile
```

## Project structure

```
converter.py        # CLI entry point
pipeline/
    tex.py          # Comment stripping, draft annotation removal
    bibtex.py       # BibTeX normalization
    deps.py         # Dependency graph (tex includes, images, bib files)
```
