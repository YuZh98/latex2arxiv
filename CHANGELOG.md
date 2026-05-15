# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · SemVer.

## [Unreleased]

### Added
- VS Code extension package icon (`vscode-extension/icon.{svg,png}`) wired into the Marketplace listing via `package.json` `"icon"` field (#128)
- `vscode-extension/LICENSE` so `vsce package` no longer warns and the Marketplace listing shows the licence (#128)
- Design spec for the icon at `docs/superpowers/specs/2026-05-15-vscode-icon-design.md` (#128)

## [0.11.0] - 2026-05-15

API stability, CI hardening, and test coverage ahead of v1.0. MCP error envelope is now a list (`"errors"` instead of singular `"error"`), which is a breaking change for MCP clients.

### Added
- `__all__` in `converter.py` exports the stable public API: `Issues`, `ConverterError`, `convert`
- JSON schema stability contract in `docs/json-schema.md`
- Deprecation-strict CI job (`pytest -W error::DeprecationWarning`)
- Coverage gate at 85% in CI; `mcp_server.py` excluded (requires optional `[mcp]` extra)
- Pre-commit config (ruff, ruff-format, trailing-whitespace, end-of-file-fixer, check-yaml, check-toml)
- CI Python matrix expanded to 3.10–3.13; `pyyaml`, `mcp`, `fastmcp` added to test deps
- 55 behavioral audit tests covering all documented features before v1.0 (#122)
- Fixture manifest assertions: output zip contents verified, not just error/warning counts (#124)
- Overleaf-style zip tests: `__MACOSX/`, `.DS_Store`, wrapper-directory handling (#124)
- New fixture `10-multifile-graphicspath`: `\graphicspath` + `\input` from subdirectory + pruning (#124)
- End-to-end `--guide` tests with complex `\author{}` blocks (#124)

### Fixed
- `convert()` raised `FileNotFoundError` on missing input instead of `ConverterError` (#122)
- `--resize` without a value now uses the default 1600 px instead of exiting with error code 2
- MCP directory zip excluded `__pycache__`, `.pyc` files, and symlinks escaping the project root
- Config and BibTeX warnings now routed through `issues.warn` (visible in `--json` and MCP output)
- `find_used_images` return type annotation corrected to `tuple[set[Path], set[str]]`

### Changed
- MCP error envelope (breaking): responses use `{"errors": [...]}` instead of `{"error": str}`
- Publish workflow split into `publish` + `release-assets` jobs for independent re-runs
- `requirements.txt` removed; `pyproject.toml` is the single source of dependencies
- `[project.urls]` added to `pyproject.toml` (Homepage, Source, Issues, Changelog)

---

## [0.10.0] - 2026-05-13

Upload guide and metadata extraction. Pass `--guide` to get a step-by-step arXiv upload walkthrough with copy-paste-ready title, authors, and abstract.

### Added
- `--guide` flag writes a `*_UPLOAD_GUIDE.txt` alongside the output zip with metadata and step-by-step instructions (#116)
- Upload summary printed to stdout after every successful conversion (title, authors, abstract snippet, figure/table counts)
- Page count included in summary and guide when `--compile` is used
- Undefined citation warning: detects `\cite{key}` not found in any kept `.bib` or `.bbl`
- `.sty`/`.cls` advisory: tells users to ignore arXiv's suggestion to remove custom style files

### Fixed
- Author extraction handles `\thanks{...}`, `\\`-separated authors, multiple `\author{}` commands, and `\and` separators
- Figure/table counting scans all `.tex` files (not just main) and counts starred variants

---

## [0.9.0] - 2026-05-13

Homebrew tap, `--version`, `--json`, and `--flatten` flags. The tool now installs without a Python toolchain on macOS and emits machine-readable output for CI tooling.

### Added
- Homebrew tap: `brew tap YuZh98/latex2arxiv && brew install latex2arxiv` (#100)
- Automated Homebrew formula bump on PyPI publish (#102)
- `--version` flag (#106)
- `--json` flag: machine-readable JSON summary on stdout; progress routed to stderr (#107)
- `--flatten` flag: inlines `\input` / `\include` / `\subfile` into a single `.tex` file (#108)

### Changed
- `convert()` raises `ConverterError` on fatal failures instead of calling `sys.exit(1)` (#107)

### Fixed
- `--json` fatal-error envelopes now populate `input` and `sizes.input_bytes` from the input file (#111)

---

## [0.8.0] - 2026-05-07

MCP server for AI agent integration. Claude, Cursor, and Copilot can now validate and clean submissions directly via `latex2arxiv-mcp`.

### Added
- MCP server with two tools: `validate_submission` (dry-run) and `clean_submission` (full conversion)
- MCP documentation (`docs/mcp.md`) with Claude Desktop and Cursor setup instructions

### Changed
- README rewritten with "Works everywhere" hero section and decision-funnel structure
- Comparison table corrected and expanded (MCP, GitHub Action rows added)

---

## [0.7.1] - 2026-05-07

Expanded pre-flight checks and reduced false positives. Catches more submission blockers while no longer warning about things that are fine.

### Added
- New `[error]` checks: `\usepackage{svg}`, `auto-pst-pdf` / `pst-pdf`, `\tikzexternalize` without pre-built figures
- New `[warn]` checks: absolute paths, `.eps` images, filenames with spaces/non-ASCII, `\today` in `\date{}`, `\subfile` with `\bibliographystyle`, biblatex without `.bbl`, output > 50 MB, `\doublespacing`

### Fixed
- Removed false-positive `doubleblind` match from the referee/doublespace check
- Removed noisy `.cls`/`.sty` warning that fired on projects correctly shipping journal style files
- `fontspec`/`unicode-math` error now mentions the `00README.XXX` XeLaTeX workaround
- biblatex warning accurately states arXiv runs Biber but version mismatches can break things

### Changed
- Pre-flight docs (`docs/pre-flight.md`) updated to match all check changes

---

## [0.7.0] - 2026-05-06

Directory and git URL input, GitHub Action, and pre-commit hook. The tool now accepts any input format and integrates into CI pipelines.

### Added
- Directory and git URL input: `latex2arxiv paper/` and `latex2arxiv https://github.com/user/paper.git`
- GitHub Action (`action.yml`): composite action for CI pre-flight with `cleaned-zip` output
- `pre-commit` hook: `latex2arxiv-dryrun` for repos with a checked-in submission zip
- Overleaf → arXiv quickstart (`docs/overleaf.md`)
- `\usepackage{fontspec}` / `unicode-math` raises `[error]`
- 2 new regression fixtures: `06-inline-verbatim`, `07-fontspec-xelatex`

### Fixed
- `\verb|...|`, `\verb*|...|`, `\lstinline`, and `\mintinline` protected during comment stripping and draft removal
- Directory zipping excludes `__pycache__`, `.DS_Store`, `Thumbs.db`, `*.pyc`; out-of-project symlinks excluded
- SSH-style git URL name derivation (`git@host:user/repo.git` → `repo_arxiv.zip`)
- `git clone` has a 5-minute timeout to prevent indefinite hangs

---

## [0.6.0] - 2026-05-04

CI regression fixtures, zip-slip protection, and biblatex/biber support in `--compile`. The test suite now catches pre-flight regressions without TeX Live and validates end-to-end compilation with it.

### Added
- `fixtures-smoke` CI job: regression tests without TeX Live
- `compile-smoke` CI job: live end-to-end test with TeX Live and biber
- `tests/fixtures/`: 5 fixture projects with `run_all.sh` runner
- `--compile` runs `biber` when biblatex is detected
- pdflatex error reporting: `!` errors paired with `l.NN` line markers, capped at 5 blocks
- `\usepackage{psfig}` raises `[error]`; `\usepackage{xr}` / `xr-hyper` raises `[warn]`
- `\printindex` / `\printglossary` / `\printnomenclature` without pre-built index files raises `[warn]`
- Unknown config keys now warn instead of silently no-oping

### Security
- Zip-slip protection: member paths validated before extraction; `..` and absolute-path members abort

### Fixed
- `\newcommand` / `\def` / `\let` definition lines skipped by config removal rules
- macOS Finder zips: `__MACOSX/` entries and `.DS_Store` files ignored
- Non-UTF-8 source files emit `[warn]` instead of crashing
- Empty or no-`.tex` zip exits cleanly with a non-zero code
- Missing `pdflatex` / `biber` / `bibtex` prints a clear message; bib tools degrade gracefully
- `00README` and `00README.XXX` files at root preserved for arXiv processor hints
- `\pdfoutput=N` normalized to `\pdfoutput=1`
- `\addbibresource{bib/refs.bib}` resolves correctly by stripping directory components
- Malformed config rules warn and skip instead of crashing

---

## [0.5.1] - 2026-05-04

Packaging fix. `demo_project.zip` was missing from the wheel.

### Fixed
- `--demo` broken on PyPI installs: `demo_project.zip` moved into `pipeline/` and `importlib.resources` lookup updated

### Changed
- README rewritten with result-first headline and restructured comparison table
- PyPI keywords and classifiers added for discoverability

---

## [0.5.0] - 2026-05-03

Pre-flight checks and CI gating. Errors cause a non-zero exit code so a bad submission can't slip through a CI pipeline.

### Added
- Pre-flight checks: `\usepackage{minted}` / `pythontex` / `shellesc` → `[error]`; biblatex without `.bbl`, zip > 50 MB, filenames with spaces/non-ASCII → `[warn]`
- Conversion summary line: `Summary: N removed, N kept | X.X MB → Y.Y MB | N errors, N warnings`
- `convert()` returns an `Issues` object for programmatic inspection

### Fixed
- Brace-balanced matcher for `--config`: nested braces (e.g. `\deleted{see \cite{smith}}`) handled correctly

### Changed
- Demo restructured by user value; `arxiv_config.yaml` bundled and auto-applied by `--demo`

---

## [0.4.2] - 2026-05-03

Main tex detection and `\graphicspath` support. Projects with multiple `\documentclass` files are now ranked correctly.

### Fixed
- Main tex auto-detection prefers `arxiv_*`, then `*main*`, deprioritizes response/backup/supplement files
- `\subfile` bibliography warning when a subfile contains `\bibliographystyle`
- `\graphicspath` support: images referenced without a directory prefix now resolved correctly
- Nested braces in draft annotations (`\todo{fix \textbf{this}}`) removed correctly

### Internal
- Pinned `bibtexparser` to `>=1.4,<2` to avoid the breaking v2 API

---

## [0.4.1] - 2026-05-02

Bug fixes for `--demo` and `--compile` on PyPI installs.

### Fixed
- `--demo` correctly locates `demo_project.zip` when installed via PyPI
- Compile: first and second `pdflatex` passes no longer abort on expected errors

### Internal
- Release workflow opens a PR instead of pushing directly to `main`

---

## [0.4.0] - 2025-05-02

`--demo` and `--dry-run` flags. Try the tool without an input file or preview changes without writing output.

### Added
- `--demo` flag: runs the built-in demo project without needing an input file
- `demo_project.zip` bundled inside the package via `importlib.resources`
- `--dry-run` flag: previews what would be removed/processed without writing output
- GitHub Releases created automatically on tag push

### Changed
- `input` argument is now optional (required only when `--demo` is not used)

### Internal
- Switched to PyPI trusted publishing (OIDC); removed API token requirement

---

## [0.3.0] - 2025-05-02

Test suite and CI linting. All pipeline stages now have automated coverage.

### Added
- Full test suite: 31 tests covering all pipeline stages
- Dependabot for GitHub Actions dependency updates
- Ruff linting in CI

### Fixed
- Comment stripping: comment-only lines no longer introduce spurious paragraph breaks
- BibTeX deduplication: prefer the cited entry when multiple duplicates share the same DOI/title

---

## [0.2.0] - 2025-05-01

Custom removal rules via `--config`. Users can now strip revision markup (`\added`, `\deleted`, `\textcolor{red}{...}`) with a YAML file.

### Added
- `--config` flag: YAML config for custom removal rules (`commands_to_delete`, `commands_to_unwrap`, `environments_to_delete`, `replacements`)
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

Initial release. One command converts a LaTeX zip to an arXiv-ready submission.

### Added
- File pruning: removes unused `.tex`, images, build artifacts, and non-essential files
- Comment stripping: removes `% ...` comments while preserving verbatim blocks and `\%`
- Draft cleanup: removes `\todo{}`, `\hl{}`, `\note{}`, `\fixme{}`, `\begin{comment}`, `\iffalse...\fi` blocks, and draft-only packages
- BibTeX normalization: canonical field ordering, deduplication, private field removal
- `\pdfoutput=1` injection before `\documentclass` if missing
- Image resizing via `--resize PX` (requires `Pillow`)
- `--compile` flag: runs `pdflatex` and opens the resulting PDF
- Dependency tracking respects `\input`, `\include`, `\subfile`, `\includegraphics`, `\begin{overpic}`, `\bibliography`
- Compliance warnings: referee/double-space mode, custom style files, `\today` in `\date`, `.eps` images

---

[Unreleased]: https://github.com/YuZh98/latex2arxiv/compare/v0.11.0...HEAD
[0.11.0]: https://github.com/YuZh98/latex2arxiv/compare/v0.10.0...v0.11.0
