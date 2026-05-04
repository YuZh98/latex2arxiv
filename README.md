# latex2arxiv

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/latex2arxiv.svg)](https://pypi.org/project/latex2arxiv/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Validates arXiv compatibility and cleans your LaTeX project in one command.**

If you submit papers to arXiv — especially from Overleaf — this tool is for you. Drop in a `.zip`, get an arXiv-ready `.zip` back, with pre-flight checks that catch submission-blocking issues before you upload.

On a real statistics paper: **950 → 40 files, 82 MB → 3 MB**.

```bash
latex2arxiv paper.zip --compile
```

```
  main tex: paper.tex
  remove: .DS_Store
  remove: cover_letter.md
  remove: paper.aux
  remove: figures/old_unused.pdf
  ... (43 more)
  [warn] \today used in \date — arXiv may rebuild the PDF and the date will change

Done → paper_arxiv.zip
Summary: 47 removed, 12 kept | 79.1 MB → 3.2 MB | 0 errors, 1 warning

Compiling paper.tex ...
  PDF → paper_arxiv.pdf
```

The cleaned demo's PDF is attached to every [GitHub Release](https://github.com/YuZh98/latex2arxiv/releases/latest) as `demo_project_arxiv.pdf` — see the output without installing.

## What it does

- **File pruning** — keeps only files reachable from your main `.tex`; removes everything else (build artifacts, editor files, cover letters, unused figures)
- **arXiv compatibility checks** — `[error]` for shell-escape packages (`minted`, `pythontex`); `[warn]` for biblatex without `.bbl`, output > 50 MB, problematic filenames, and other gotchas
- **Comment + draft cleanup** — strips `% ...` comments; removes `\todo{}`, `\hl{}`, `\note{}`, `\fixme{}`, `\begin{comment}` blocks, `\iffalse...\fi` blocks, and draft-only packages
- **`\pdfoutput=1` auto-injection** — arXiv requires it; easy to forget
- **BibTeX normalization** — canonical field ordering, deduplication, private-field strip (requires `bibtexparser`)
- **Image resizing** (optional) — caps longest side at N pixels via Pillow
- **Custom revision-markup rules** (optional) — YAML config; brace-balanced matcher correctly handles `\deleted{see \cite{x}}`
- **`--compile`** — runs `pdflatex` and opens the cleaned PDF for review

Dependency tracking respects `\input`, `\include`, `\subfile`, `\includegraphics`, `\graphicspath`, and `\bibliography`. Commented-out commands are ignored.

## How does this compare to `arxiv_latex_cleaner`?

[`arxiv_latex_cleaner`](https://github.com/google-research/arxiv-latex-cleaner) is the established tool in this space — Google-backed, ~5k★, years of usage. If you want the most battle-tested option, use it.

### Where `latex2arxiv` is different

- **Pre-flight checks with severity levels.** `[error]` blocks submission and exits non-zero (CI-friendly); `[warn]` flags risk. Nothing else in this space does this.
- **One-command zip-in / zip-out workflow.** Drop a `.zip`, get a `.zip` back, optionally compile and preview the PDF. No directory dance, no manual repack.
- **Brace-balanced config matcher.** `\deleted{see \cite{x}}` and `\added{some \emph{nested} text}` work correctly — naive regex-based cleaners silently leave nested content behind.
- **`\pdfoutput=1` auto-injection** and **BibTeX normalization** out of the box.

### Where `arxiv_latex_cleaner` is stronger

- **Maturity** — thousands of papers cleaned, larger contributor pool, more edge cases discovered.
- **Ghostscript-based PDF compression** — we don't bundle this.
- **PNG → JPG conversion** — we don't do this.

### Full feature comparison

| | `latex2arxiv` | `arxiv_latex_cleaner` |
|---|---|---|
| Output format | `.zip` → `.zip` | Cleaned directory |
| Pre-flight `[error]` / `[warn]` | ✅ | ❌ |
| Non-zero exit on errors | ✅ | ❌ |
| `--compile` preview | ✅ | ❌ |
| Auto-detect main `.tex` | ✅ | ❌ |
| Brace-balanced config | ✅ | ❌ |
| BibTeX normalization | ✅ | ❌ |
| `\pdfoutput=1` injection | ✅ | ❌ |
| `--dry-run` | ✅ | ❌ |
| Built-in `--demo` | ✅ | ❌ |
| Image resizing (Pillow) | ✅ | ✅ |
| PDF compression (Ghostscript) | ❌ | ✅ |
| PNG → JPG conversion | ❌ | ✅ |
| Maturity | New (0.5.0) | ~5k★, years |

## Installation

```bash
pip install latex2arxiv
```

On macOS, if you get an `externally-managed-environment` error, use [`pipx`](https://pipx.pypa.io/):

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

`pdflatex` is required only for `--compile` (install via [TeX Live](https://tug.org/texlive/) or [MacTeX](https://tug.org/mactex/)).

Once installed, try the built-in demo to see the tool in action — no input file needed:

```bash
latex2arxiv --demo --compile
```

This processes a bundled self-documenting paper and opens the cleaned PDF.

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
latex2arxiv paper.zip                                  # auto-detect main, basic conversion
latex2arxiv paper.zip out.zip --main main.tex --compile
latex2arxiv paper.zip --resize 1600 --compile          # shrink images
latex2arxiv paper.zip --config arxiv_config.yaml       # custom rules
latex2arxiv paper.zip --dry-run                        # preview without writing
latex2arxiv --demo --compile                           # run the built-in demo
```

The tool exits non-zero if any pre-flight error fires (e.g. `\usepackage{minted}`) — useful for CI gating. Warnings do not affect the exit code.

## Custom removal rules (`--config`)

For revision markup and other project-specific cleanup, create a YAML config file. A template is in [`arxiv_config.yaml`](arxiv_config.yaml).

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

The config parser is built in (no extra dependencies). The brace-balanced matcher correctly handles nested commands like `\deleted{see \cite{x}}`.

## Known limitations

**Dynamically constructed filenames** — `\includegraphics{\figpath/fig1}` cannot be resolved statically and the image will be deleted. Expand path macros before running.

**`\subfile` vs `\input` path resolution** — `\input`/`\include` paths resolve relative to the project root; `\subfile` paths resolve relative to the subfile's own directory. Unusual nested setups may cause images to be incorrectly pruned; use `--compile` to verify.

**Inline `\verb|...|`** — comment-stripping and draft-removal don't currently protect inline `\verb|...|`. A `%` or `\todo{...}` inside `\verb|...|` may get mangled. Standard `verbatim`, `lstlisting`, and `minted` *block* environments are protected.

**`--compile` is a local sanity check** — a successful local compile doesn't guarantee arXiv will compile it. arXiv pins specific TeX Live versions. Always check the [arXiv submission preview](https://arxiv.org/help/submit) after uploading.

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
