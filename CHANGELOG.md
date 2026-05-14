# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Breaking changes
- **MCP error envelope**: all responses from `validate_submission` / `clean_submission` now use `{"errors": [str], "warnings": [], "log": ""}` (list) instead of the former `{"error": str}` (singular key). Clients checking `result["error"]` must switch to `result["errors"][0]` or `result.get("errors", [])`.

### Added
- **`__all__` in `converter.py`**: documents the stable public API — `Issues`, `ConverterError`, `convert`; internal helpers are no longer implicitly exported
- **`--json` schema stability contract** (`docs/json-schema.md`): `errors[]` / `warnings[]` string content is explicitly **not stable** across releases; `compile` field documented as always `null` in v1.0 (including with `--compile`)
- **`MCPEnvelope` TypedDict** in `mcp_server.py`: all MCP tool return types are now fully typed, preventing `"error"` vs `"errors"` drift at the type-checker level
- Python matrix expanded to 3.10–3.13 in CI; `pyyaml`, `mcp`, `fastmcp` added to test dependencies so YAML and MCP tests never silently skip
- Deprecation-strict CI job (`pytest -W error::DeprecationWarning`)
- Coverage gate at 74% (measured against product code; `make_demo.py` excluded)
- Pre-commit config: ruff, ruff-format, trailing-whitespace, end-of-file-fixer, check-yaml, check-toml

### Improved
- **MCP server hardening**: temp files are cleaned up on all error paths; bare `except Exception` guarantees every unhandled exception returns a structured `MCPEnvelope` instead of crashing the tool call; symlink-escape files excluded from directory zip are now surfaced in `warnings` instead of silently dropped; empty-string `path` rejected explicitly; `Path.cwd()` consistently resolved before path containment checks
- **Warning routing**: `load_config`, `apply_config`, and `normalize_bibtex` accept a `warn_fn` callback; callers in `convert()` pass `issues.warn`, making config and BibTeX warnings visible in `--json` output and the MCP `warnings` field

### Fixed
- `--resize` without a value now uses the default 1600 px (`nargs='?', const=DEFAULT_MAX_PX`) instead of exiting with error code 2
- MCP directory zip excluded `__pycache__`, `.pyc` files, and symlinks escaping the project root
- `find_used_images` return type annotation corrected from `set` to `tuple[set[Path], set[str]]`

### Changed
- Publish workflow split into `publish` (PyPI only) and `release-assets` (TeX Live → demo PDF → GitHub Release) jobs; each can be re-run independently on failure
- CI matrix uses `fail-fast: false` so a failure on one Python version does not cancel the others
- `requirements.txt` removed; `pyproject.toml` is authoritative
- `[project.urls]` added to `pyproject.toml` (Homepage, Source, Issues, Changelog)

---

## [0.10.0] - 2026-05-13

### Added
- **`--guide` flag**: writes a detailed `*_UPLOAD_GUIDE.txt` alongside the output zip with copy-paste-ready metadata (title, authors, abstract, page/figure/table counts) and a step-by-step arXiv upload walkthrough (#116)
- **Always-on upload summary**: after every successful conversion, prints extracted title, authors, abstract snippet, and figure/table counts to stdout
- **Page count**: when `--compile` is used, the compiled PDF's page count is included in the summary and guide
- **Undefined citation warning**: detects `\cite{key}` references not found in any kept `.bib` or `.bbl` file after cleaning
- **`.sty`/`.cls` advisory**: warns that arXiv may suggest removing custom style files — tells users to ignore that and keep them

### Improved
- **Author extraction**: handles `\thanks{...}` stripping, `\\`-separated authors with affiliations, multiple `\author{}` commands, and `\and` separators
- **Figure/table counting**: scans all `.tex` files in the output (not just main), counts `figure*`/`table*` starred variants

---

## [0.9.0] - 2026-05-13

### Added
- **Homebrew tap**: `brew tap YuZh98/latex2arxiv && brew install latex2arxiv` — no Python toolchain required (#100)
- Automated Homebrew formula bump: publish workflow fetches new sdist metadata from PyPI and pushes a bump commit to the tap repo (#102)
- `--version` flag: prints `latex2arxiv <version>` and exits 0 (#106)
- `--json` flag: machine-readable JSON summary on stdout; progress routed to stderr. Fatal errors still produce a JSON envelope. Schema: `docs/json-schema.md` (#107)
- `--flatten` flag: inlines every `\input` / `\include` / `\subfile` into the main `.tex` for single-file output. `\include` preserves `\clearpage` semantics; `\subfile` preamble is stripped; cycles and missing files are flagged. Details: `docs/flatten.md` (#108)

### Changed
- `convert()` raises `ConverterError` on fatal failures instead of calling `sys.exit(1)`, enabling the `--json` envelope and cleaner MCP server error handling (#107)

### Fixed
- `--json` fatal-error envelopes (e.g. zip-slip rejection) now populate `input` and `sizes.input_bytes` from the as-passed input file when it exists on disk, instead of all-null fields (#111)

---

## [0.8.0] - 2026-05-07

### Added
- **MCP server**: AI agents (Claude, Cursor, Zed, Copilot) can now validate and clean
  submissions directly via `latex2arxiv-mcp`. Install with `pip install "latex2arxiv[mcp]"`.
  Two tools: `validate_submission` (dry-run pre-flight) and `clean_submission` (full conversion).
  See [docs/mcp.md](docs/mcp.md) for setup.
- MCP documentation (`docs/mcp.md`) with Claude Desktop and Cursor setup instructions (Zed support deferred)

### Changed
- README rewritten: "Works everywhere" hero section (CLI/CI/AI), decision-funnel structure,
  Integrations table with roadmap
- Comparison table: corrected BibTeX normalization (both tools have it), added MCP and
  GitHub Action rows

---

## [0.7.1] - 2026-05-07

### Added
- New pre-flight `[error]` checks: `\usepackage{svg}` (requires Inkscape), `auto-pst-pdf` / `pst-pdf` (require shell-escape), `\tikzexternalize` without pre-built figures
- New pre-flight `[warn]` checks: absolute paths in `\input`/`\includegraphics`, `.eps` images, filenames/directories with spaces or non-ASCII, `\today` in `\date{}`, `\subfile` with `\bibliographystyle`, biblatex without `.bbl`, output/uncompressed size > 50 MB, `\doublespacing` command, `\documentclass[doublespace]`

### Fixed
- Removed false-positive `doubleblind` match from the referee/doublespace check (`doubleblind` is an anonymization flag, not a spacing flag)
- Removed noisy custom `.cls`/`.sty` warning that fired on every project correctly shipping journal style files
- `fontspec`/`unicode-math` error now mentions the `00README.XXX` XeLaTeX workaround
- biblatex warning accurately states arXiv runs Biber but version mismatches can break things

### Changed
- README comparison table no longer hardcodes a test count (the CI badge shows pass/fail)
- Pre-flight docs (`docs/pre-flight.md`) updated to match all check changes

---

## [0.7.0] - 2026-05-06

### Added
- Directory and git URL input: `latex2arxiv paper/` and `latex2arxiv https://github.com/user/paper.git` now work alongside `.zip` input
- GitHub Action (`action.yml`): composite action for CI pre-flight; accepts `.zip` or directory input; emits `cleaned-zip` output for release workflows
- `pre-commit` hook: `latex2arxiv-dryrun` for repos with a checked-in submission zip
- Overleaf → arXiv quickstart (`docs/overleaf.md`): 3-step guide for non-CLI users
- `action-smoke` CI job: tests `action.yml` against clean and error fixtures
- `\usepackage{fontspec}` / `unicode-math` raises `[error]`: requires XeLaTeX/LuaLaTeX but arXiv defaults to pdfLaTeX
- 2 new regression fixtures: `06-inline-verbatim`, `07-fontspec-xelatex`

### Fixed
- `\verb|...|`, `\verb*|...|`, `\lstinline`, and `\mintinline` (both delimiter and brace forms) are now protected during comment stripping and draft annotation removal
- Directory zipping excludes `__pycache__`, `.DS_Store`, `Thumbs.db`, `*.pyc`; symlinks pointing outside the project are excluded while in-project symlinks are kept
- SSH-style git URL name derivation (`git@host:user/repo.git` → `repo_arxiv.zip`)
- `git clone` has a 5-minute timeout to prevent indefinite hangs

---

## [0.6.0] - 2026-05-04

### Added
- `fixtures-smoke` CI job: fixture regression tests without TeX Live
- `compile-smoke` CI job: live end-to-end test with TeX Live and biber
- `tests/fixtures/`: 5 fixture projects with `run_all.sh` runner
- `--compile` now runs `biber` when `\usepackage{biblatex}` or `\addbibresource` is detected
- pdflatex error reporting: `!` errors paired with `l.NN` line markers, capped at 5 blocks
- `\usepackage{psfig}` raises `[error]`: no longer supported by arXiv
- `\usepackage{xr}` / `xr-hyper` raises `[warn]`: external-document references break on arXiv
- `\printindex`, `\printglossary`, `\printnomenclature` without pre-built index files raises `[warn]`
- Main `.tex` not at submission root raises `[warn]`
- Unknown config keys now warn instead of silently no-oping
- `arxiv_config.yaml` template rewritten with decision tree, before/after examples, and `\textcolor{*}` recipe

### Security
- Zip-slip protection: member paths validated before extraction; `..` and absolute-path members abort with a non-zero exit

### Fixed
- `\newcommand`, `\def`, `\let` definition lines are skipped by config removal rules to avoid corrupting macro definitions
- macOS Finder zips: `__MACOSX/` entries and `.DS_Store` files are ignored
- Non-UTF-8 source files emit `[warn]` instead of crashing
- Empty or no-`.tex` zip exits cleanly with a non-zero code instead of a traceback
- Missing `pdflatex`, `biber`, or `bibtex` prints a clear message; bib tools degrade gracefully
- makeindex/glossary warnings now say "re-run latex2arxiv" since `.ind`/`.gls`/`.nls` are picked up automatically
- `\usepackage{xr}` warning links to the `subfiles` workaround in arXiv docs
- `00README` and `00README.XXX` files at root are preserved for arXiv processor hints
- `\pdfoutput=N` with any value is normalized to `\pdfoutput=1`
- `\addbibresource{bib/refs.bib}` now resolves correctly by stripping directory components
- Malformed config rules (null keys, bad regex, non-dict entries) warn and skip instead of crashing

---

## [0.5.1] - 2026-05-04

### Fixed
- `--demo` broken on PyPI installs: `demo_project.zip` was missing from the wheel; moved into `pipeline/` and updated `importlib.resources` lookup

### Changed
- README rewritten with result-first headline, terminal output snippet, restructured comparison vs. `arxiv_latex_cleaner`, and "Known limitations" section
- PyPI keywords and classifiers added for discoverability

---

## [0.5.0] - 2026-05-03

### Added
- Pre-flight checks: structured `[error]` / `[warn]` output after processing; errors cause a non-zero exit code for CI gating. Checks: `\usepackage{minted}` / `pythontex` / `shellesc` → `[error]`; biblatex without `.bbl`, zip > 50 MB, filenames with spaces or non-ASCII → `[warn]`
- Conversion summary line: every run ends with `Summary: N removed, N kept | X.X MB → Y.Y MB | N errors, N warnings` (size omitted in `--dry-run`)
- `convert()` returns an `Issues` object so callers can inspect errors and warnings programmatically

### Fixed
- Brace-balanced matcher for `--config`: `commands_to_delete` and `commands_to_unwrap` now correctly handle nested braces (e.g. `\deleted{see \cite{smith}}`)

### Changed
- Demo restructured: sections reordered by user value; `arxiv_config.yaml` bundled inside `demo_project.zip` and auto-applied by `--demo`
- README: pre-flight checks added to the "What it does" table; exit code behavior documented for CI users

---

## [0.4.2] - 2026-05-03

### Fixed
- Main tex auto-detection: projects with multiple `\documentclass` files now prefer `arxiv_*`, then `*main*`, and deprioritize response/backup/supplement files; falls back with a `--main` hint warning when ambiguous
- `\subfile` bibliography warning: warns when a `\subfile`'d document contains `\bibliographystyle`
- `\graphicspath` support: images referenced without a directory prefix are now correctly resolved and kept
- Nested braces in draft annotations: `\todo{fix \textbf{this}}` and similar are correctly removed using a brace-balanced matcher

### Internal
- Pinned `bibtexparser` to `>=1.4,<2` to avoid the breaking API change in v2

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

---

[Unreleased]: https://github.com/YuZh98/latex2arxiv/compare/v0.10.0...HEAD
