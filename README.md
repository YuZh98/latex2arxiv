# latex2arxiv

[![PyPI](https://img.shields.io/pypi/v/latex2arxiv.svg)](https://pypi.org/project/latex2arxiv/)
[![Downloads](https://img.shields.io/pypi/dm/latex2arxiv.svg)](https://pypi.org/project/latex2arxiv/)
[![Tests](https://github.com/YuZh98/latex2arxiv/actions/workflows/test.yml/badge.svg)](https://github.com/YuZh98/latex2arxiv/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Submit to arXiv without the headache. One command cleans your project, catches rejection-causing errors, and walks you through the upload.**

```bash
latex2arxiv paper.zip --compile          # clean + verify PDF
latex2arxiv paper.zip --compile --guide  # + step-by-step upload instructions
latex2arxiv paper/ --compile             # directory input
latex2arxiv https://github.com/u/p.git   # git URL input
```

> Your original project is never modified. All output goes to a new `_arxiv.zip` file.

Try the built-in demo:

```bash
pip install latex2arxiv
latex2arxiv --demo --compile --guide
```

This processes a bundled self-documenting paper, opens the cleaned PDF, and writes a step-by-step arXiv upload guide with copy-paste-ready metadata. The cleaned demo's PDF is attached to every [GitHub Release](https://github.com/YuZh98/latex2arxiv/releases/latest) as `demo_project_arxiv.pdf`.

## Before / After

On a real statistics paper ([arXiv:2504.11630](https://arxiv.org/abs/2504.11630)): **934 → 40 files, 80.6 MB → 3.1 MB**.

<img src="docs/demo.gif" width="700" alt="latex2arxiv demo">

| Before (Overleaf export) | After (latex2arxiv output) |
|---|---|
| 📁 Images/ | 📁 Images/ |
| 📄 JASA_main.tex | 📄 JASA_main.tex |
| 📄 JASA_main_backup.tex | 📄 ref.bib |
| 📄 main_bak_svm.tex | 📄 Supplementary_Materials.tex |
| 📄 cover_letter.md | |
| 📄 response.tex | |
| 📄 ref.bib | |
| 📄 JASA_main.aux/.log/.bbl/.pdf | |
| 📁 jasa_comments/, jasa_revision/ | |
| ... (and ~930 more) | |
| **934 files, 80.6 MB** | **40 files, 3.1 MB** |

## Who is this for?

**You've never submitted to arXiv before.** Your project compiles locally. arXiv might still reject it for reasons nobody warned you about. `latex2arxiv paper.zip --compile --guide` flags the rejection-causing issues and writes you a copy-paste-ready upload walkthrough.

**You wrote it in Overleaf.** Overleaf gave you hundreds of files and messy tex files. You need to tidy up everything safely.  [Overleaf → arXiv quickstart →](docs/overleaf.md)

**You're CI-gating a paper repo.** `latex2arxiv paper.zip --dry-run` exits non-zero on rejection-causing errors. Drop it into your build matrix.

**Your paper has revision tracking.** `\added{}`, `\deleted{}`, `\textcolor{red}{}` — gone, no manual cleanup. [Custom removal rules →](#custom-removal-rules---config)

## What it does

| Feature | What it does |
|---|---|
| 📦 **One command, any input** | Accepts a `.zip`, directory, or git URL; outputs an arXiv-ready `.zip`; optionally compiles and opens the PDF for review |
| ✂️ **Prunes your project to submission-ready** | Keeps only files reachable from your main `.tex`; removes build artifacts, editor files, cover letters, unused figures |
| 🧹 **Cleans your `.tex`** | Strips comments, removes `\todo{}` / `\hl{}` / draft packages, handles nested braces correctly (`\deleted{see \cite{x}}` works) |
| 🚨 **Catches submission blockers before you upload** | `[error]` for shell-escape packages that will fail on arXiv (`minted`, `pythontex`); `[warn]` for biblatex without `.bbl`, missing index files, oversized output, undefined citations, problematic filenames — [full list](#pre-flight-checks) |
| 🗺️ **Guides you through upload** | `--guide` extracts title, authors, abstract, page/figure/table counts and writes a step-by-step arXiv upload walkthrough |

Also: `--flatten` (single-file output, [docs](docs/flatten.md)), `--json` (CI integration, [schema](docs/json-schema.md)), `--resize` (image downscaling), `--dry-run` (preview without writing), BibTeX normalization, `\pdfoutput=1` injection.

Dependency tracking respects `\input`, `\include`, `\subfile`, `\includegraphics`, `\graphicspath`, and `\bibliography`. Commented-out commands are ignored.

## Upload guide (`--guide`)

Pass `--guide` and latex2arxiv writes a plain-text file alongside your output zip with everything you need for the arXiv upload form:

```text
── arXiv Upload Guide ──

📋 Your metadata (copy-paste ready):

  Title:
    Statistical Modeling of Combinatorial Response Data

  Authors:
    Yu Zheng, Malay Ghosh, Leo Duan

  Abstract:
    There is a rich literature for modeling binary and polychotomous responses...

  Comments:
    53 pages, 13 figures, 6 tables

📌 Step 1: Start a new submission or replace an existing one
📌 Step 2: Choose license
📌 Step 3: Select category
📌 Step 4: Upload files (arXiv may warn about .sty — ignore it)
📌 Step 5: Check processing
📌 Step 6: Fill in metadata (paste from above)
📌 Step 7: Preview and submit

📁 Files in your zip:
    JASA_main.tex ← main file
    ref.bib
    Supplementary_Materials.tex
    Images/
    ...
```

No more guessing what goes where.

## Works everywhere

**Terminal** — one command, full pipeline:

```bash
latex2arxiv paper.zip --compile --guide
```

**CI** — gate your paper repo on arXiv compliance:

```yaml
- run: pip install latex2arxiv && latex2arxiv paper.zip --dry-run
```

**AI agents** — Claude, Cursor, or Copilot validate and fix issues in conversation:

```bash
pip install "latex2arxiv[mcp]"
```

```json
{"mcpServers": {"latex2arxiv": {"command": "latex2arxiv-mcp"}}}
```

## Installation

```bash
pip install latex2arxiv
```

> If you get an `externally-managed-environment` error from `pip`, use [`pipx`](https://pipx.pypa.io/):

```bash
brew install pipx
pipx install latex2arxiv
```

On macOS, install via Homebrew (no Python toolchain required):

```bash
brew tap YuZh98/latex2arxiv
brew install latex2arxiv
```

> First `brew install` builds Pillow from source. To avoid 5+ min silence, add `--verbose` to monitor installation progress.

Or from source:

```bash
git clone https://github.com/YuZh98/latex2arxiv
cd latex2arxiv
pip install .
```

`pdflatex` is required only for `--compile` (install via [TeX Live](https://tug.org/texlive/) or [MacTeX](https://tug.org/mactex/)).

## Usage

```bash
latex2arxiv input [output.zip] [options]
```

`input` can be a `.zip` file, a directory of LaTeX sources, or a git URL (https or ssh). Directories are zipped internally; git URLs are cloned with `--depth 1`.

| Flag | Description |
|---|---|
| `--main FILENAME` | Specify the main `.tex` file (e.g. `JASA_main.tex`). Auto-detected via `\documentclass` if omitted. |
| `--resize PX` | Resize images so longest side ≤ PX pixels (e.g. `--resize 1600`). Requires `Pillow`. |
| `--config FILE` | YAML config file for custom removal rules (see below). |
| `--compile` | Run `pdflatex` on the output and open the resulting PDF. |
| `--guide` | Write a detailed arXiv upload guide (metadata + step-by-step instructions) to a text file alongside the output. |
| `--dry-run` | Preview what would be removed/processed without writing any output. |
| `--flatten` | Inline every `\input` / `\include` / `\subfile` into the main `.tex` for single-file output. [Details](docs/flatten.md). |
| `--json` | Emit a machine-readable JSON summary on stdout; route progress to stderr. [Schema](docs/json-schema.md). |
| `--demo` | Run the built-in demo project (no input file needed). |
| `--version` | Print version and exit. |

**Examples**

```bash
latex2arxiv paper.zip                                  # zip input
latex2arxiv paper/                                     # directory input
latex2arxiv https://github.com/user/paper.git          # git URL input
latex2arxiv paper.zip out.zip --main main.tex --compile
latex2arxiv paper.zip --resize 1600 --compile          # shrink images
latex2arxiv paper.zip --config arxiv_config.yaml       # custom rules
latex2arxiv paper.zip --compile --guide                # full pipeline + upload guide
latex2arxiv paper.zip --dry-run                        # preview without writing
latex2arxiv --demo --compile --guide                   # run the built-in demo
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

> If your project root contains `arxiv_config.yaml`, it is applied automatically — no need to pass `--config`.

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
replacements:
  - pattern: '\\textcolor\{[^}]*\}\{([^}]*)\}'
    replacement: '\1'
```

The brace-balanced matcher correctly handles nested commands like `\deleted{see \cite{x}}`. Unknown top-level keys warn — typos like `command_to_delete` (singular) no longer silently no-op.

## `latex2arxiv` vs. `arxiv_latex_cleaner`

[`arxiv_latex_cleaner`](https://github.com/google-research/arxiv-latex-cleaner) is the incumbent — Google-backed, mature, cleans well. Here's how the two compare on the things that change your workflow.

### What only `latex2arxiv` does

| | `latex2arxiv` | `arxiv_latex_cleaner` |
|---|---|---|
| **Pre-flight `[error]` / `[warn]`** ([details](#pre-flight-checks)) | ✅ | ❌ |
| **Upload walkthrough** (`--guide`) | ✅ | ❌ |
| **Non-zero exit on errors** (CI-gateable) | ✅ | ❌ |
| **Outputs the `.zip` you upload** | ✅ | ❌ |
| **MCP server** (Claude / Cursor / Copilot) | ✅ | ❌ |
| **GitHub Action + `pre-commit` hook** | ✅ | ❌ |
| **VS Code extension** | ✅ | ❌ |
| **Multiple input forms** (`.zip` / directory / git URL) | ✅ | ❌ |
| `--compile` preview | ✅ | ❌ |
| `--dry-run` | ✅ | ❌ |
| `--demo` | ✅ | ❌ |
| Auto-detect main `.tex` | ✅ | ❌ |
| Brace-balanced config | ✅ | ❌ |

### What only `arxiv_latex_cleaner` does

| | `latex2arxiv` | `arxiv_latex_cleaner` |
|---|---|---|
| PDF compression (Ghostscript) | ❌ | ✅ |
| PNG → JPG conversion | ❌ | ✅ |

If you need image transcoding for size, run `arxiv_latex_cleaner` first, or use `latex2arxiv --resize PX`.

### Both do

BibTeX normalization · image resizing (Pillow).

### Maturity

| | `latex2arxiv` | `arxiv_latex_cleaner` |
|---|---|---|
|  | v1.0 production-stable · 380 tests · Python 3.10–3.13 matrix · live `pdflatex`+`biber` end-to-end CI · 10 regression fixtures | ~5k★, years in production |

## Integrations

| Surface | Status | Details |
|---|---|---|
| CLI | ✅ | `pip install latex2arxiv` |
| GitHub Action | ✅ | [`action.yml`](docs/ci.md) |
| `pre-commit` hook | ✅ | [`latex2arxiv-dryrun`](docs/ci.md) |
| MCP server (AI agents) | ✅ | `pip install "latex2arxiv[mcp]"` — [setup](docs/mcp.md) |
| VS Code extension | ✅ | [Marketplace](https://marketplace.visualstudio.com/items?itemName=YuZh98.latex2arxiv) — `ext install YuZh98.latex2arxiv` |
| Homebrew formula | ✅ | `brew tap YuZh98/latex2arxiv && brew install latex2arxiv` |

## Known limitations

**Dynamically constructed filenames** — `\includegraphics{\figpath/fig1}` cannot be resolved statically and the image will be deleted. Expand path macros before running.

**`\subfile` vs `\input` path resolution** — `\input`/`\include` paths resolve relative to the project root; `\subfile` paths resolve relative to the subfile's own directory. Unusual nested setups may cause images to be incorrectly pruned; use `--compile` to verify.

**`--compile` is a local sanity check** — a successful local compile doesn't guarantee arXiv will compile it. arXiv pins specific TeX Live versions. Always check the [arXiv submission preview](https://arxiv.org/submit) after uploading.

## FAQ

**1. arXiv rejected my submission even though latex2arxiv said it was clean.**
Pre-flight catches the documented submission-blocking patterns. arXiv pins specific TeX Live versions and occasionally surfaces new edge cases — always run the [arXiv submission preview](https://arxiv.org/submit) after upload. If you hit a reproducible miss, [file an issue](https://github.com/YuZh98/latex2arxiv/issues) with your project zip.

**2. What's the difference between `[error]` and `[warn]`?**
Errors block submission and exit the tool non-zero — use them to gate CI. Warnings are advisory: the build will likely succeed on arXiv but a human should look. Example: missing `.bbl` is a warn (arXiv will run BibTeX); `\usepackage{minted}` is an error (shell-escape isn't allowed).

**3. My main `.tex` isn't being auto-detected correctly.**
Auto-detection ranks files containing `\documentclass` by `\input` reference count. For ambiguous projects (response letters next to the paper, multiple `\documentclass` files), pass `--main paper.tex` explicitly.

**4. Will this modify my original files?**
No. All output goes to a new `_arxiv.zip` (or whatever path you pass). The source project is read-only.

**5. My CI step keeps failing on what I thought were just warnings.**
Warnings don't fail CI. If your build is failing, it's an `[error]` — read the message. Use `--json` for a machine-readable summary.

**6. Why does `brew install` hang for 5+ minutes?**
Homebrew compiles Pillow's C extensions from source and suppresses progress output. Add `--verbose` to see what's happening.

---

⭐ **Found this useful?** [Star on GitHub](https://github.com/YuZh98/latex2arxiv) — it helps others find the tool.

🐛 **Issues or feature requests:** [github.com/YuZh98/latex2arxiv/issues](https://github.com/YuZh98/latex2arxiv/issues)

📦 **Install:** `pip install latex2arxiv` · `brew install latex2arxiv` (after `brew tap YuZh98/latex2arxiv`)

🎬 **Try the demo:** `latex2arxiv --demo --compile --guide`

Made by [Hugh Zheng](https://github.com/YuZh98) · MIT License
