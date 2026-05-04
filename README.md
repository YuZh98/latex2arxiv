# latex2arxiv

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/latex2arxiv.svg)](https://pypi.org/project/latex2arxiv/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Validates arXiv compatibility and cleans your LaTeX project in one command — zip in, zip out.**

If you submit papers to arXiv, this tool is for you. Drop in a `.zip`, get a new arXiv-ready `.zip` back — your input is never overwritten — with pre-flight checks that catch submission-blocking issues before you upload.

```bash
latex2arxiv paper.zip --compile
```

Try the built-in demo:

```bash
pip install latex2arxiv
latex2arxiv --demo --compile
```

This processes a bundled self-documenting paper and opens the cleaned PDF. The cleaned demo's PDF is attached to every [GitHub Release](https://github.com/YuZh98/latex2arxiv/releases/latest) as `demo_project_arxiv.pdf` — see the output without installing.

[What it does](#what-it-does) • [Before/After](#before--after) • [Install](#installation) • [Usage](#usage) • [Pre-flight checks](#pre-flight-checks) • [vs `arxiv_latex_cleaner`](#latex2arxiv-vs-arxiv_latex_cleaner)

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

## What it does

| Feature | What it does |
|---|---|
| 📦 **One-command zip-in / zip-out** | No directory dance, no manual repack; optionally compiles and opens the PDF for review |
| ✂️ **Prunes your project to submission-ready** | Keeps only files reachable from your main `.tex`; removes build artifacts, editor files, cover letters, unused figures |
| 🧹 **Cleans your `.tex`** | Strips comments, removes `\todo{}` / `\hl{}` / draft packages, handles nested braces correctly (`\deleted{see \cite{x}}` works) |
| 🚨 **Catches submission blockers before you upload** | `[error]` for shell-escape packages that will fail on arXiv (`minted`, `pythontex`); `[warn]` for biblatex without `.bbl`, missing index files, oversized output, problematic filenames — [full list](#pre-flight-checks) |

Also: BibTeX normalization, `\pdfoutput=1` injection, image resizing (Pillow), `--dry-run` preview, `--demo` for first-run.

Dependency tracking respects `\input`, `\include`, `\subfile`, `\includegraphics`, `\graphicspath`, and `\bibliography`. Commented-out commands are ignored.

## `latex2arxiv` vs. `arxiv_latex_cleaner`

[`arxiv_latex_cleaner`](https://github.com/google-research/arxiv-latex-cleaner) is the established tool in this space — Google-backed, ~5k★, years of usage. If you want the most battle-tested option, use it.

### Where `latex2arxiv` is different

| ❌ Without `latex2arxiv` | ✅ With `latex2arxiv` |
|---|---|
| You upload, wait for arXiv to compile, get a cryptic failure email about `\usepackage{minted}`, re-upload and wait again. | Pre-flight checks catch it locally with a clear `[error]` message. Exits non-zero so your CI catches it too. |
| `arxiv_latex_cleaner` cleans into a directory — you still figure out what to zip, hope you didn't miss a `.bbl`. | The output *is* the file you upload. Nothing to figure out. |
| `\deleted{see \cite{smith}}` silently leaves `\cite{smith}` in your paper — PDF looks fine locally, reviewer sees a stray citation. | Brace-balanced matcher removes the whole nested expression correctly. |

### Where `arxiv_latex_cleaner` is stronger

| Advantage | Notes |
|---|---|
| **Maturity** | Thousands of papers cleaned, larger contributor pool, more edge cases discovered. |
| **Ghostscript-based PDF compression** | We don't bundle this. |
| **PNG → JPG conversion** | We don't do this. |

### Full feature comparison

| | `latex2arxiv` | `arxiv_latex_cleaner` |
|---|---|---|
| Output format | `.zip` → `.zip` | Cleaned directory |
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

Once installed, try the built-in demo to see the tool in action:

```bash
latex2arxiv --demo --compile
```

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

## Pre-flight checks

Before producing the output zip, latex2arxiv validates the project against [arXiv's LaTeX submission guide](https://info.arxiv.org/help/submit_tex.html). `[error]` lines block submission (the tool exits non-zero, useful for CI gating); `[warn]` lines are advisory and do not affect the exit code.

| Severity | Trigger | Why it matters |
|---|---|---|
| 🛑 error | `\usepackage{minted}` / `pythontex` / `shellesc` | Require `--shell-escape`; arXiv compiles without it. |
| 🛑 error | `\usepackage{psfig}` | arXiv no longer supports the psfig package. |
| ⚠️ warn | `\usepackage{xr}` or `xr-hyper` | File paths/locations differ on arXiv; external-document references break. |
| ⚠️ warn | Main `.tex` not at the submission root | arXiv compiles from root; subdirectory main files aren't found. |
| ⚠️ warn | `\printindex` / `\printglossary` / `\printnomenclature` without matching `.ind` / `.gls` / `.nls` | arXiv doesn't run makeindex or glossary processors; the printed section silently disappears. |
| ⚠️ warn | `\usepackage{biblatex}` (or `\addbibresource`) without `<main>.bbl` shipped | If arXiv can't resolve any `.bib` file, your submission is blocked. |
| ⚠️ warn | `\documentclass[referee]` / `[doublespace]` / `\doublespacing` | arXiv requires single-spaced submissions. |
| ⚠️ warn | `\today` inside `\date{...}` | arXiv may rebuild the PDF; the date will change. |
| ⚠️ warn | `\subfile`'d document containing `\bibliographystyle` | Likely a standalone supplement; remove the `\subfile` line to avoid duplicate bibliography commands. |
| ⚠️ warn | `.eps` images shipped | `pdflatex` doesn't support `.eps`; convert to `.pdf` or `.png`. |
| ⚠️ warn | Custom `.cls` / `.sty` files | Verify they aren't already provided by TeX Live. |
| ⚠️ warn | Filename has spaces or non-ASCII characters | Breaks `\input` and `\includegraphics` resolution. |
| ⚠️ warn | Output `.zip` larger than 50 MB | arXiv has size limits; consider `--resize` or splitting supplementary materials. |

In addition to surfacing issues, the conversion silently fixes common pitfalls:

- Inserts `\pdfoutput=1` (or normalizes any `\pdfoutput=N`) in the main `.tex`, so arXiv selects pdfLaTeX.
- Preserves `00README` / `00README.XXX` files at root for arXiv processor hints.
- Strips comments and standard draft annotations (`\todo`, `\hl`, ...) and packages (`todonotes`, `comment`, ...).

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

**Safety guarantees.** Unknown top-level keys warn — typos like `command_to_delete` (singular) no longer silently no-op. A malformed regex in any `replacements` rule emits a `[warn]` naming the rule's index, then skips just that rule; other rules still apply.

## Caveats ⚠️

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

[^main]: `JASA_main.tex` is identified as the main file via auto-detection (or pass `--main JASA_main.tex` to be explicit).
[^supp]: `Supplementary_Materials.tex` is kept because it's a `\subfile` dependency of the main file.
