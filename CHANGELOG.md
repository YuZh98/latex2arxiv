# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- **`pdflatex` / `biber` / `bibtex` not installed now prints a clear message** — `FileNotFoundError` is caught and surfaces an actionable install hint instead of a Python traceback. For `pdflatex`, compilation aborts immediately (no repeated messages). For the bib tool, compilation continues without bibliography processing.
- **makeindex/glossary warnings now say "re-run latex2arxiv"** — previously said "include the .ind/.gls/.nls file", implying manual zip editing. The tool picks up these files automatically on re-run.

### Added
- **Better pdflatex error reporting in `--compile`** — each `! error` line is now paired with its `l.NN <prefix>` line marker and source-line suffix, giving the exact file location. Capped at 5 error blocks. Previously only the bare `!` lines were shown.
- **`\usepackage{xr}` warning links to arXiv docs** — points users to the recommended `subfiles` workaround at `info.arxiv.org/help/submit_tex.html`.

### Fixed
- **00README files no longer stripped** — `00README` and `00README.XXX` at the submission root are now preserved. arXiv reads these for processor hints, encoding declarations, and auxiliary file lists; silently deleting them was a data-loss bug for power users.
- **`\pdfoutput=0` (or any non-1 value) now corrected** — `ensure_pdfoutput` previously only injected `\pdfoutput=1` when absent; a user-supplied `\pdfoutput=0` slipped through and forced DVI mode. Now strips any existing `\pdfoutput=N` before prepending `\pdfoutput=1`.
- **`\addbibresource` with subdirectory paths** — `find_used_bib_files()` now strips directory components so `\addbibresource{bib/refs.bib}` correctly keeps `bib/refs.bib` in the output zip.
- **Config `None` values no longer crash** — a YAML key with no value (e.g. `commands_to_delete:` alone) parses as `None`; `config.get(key) or []` now treats it the same as an absent key instead of raising `TypeError`.
- **Non-dict / null / empty `replacements` rules skipped gracefully** — a string, `~`, or missing-`pattern` item in the `replacements` list now emits `[warn]` and continues instead of crashing or silently corrupting the source.
- **Malformed `replacements` regex warns and skips** — a bad regex pattern emits `[warn]` naming the rule index and continues processing subsequent rules instead of crashing.
- **Top-level non-dict config warns and is ignored** — a root-level YAML list or scalar now emits `[warn]` and returns `{}` instead of raising `AttributeError` downstream.

### Added
- **biblatex/biber support in `--compile`** — detects `\usepackage{biblatex}` or `\addbibresource` and runs `biber` instead of `bibtex`; prints error output on non-zero exit for both tools.
- **`\usepackage{psfig}` → `[error]`** — arXiv explicitly dropped psfig support; submissions using it will fail to build.
- **`\usepackage{xr}` / `xr-hyper` → `[warn]`** — file paths differ on arXiv's servers; external-document references will break. Warning names the exact package detected.
- **makeindex/glossary without pre-built files → `[warn]`** — arXiv does not run `makeindex` or glossary processors. Detects `\printindex` without `.ind`, `\printglossary`/`\printglossaries` without `.gls`, and `\printnomenclature` without `.nls` at root.
- **Main tex not at submission root → `[warn]`** — arXiv compiles from the zip root; a main file in a subdirectory will not be found.
- **Unknown config keys warn** — a typo like `command_to_delete` (singular) now prints `[warn] unknown config key` listing valid options, preventing silent no-ops.
- **Rewritten `arxiv_config.yaml` template** — decision tree explaining delete vs. unwrap vs. environments vs. replacements; inline before/after examples for each entry.

---

## [0.5.1] - 2026-05-04

### Fixed
- **`--demo` broken on PyPI installs** — `demo_project.zip` was never included in the wheel because `package-data` globs only work inside Python package directories, not at the project root. Moved `demo_project.zip` into `pipeline/` and updated the `importlib.resources` lookup accordingly.

### Changed
- README rewritten: result-first headline with real numbers (950→40 files, 82→3 MB), terminal output snippet, restructured comparison vs. `arxiv_latex_cleaner` (prose bullets + ✅/❌ table), "Known limitations" replacing "Caveats".
- PyPI keywords and classifiers added for discoverability.

---

## [0.5.0] - 2026-05-03

### Added
- **Pre-flight checks**: structured `[error]` / `[warn]` output after processing. Errors cause a non-zero exit code (CI-friendly). Checks include:
  - `[error]` `\usepackage{minted}`, `pythontex`, `shellesc` — require `--shell-escape`; arXiv compiles without it
  - `[warn]` biblatex detected without a `.bbl` fallback
  - `[warn]` output zip > 50 MB advisory threshold
  - `[warn]` filenames with spaces or non-ASCII characters
- **Conversion summary line**: every run ends with `Summary: N removed, N kept | X.X MB → Y.Y MB | N errors, N warnings`. Size segment omitted in `--dry-run`.
- **`convert()` returns `Issues`**: callers can inspect errors and warnings programmatically.

### Fixed
- **Brace-balanced matcher for `--config`**: `commands_to_delete` and `commands_to_unwrap` in user config files now correctly handle nested braces (e.g. `\deleted{see \cite{smith}}`). Previously the naive `\{[^{}]*\}` regex silently left nested content behind.

### Changed
- **Demo restructured**: sections reordered by user value (pruning → arXiv compatibility → tex cleanup → revision markup → BibTeX → CLI tools). `arxiv_config.yaml` bundled inside `demo_project.zip` and auto-applied by `--demo` so live `\deleted{}`/`\added{}` markup is demonstrated without requiring `--config`. Headline numbers (950→40 files, 82→3 MB) moved to the abstract.
- README: pre-flight checks added to the "What it does" table; exit code behavior documented for CI users; removed outdated "50 MB limit" framing for `--resize`.

---

## [0.4.2] - 2026-05-03

### Fixed
- **Main tex auto-detection**: projects with multiple `\documentclass` files (e.g. main paper + response letter + supplement) now correctly prefer `arxiv_*` files, then `*main*` files, and deprioritize response/backup/supplement files. Falls back with a `--main` hint warning when ambiguous.
- **`\subfile` bibliography warning**: warns when a `\subfile`'d document contains `\bibliographystyle` — a common cause of duplicate bibliography commands and arXiv BibTeX failures.
- **`\graphicspath` support**: images referenced without directory prefix (e.g. `\includegraphics{fig}` with `\graphicspath{{figures/}}`) are now correctly resolved and kept instead of being silently deleted.
- **Nested braces in draft annotations**: `\todo{fix \textbf{this}}` and `\todo{see \cite{smith2020}}` are now correctly removed using a brace-balanced matcher instead of a regex that stopped at the first `}`.

### Internal
- Pinned `bibtexparser` to `>=1.4,<2` to prevent accidental installation of the v2 beta, which has a breaking API change.

---

## [0.4.1] - 2026-05-02

### Fixed
- `--demo` flag now correctly locates the bundled `demo_project.zip` when installed via PyPI (`resources.files(__name__)` resolved to `__main__` at runtime; fixed by referencing the module explicitly)
- Compile: first and second `pdflatex` passes no longer abort on expected errors (missing `.sty` cache, unresolved references); only the final pass reports a failure

### Internal
- Release workflow now opens a PR instead of pushing directly to `main`, avoiding branch protection conflicts

---

## [0.4.0] - 2025-05-02

### Added
- `--demo` flag: runs the built-in demo project without needing an input file (`latex2arxiv --demo --compile`)
- `demo_project.zip` bundled inside the package via `importlib.resources`
- `--dry-run` flag: previews what would be removed/processed without writing any output
- Demo now documents all pipeline stages including `\pdfoutput=1` injection and the `--resize`, `--dry-run`, and `--demo` CLI flags
- GitHub Releases created automatically on tag push

### Changed
- `input` argument is now optional (required only when `--demo` is not used)

### Internal
- Switched to PyPI trusted publishing (OIDC); removed API token requirement
- Updated GitHub Actions to `actions/checkout@v6` and `actions/setup-python@v6`

---

## [0.3.0] - 2025-05-02

### Added
- Full test suite: 31 tests covering all pipeline stages
- Dependabot for GitHub Actions dependency updates
- Ruff linting in CI

### Fixed
- Comment stripping: comment-only lines no longer introduce spurious paragraph breaks
- BibTeX deduplication: prefer the cited entry when multiple duplicates share the same DOI/title

---

## [0.2.0] - 2025-05-01

### Added
- `--config` flag: YAML config file for custom removal rules (`commands_to_delete`, `commands_to_unwrap`, `environments_to_delete`, `replacements`)
- Built-in YAML parser (no `pyyaml` dependency required)
- GitHub Actions workflow for automatic PyPI publishing on version tags
- Self-documenting 6-section demo paper ordered by pipeline stage

### Fixed
- YAML parser: strip inline comments from list values
- Style file detection: try both `.sty` and `.cls` for `\documentclass` and `\usepackage`
- Support file whitelist: root-only, `.bbl` must match main stem
- Compile: `UnicodeDecodeError` on binary files

---

## [0.1.0] - 2025-05-01

### Added
- Initial release
- File pruning: removes unused `.tex`, images, build artifacts, and non-essential files
- Comment stripping: removes `% ...` comments while preserving verbatim blocks and `\%`
- Draft cleanup: removes `\todo{}`, `\hl{}`, `\note{}`, `\fixme{}`, `\begin{comment}`, `\iffalse...\fi` blocks, and draft-only packages
- BibTeX normalization: canonical field ordering, deduplication, private field removal (requires `bibtexparser`)
- `\pdfoutput=1` injection before `\documentclass` if missing
- Image resizing via `--resize PX` (requires `Pillow`)
- `--compile` flag: runs `pdflatex` and opens the resulting PDF
- Dependency tracking respects `\input`, `\include`, `\subfile`, `\includegraphics`, `\begin{overpic}`, `\bibliography`
- Compliance warnings: referee/double-space mode, custom style files, `\today` in `\date`, `.eps` images
