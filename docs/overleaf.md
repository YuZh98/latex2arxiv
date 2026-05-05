# Overleaf → arXiv in 30 seconds

Most LaTeX papers live in [Overleaf](https://www.overleaf.com), and Overleaf's "Submit to arXiv" link doesn't actually clean your project — it just points you at the arXiv upload form. This guide takes you from an Overleaf project to an arXiv-ready upload in three steps, using `latex2arxiv` to do the cleaning and validation.

> **Why this matters:** Overleaf compiles with `-shell-escape` enabled by default. arXiv does not. So packages like `minted` and `pythontex` work in Overleaf and silently fail on arXiv — the kind of gotcha that costs you a 30-minute round-trip waiting for arXiv's rejection email. `latex2arxiv` catches it locally before you upload.

## Prerequisites

```bash
pip install latex2arxiv
```

(Python 3.10+. On macOS with `externally-managed-environment` errors, use [`pipx`](https://pipx.pypa.io/) instead — see the [main README](../README.md#installation).)

## Quickstart (3 steps)

1. **In Overleaf**, click **Menu** (top-left) → under **Download**, click **Source**. Your browser saves a file like `my_project.zip` to your Downloads folder.
2. **Open a terminal** in the folder where the zip lives, then run:
   ```bash
   latex2arxiv my_project.zip --compile
   ```
   Replace `my_project` with whatever Overleaf named your file.
3. **Upload the output.** A new file `my_project_arxiv.zip` appears next to the input — that's your arXiv-ready zip. Upload it at [arxiv.org/submit](https://arxiv.org/submit).

> **How do I open a terminal in a folder?**
> - **macOS:** in Finder, right-click the folder → **New Terminal at Folder**. If you don't see that option, enable it once under **System Settings → Keyboard → Keyboard Shortcuts… → Services → Files and Folders → New Terminal at Folder**.
> - **Windows 11:** in File Explorer, hold Shift and right-click inside the folder → **Open in Terminal**. (On Windows 10 you'll see **Open PowerShell window here** instead — that works too.)
> - **Linux:** most file managers offer **Open in Terminal** on right-click.

That's it for the happy path. If your terminal says `command not found: latex2arxiv`, the install didn't put the tool on your PATH — see the [installation notes](../README.md#installation). If `latex2arxiv` prints `[error]` lines, or you want to understand what each step does and how to handle revision macros, biblatex, or journal templates, keep reading.

## How it works

When you run `latex2arxiv my_project.zip --compile`, it:

1. **Auto-detects** your main `.tex` file via `\documentclass` (override with `--main main.tex` if needed).
2. **Prunes** the project to only files reachable from the main `.tex` — drops cover letters, response letters, supplementary builds, editor backups, and unused figures.
3. **Cleans** the source — strips comments, `\todo{}`, draft packages, normalizes BibTeX, injects `\pdfoutput=1`.
4. **Pre-flight checks** — flags shell-escape packages, biblatex/`.bbl` mismatches, `.eps` images, and other [arXiv submission gotchas](../README.md#pre-flight-checks). Errors exit non-zero.
5. **Compiles** the cleaned project locally with `pdflatex` and opens the PDF for visual review.

Your input zip is never overwritten.

### Pre-flight errors

If `latex2arxiv` reports `[error]` lines, fix them before uploading. Common ones for Overleaf users:

| Error | What it means | Fix |
|---|---|---|
| `\usepackage{minted} requires shell-escape` | Works in Overleaf, fails on arXiv | Replace with `listings` or pre-render code blocks |
| `\usepackage{psfig}` | Legacy, no longer supported by arXiv | Switch to `graphicx`'s `\includegraphics` |
| `.eps image found` | `pdflatex` can't process `.eps` | Convert to `.pdf` (use `epstopdf`) |
| biblatex without `.bbl` shipped | arXiv often fails to resolve `.bib` files | Compile locally first; the `.bbl` will be picked up automatically on the next run |

Always check the [arXiv submission preview](https://arxiv.org/submit) PDF before submitting — `--compile` is a local sanity check, but arXiv pins specific TeX Live versions and edge cases occasionally slip through.

## Common Overleaf-specific situations

**Project uses a journal template (`elsarticle.cls`, `IEEEtran.cls`, etc.)**  
Most are already in TeX Live, so arXiv has them. `latex2arxiv` warns if you ship a custom `.cls` to make you double-check.

**Project uses `\subfile` for chapters or supplements**  
Supported. Dependency tracker handles `\subfile`. Watch for `\subfile`'d files containing `\bibliographystyle` — `latex2arxiv` warns about that case (it's a common cause of duplicate bibliography commands on arXiv).

**Project uses custom revision-tracking macros (`\added`, `\deleted`, `\textcolor{red}{...}`)**  
Use a YAML config to strip them on the way out. See [Custom removal rules](../README.md#custom-removal-rules---config) and the [`arxiv_config.yaml`](../arxiv_config.yaml) template.

**Project uses biblatex + biber**  
Supported. `latex2arxiv --compile` detects `\usepackage{biblatex}` or `\addbibresource` and runs `biber` instead of `bibtex`. arXiv compiles biblatex projects too as long as you ship a `.bbl` (or your project still resolves the `.bib`).

**Overleaf project has `__MACOSX/` and `.DS_Store` files**  
If you ever round-trip through macOS Finder, those folders end up in the zip. `latex2arxiv` ignores them.

## Going further

See the [main README](../README.md) for the full pre-flight check reference, custom removal rules, and known limitations.
