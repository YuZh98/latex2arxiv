# Test fixture projects

Small, self-contained LaTeX projects covering distinct user scenarios. Each
subdirectory is a project tree you can zip and feed to `latex2arxiv` for
manual exploration, regression checks, or showcasing behavior.

These are **not** run by `pytest` directly — `tests/test_pipeline.py` covers
the same scenarios with synthetic in-memory fixtures. The directories here
are for hands-on inspection, demo material, and ad-hoc shakeouts when you
change something in `_compile()`, `_check_compliance()`, or the file-pruning
logic.

## What's covered

| # | Fixture | Tests |
|---|---|---|
| 01 | `01-minimal/` | Smallest viable project — main.tex only. Pipeline smoke. |
| 02 | `02-biblatex-biber/` | biblatex + biber dispatch in `--compile`, with `.bib` in a `bib/` subdirectory. Exercises `find_used_bib_files()` basename normalization. |
| 03 | `03-revision-markup/` | `\added`/`\deleted`/`\textcolor{red}` markup with bundled `arxiv_config.yaml`. Tests config-driven cleanup and brace-balanced matcher (nested `\emph`, `\textbf`). |
| 04 | `04-multi-documentclass/` | Four files with `\documentclass` (`main.tex`, `main_backup.tex`, `response.tex`, `Supplementary_Materials.tex`). Tests the main-tex auto-detect heuristic ranking. |
| 05 | `05-pre-flight-warnings/` | Deliberately triggers most pre-flight checks at once: `minted` + `psfig` (errors), `xr` + `referee` + `\today`-in-`\date` + `.eps` + `\printindex` without `.ind` + `\printglossary` without `.gls` (warns). |
| 06 | `06-inline-verbatim/` | `\verb`, `\verb*`, `\lstinline`, `\mintinline` with `%` and `\todo{}` inside. Tests inline-code protection during comment stripping and draft removal. |
| 07 | `07-fontspec-xelatex/` | `\usepackage{fontspec}` + `\usepackage{unicode-math}`. Tests the XeLaTeX/LuaLaTeX pre-flight `[error]` check. |

## How to run

Quick one-shot against any fixture:

```bash
(cd tests/fixtures/02-biblatex-biber && zip -qr /tmp/fixture.zip . -x ".DS_Store") \
  && latex2arxiv /tmp/fixture.zip /tmp/out.zip --dry-run
```

Or use the bundled runner to exercise all of them:

```bash
tests/fixtures/run_all.sh           # dry-run on each
tests/fixtures/run_all.sh --compile # full pipeline including pdflatex
```

`--compile` requires TeX Live + biber on `PATH`.

## Expected outcomes

The reference output for each fixture in `--dry-run` mode (the runner's
default). If `run_all.sh` produces something different from what's listed
here, treat it as a regression and investigate.

### 01-minimal

- **Kept:** `main.tex` (1 file).
- **Removed:** none.
- **Errors / warnings:** 0 / 0.
- **Cleaned-source notes:** `\pdfoutput=1` prepended; `% ...` line comments
  stripped.

### 02-biblatex-biber

- **Kept:** `main.tex`, `bib/refs.bib` (2 files).
- **Removed:** none.
- **Errors / warnings:** 0 / 1.
  - `biblatex detected but no main.bbl shipped` — defensive recommendation;
    the .bbl would be the fallback if arXiv can't resolve any `.bib`. Legitimate.
- **Regression anchor:** if `bib/refs.bib` shows up under `remove:`, the
  subdirectory-`.bib` handling in `find_used_bib_files()` has regressed.
  This was the entire point of the fix shipped in PR #45.
- **`--compile` mode:** `Running biber ...` line should appear and a PDF
  should be produced.

### 03-revision-markup (config auto-applied by the runner)

- **Kept:** `main.tex` (1 file).
- **Removed:** `arxiv_config.yaml` (the config itself is not a deliverable;
  pruned because no `.tex` source references it).
- **Errors / warnings:** 0 / 0.
- **Cleaned-source notes:**
  - `\usepackage{changes}` is dropped by `remove_draft_packages` on the way
    out — the cleaned source compiles standalone without `changes` installed.
  - `\added{plus a sentence reviewers asked us to add}` → `plus a sentence reviewers asked us to add`
  - `\deleted{a sentence reviewers asked us to remove ...}` → `` (empty)
  - `\textcolor{red}{Red-highlighted phrasing}` → `Red-highlighted phrasing`
- **Brace-balanced regression anchor:**
  `\added{nested commands like \emph{this italic} and \textbf{this bold}}`
  should unwrap to `nested commands like \emph{this italic} and \textbf{this bold}`.
  If the inner `\emph` or `\textbf` is dropped or truncated, the brace-balanced
  matcher in `pipeline/tex.py:unwrap_cmd` has regressed.

### 04-multi-documentclass

- **Kept:** `main.tex` (1 file).
- **Removed:** `main_backup.tex`, `response.tex`, `Supplementary_Materials.tex` (3 files).
- **Errors / warnings:** 0 / 0.
  - The `multiple \documentclass files found; using 'main.tex'` line printed
    by `find_main_tex` is informational, *not* an `issues.warn`. It does not
    appear in the warning count.
- **Heuristic regression anchor:** the runner's `main tex:` line must read
  `main tex: main.tex`. If the heuristic picks `Supplementary_Materials.tex`,
  `response.tex`, or `main_backup.tex`, the ranking in `find_main_tex` has
  regressed.

### 05-pre-flight-warnings

This fixture deliberately triggers as many pre-flight checks as possible.
The runner reports it as having "non-zero exit (expected)" — that's correct
behavior because the pre-flight errors trigger `sys.exit(1)`.

- **Kept (eventually):** `main.tex`, `photo.eps`. The `.eps` stays because
  the converter doesn't auto-convert; the user is expected to convert before
  re-running.
- **Removed:** `custom.sty` (not referenced by any `\usepackage`).
- **Errors:** 2.
  - `\usepackage{minted} requires shell-escape — arXiv compiles without it`
  - `\usepackage{psfig} — arXiv no longer supports the psfig package`
- **Warnings:** 6 (same in `--dry-run` and real-run mode).
  - `'referee' or 'doublespace' option detected in \documentclass`
  - `\today used in \date`
  - `.eps image found: photo.eps`
  - `\usepackage{xr} detected — file paths/locations differ on arXiv ...`
    (also includes the docs link to `info.arxiv.org/help/submit_tex.html`)
  - `\printindex used but no .ind file at root`
  - `\printglossary used but no .gls file at root`
- **Regression anchor:** if any of the 8 listed `[error]`/`[warn]` lines
  goes missing from the runner output, the corresponding check has
  regressed (or the warn message wording has changed).

## Why these specific fixtures

Each scenario reflects something we've seen break in real use or that we
shipped recently:

- **#02** locks in the biber/biblatex support added in PR #45 (subdirectory `.bib` was the latent bug).
- **#03** mirrors the bundled `pipeline/demo_project.zip` at smaller scale, kept here so the demo can evolve without losing the "config UX" canonical example. Uses the `changes` package rather than inline `\newcommand` to avoid the [definition-mangling caveat](../../arxiv_config.yaml).
- **#04** guards against a regression in the main-tex ranking from PR #42 — without it, `Supplementary_Materials.tex` could win.
- **#05** is the "can I see what the tool actually surfaces?" demo. Useful for screenshots, README copy, and validating new pre-flight checks don't silently overlap.

## Adding a new fixture

Pick the smallest possible source files that exercise the scenario. Avoid
real images unless the test depends on image content — placeholder bytes
or synthetic stubs are fine. Add a row to the "What's covered" table above,
a section under "Expected outcomes" naming the regression anchor, and a
brief note in the "Why" section.

### 06-inline-verbatim

- **Kept:** `main.tex` (1 file).
- **Removed:** none.
- **Errors / warnings:** 0 / 0.
- **Cleaned-source notes:**
  - `\verb|%|` preserved (not treated as comment).
  - `\verb+\todo{x}+` preserved (todo not removed from verb content).
  - `\lstinline|%foo|` and `\lstinline{\todo{bar}}` preserved.
  - `\verb|\todo{this}|` preserved.
  - Real `% comments` stripped normally.
  - Standalone `\todo{...}` removed normally.
  - `verbatim` block content preserved.
- **Regression anchor:** if any `\verb`, `\lstinline`, or `\mintinline`
  content is mangled (% stripped, \todo removed), the inline-code protection
  in `pipeline/tex.py:_protect_verbatim` has regressed.

### 07-fontspec-xelatex

- **Kept:** `main.tex` (1 file).
- **Removed:** none.
- **Errors:** 2.
  - `\usepackage{fontspec} requires XeLaTeX or LuaLaTeX — arXiv defaults to pdfLaTeX and this submission will fail to build`
  - `\usepackage{unicode-math} requires XeLaTeX or LuaLaTeX — arXiv defaults to pdfLaTeX and this submission will fail to build`
- **Warnings:** 0.
- **Regression anchor:** if either `[error]` line goes missing, the
  fontspec/unicode-math check in `converter.py:_check_compliance` has
  regressed.
