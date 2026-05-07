# latex2arxiv

[![PyPI](https://img.shields.io/pypi/v/latex2arxiv.svg)](https://pypi.org/project/latex2arxiv/)
[![Downloads](https://img.shields.io/pypi/dm/latex2arxiv.svg)](https://pypi.org/project/latex2arxiv/)
[![Tests](https://github.com/YuZh98/latex2arxiv/actions/workflows/test.yml/badge.svg)](https://github.com/YuZh98/latex2arxiv/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Validates arXiv compatibility and cleans your LaTeX project in one command — project in, arXiv-ready zip out.**

If you submit papers to arXiv, this tool is for you. Point it at a zip, a directory, or a git URL — get a clean, arXiv-ready `.zip` back with pre-flight checks that catch submission-blocking issues before you upload. Your input is never overwritten.

```bash
latex2arxiv paper.zip --compile          # zip
latex2arxiv paper/ --compile             # directory
latex2arxiv https://github.com/u/p.git   # git URL
```

Try the built-in demo:

```bash
pip install latex2arxiv
latex2arxiv --demo --compile
```

This processes a bundled self-documenting paper and opens the cleaned PDF. The cleaned demo's PDF is attached to every [GitHub Release](https://github.com/YuZh98/latex2arxiv/releases/latest) as `demo_project_arxiv.pdf` — see the output without installing.

## Before / After

On a real statistics paper: **934 → 40 files, 80.6 MB → 3.1 MB**.

<img src="docs/demo.gif" width="700" alt="latex2arxiv demo">

| Before (Overleaf export) | After (latex2arxiv output) |
|---|---|
| 📁 Images/ | 📁 Images/ |
| 📄 JASA_main.tex | 📄 JASA_main.tex[^main] |
| 📄 JASA_main_backup.tex | 📄 ref.bib |
| 📄 main_bak_svm.tex | 📄 Supplementary_Materials.tex[^supp] |
| 📄 cover_letter.md | |
| 📄 response.tex | |
| 📄 ref.bib | |
| 📄 JASA_main.aux/.log/.bbl/.pdf | |
| 📁 jasa_comments/, jasa_revision/ | |
| ... (and ~930 more) | |
| **934 files, 80.6 MB** | **40 files, 3.1 MB** |

## Who is this for?

- You wrote your paper in Overleaf and need a clean, arXiv-ready zip without manually pruning files. → [Overleaf → arXiv quickstart](docs/overleaf.md)
- You want to gate a paper repo's CI on arXiv compliance so a bad merge can't slip through. → `--dry-run` + non-zero exit on `[error]` ([details](#pre-flight-checks))
- Your paper uses custom revision-tracking macros (`\added`, `\deleted`, `\textcolor{red}{...}`) that you need stripped before submission. → [Custom removal rules](#custom-removal-rules---config)

## What it does

| Feature | What it does |
|---|---|
| 📦 **One command, any input** | Accepts a `.zip`, directory, or git URL; outputs an arXiv-ready `.zip`; optionally compiles and opens the PDF for review |
| ✂️ **Prunes your project to submission-ready** | Keeps only files reachable from your main `.tex`; removes build artifacts, editor files, cover letters, unused figures |
| 🧹 **Cleans your `.tex`** | Strips comments, removes `\todo{}` / `\hl{}` / draft packages, handles nested braces correctly (`\deleted{see \cite{x}}` works) |
| 🚨 **Catches submission blockers before you upload** | `[error]` for shell-escape packages that will fail on arXiv (`minted`, `pythontex`); `[warn]` for biblatex without `.bbl`, missing index files, oversized output, problematic filenames — [full list](#pre-flight-checks) |

Also: BibTeX normalization, `\pdfoutput=1` injection, image resizing (Pillow), `--dry-run` preview, `--demo` for first-run.

Dependency tracking respects `\input`, `\include`, `\subfile`, `\includegraphics`, `\graphicspath`, and `\bibliography`. Commented-out commands are ignored.

## `latex2arxiv` vs. `arxiv_latex_cleaner`

[`arxiv_latex_cleaner`](https://github.com/google-research/arxiv-latex-cleaner) is the incumbent — Google-backed, mature, and cleans well. The key difference: it won't tell you that `\usepackage{minted}` will fail on arXiv, won't produce the `.zip` you upload, and has no exit code for CI gating.

| | `latex2arxiv` | `arxiv_latex_cleaner` |
|---|---|---|
| Output format | Any input → `.zip` | Cleaned directory |
| Pre-flight `[error]` / `[warn]` ([details](#pre-flight-checks)) | ✅ | ❌ |
| Non-zero exit on errors | ✅ | ❌ |
| `--compile` preview | ✅ | ❌ |
| Auto-detect main `.tex` | ✅ | ❌ |
| Brace-balanced config | ✅ | ❌ |
| BibTeX normalization | ✅ | ❌ |
| Auto `\pdfoutput=1` injection | ✅ | ❌ |
| `--dry-run` | ✅ | ❌ |
| Built-in `--demo` | ✅ | ❌ |
| Image resizing (Pillow) | ✅ | ✅ |
| PDF compression (Ghostscript) | ❌ | ✅ |
| PNG → JPG conversion | ❌ | ✅ |
| Maturity | 7 regression fixtures, live `pdflatex`+`biber` end-to-end CI | ~5k★, years |

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

Once installed, try the built-in demo to see the tool in action:

```bash
latex2arxiv --demo --compile
```

## Usage

```bash
latex2arxiv input [output.zip] [--main MAIN_TEX] [--resize PX] [--config FILE] [--compile]
```

`input` can be a `.zip` file, a directory of LaTeX sources, or a git URL (https or ssh). Directories are zipped internally; git URLs are cloned with `--depth 1`.

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
latex2arxiv paper.zip                                  # zip input
latex2arxiv paper/                                     # directory input
latex2arxiv https://github.com/user/paper.git          # git URL input
latex2arxiv paper.zip out.zip --main main.tex --compile
latex2arxiv paper.zip --resize 1600 --compile          # shrink images
latex2arxiv paper.zip --config arxiv_config.yaml       # custom rules
latex2arxiv paper.zip --dry-run                        # preview without writing
latex2arxiv --demo --compile                           # run the built-in demo
```

## Pre-flight checks

Before producing the output zip, latex2arxiv validates the project against [arXiv's LaTeX submission guide](https://info.arxiv.org/help/submit_tex.html). `[error]` lines block submission (the tool exits non-zero, useful for CI gating); `[warn]` lines are advisory and do not affect the exit code.

```text
$ latex2arxiv paper.zip --dry-run
  [error] \usepackage{minted} requires shell-escape — arXiv compiles without it; this submission will fail to build
  [error] \usepackage{psfig} — arXiv no longer supports the psfig package
  [warn]  \today used in \date — arXiv may rebuild the PDF and the date will change
  [warn]  .eps image found: photo.eps — pdflatex does not support .eps; convert to .pdf or .png
  [warn]  \printindex used but no .ind file at root — build locally and re-run latex2arxiv

Summary: 2 errors, 7 warnings
```

Either `[error]` line would have caused arXiv to reject the submission after upload. The exit code is non-zero on errors, so a CI step like `latex2arxiv paper.zip --dry-run` fails the build before the bad submission ever leaves the repo.

See [docs/pre-flight.md](docs/pre-flight.md) for the full list of checks and silent fixes.

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

# Raw regex (last resort — prefer the verbs above when they fit).
# Recipe: any-color \textcolor → unwrapped text. Won't span nested
# commands like \cite — for those, use one commands_to_unwrap per color.
replacements:
  - pattern: '\\textcolor\{[^}]*\}\{([^}]*)\}'
    replacement: '\1'
```

The config parser is built in (no extra dependencies). The brace-balanced matcher correctly handles nested commands like `\deleted{see \cite{x}}`.

Unknown top-level keys warn — typos like `command_to_delete` (singular) no longer silently no-op. A malformed regex in any `replacements` rule emits a `[warn]` naming the rule's index, then skips just that rule; other rules still apply.

## CI / pre-commit integration

A GitHub Action and `pre-commit` hook are available for paper repos. See [docs/ci.md](docs/ci.md) for full setup with examples.

You can also use `latex2arxiv` directly in any CI script:

```yaml
- run: pip install latex2arxiv && latex2arxiv paper.zip --dry-run
```

The exit code is non-zero on `[error]`, so this fails the job automatically.

## Known limitations

**Dynamically constructed filenames** — `\includegraphics{\figpath/fig1}` cannot be resolved statically and the image will be deleted. Expand path macros before running.

**`\subfile` vs `\input` path resolution** — `\input`/`\include` paths resolve relative to the project root; `\subfile` paths resolve relative to the subfile's own directory. Unusual nested setups may cause images to be incorrectly pruned; use `--compile` to verify.

**`--compile` is a local sanity check** — a successful local compile doesn't guarantee arXiv will compile it. arXiv pins specific TeX Live versions. Always check the [arXiv submission preview](https://arxiv.org/submit) after uploading.

[^main]: `JASA_main.tex` is identified as the main file via auto-detection (or pass `--main JASA_main.tex` to be explicit).
[^supp]: `Supplementary_Materials.tex` is kept because it's a `\subfile` dependency of the main file.
