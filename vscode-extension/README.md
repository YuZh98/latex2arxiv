# latex2arxiv

[![CI](https://github.com/YuZh98/latex2arxiv/actions/workflows/test.yml/badge.svg)](https://github.com/YuZh98/latex2arxiv/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/YuZh98/latex2arxiv/blob/main/LICENSE)

**arXiv pre-flight validation for LaTeX projects, surfaced as VS Code diagnostics.**

Stop discovering submission errors only after arXiv rejects your zip. This extension catches arXiv-specific issues — `\usepackage{minted}`, `\today` inside `\date{}`, `.eps` images, file-size limits, biblatex/biber flow, encoding traps — while you're still writing, and produces a clean, ready-to-upload zip with one command.

<!-- TODO: hero GIF — typing `\usepackage{minted}`, diagnostic surfaces in Problems panel, status bar updates -->

## Features

- 🔍 **Inline diagnostics** for arXiv-specific issues, mapped to the exact `.tex` file and line
- 📦 **One-click clean** — `Clean for arXiv` produces a submission-ready zip
- 🪧 **Status-bar summary** — errors and warnings at a glance
- 💾 **Validate on save** (opt-in) — fast feedback loop
- 🎯 **Auto-detects the main `.tex`** — override per project via setting

## Quick start

1. Install the CLI:
   ```sh
   pip install latex2arxiv
   # or, on macOS:
   brew tap YuZh98/latex2arxiv && brew install latex2arxiv
   ```
2. Open a LaTeX project in VS Code.
3. `Cmd+Shift+P` → **latex2arxiv: Validate**.
4. Inspect the **Problems** panel and the status-bar item.

<!-- TODO: screenshot — Problems panel after running Validate on a project with 2 errors + 3 warnings -->

## What gets validated

Every check the underlying [`latex2arxiv` CLI](https://github.com/YuZh98/latex2arxiv) performs, including:

- **arXiv submission rules** — file-size limits, `.eps` vs `.pdf`, hidden files, `__MACOSX/` cruft, BOM markers, suspicious filename characters
- **Engine quirks** — `\usepackage{minted}` (not available on arXiv), biblatex + biber flow, `\subfile` resolution, `\graphicspath`
- **Date traps** — `\today` inside `\date{}` (renders to upload date, not submission date)
- **Bibliography** — missing `.bib`, mismatched `\bibliographystyle`, biber-only commands
- **Project hygiene** — unused `\input`s, missing referenced files, encoding mismatches

Full check list and JSON output schema: [docs/json-schema.md](https://github.com/YuZh98/latex2arxiv/blob/main/docs/json-schema.md).

## Commands

| Command | Action |
|---|---|
| `latex2arxiv: Validate` | Runs `latex2arxiv --dry-run` on the workspace. Errors and warnings populate the Problems panel. |
| `latex2arxiv: Clean for arXiv` | Full conversion. On success, reveals the output zip in Explorer. |

## Settings

| Setting | Type | Default | Description |
|---|---|---|---|
| `latex2arxiv.executablePath` | string | `"latex2arxiv"` | Path to the CLI. Use an absolute path if not on `PATH`. |
| `latex2arxiv.validateOnSave` | boolean | `false` | Re-validate whenever a `.tex` file is saved. |
| `latex2arxiv.mainFile` | string | `""` | Filename of the main `.tex` (e.g. `main.tex`). Auto-detected if empty. |

## Status bar

The status-bar item summarises the most recent validation:

| State | Meaning |
|---|---|
| `$(check) arXiv` | No issues. Submission-ready. |
| `$(warning) arXiv: 3W` | Warnings only. Submission allowed; review first. |
| `$(error) arXiv: 2E 3W` | Errors block submission. |
| `$(warning) arXiv: not installed` | CLI not found on `PATH`. |

Click the item to re-run validation.

## How locations are inferred

Diagnostics map to `file:line` by regex-searching `.tex` sources for the pattern that triggered each check (e.g. `\usepackage{minted}`, `\today` inside `\date{}`, `.eps` filename in `\includegraphics`). Checks without a precise location (project-level size warnings, encoding warnings on directories, etc.) are routed to **Output → latex2arxiv** instead.

## Requirements

- VS Code ≥ 1.85.0
- `latex2arxiv` CLI (Python ≥ 3.10) on `PATH`. See the [main repo](https://github.com/YuZh98/latex2arxiv#install) for all install options.

## Troubleshooting

**"arXiv: not installed" in status bar.** The CLI isn't on `PATH`. Two fixes:

- Install it: `pip install latex2arxiv` (or `brew install latex2arxiv` on macOS).
- Or point the extension at the binary: settings → `latex2arxiv.executablePath` → absolute path (e.g. `/usr/local/bin/latex2arxiv`, `~/.venv/bin/latex2arxiv`).

**Validate-on-save isn't firing.** Enable `latex2arxiv.validateOnSave` in settings (off by default to avoid surprising users).

**Diagnostic shows in Output panel, not Problems.** Expected: the check has no precise file:line (e.g. project-level size warnings, encoding warnings on directories). The full message is in **Output → latex2arxiv**.

**Wrong file is treated as `main`.** Set `latex2arxiv.mainFile` explicitly (e.g. `"main.tex"`). Auto-detection picks the file with the most `\input` references — fine for single-paper projects, ambiguous for multi-paper repos.

**Bibliography errors I don't see in the regular LaTeX build.** The arXiv flow uses `bibtex` (legacy) by default. If your project uses `biblatex` + `biber`, the CLI validates that flow too — re-run **Validate** after editing your `.bib`.

## Contributing

This extension is a thin wrapper around the [latex2arxiv CLI](https://github.com/YuZh98/latex2arxiv). Bug reports, feature requests, and PRs welcome at the [main repo issues](https://github.com/YuZh98/latex2arxiv/issues).

Local dev:

```sh
git clone https://github.com/YuZh98/latex2arxiv.git
cd latex2arxiv/vscode-extension
npm install
npm run compile
# Press F5 in VS Code to launch the Extension Development Host
```

## Links

- [Source code & CLI](https://github.com/YuZh98/latex2arxiv)
- [Issue tracker](https://github.com/YuZh98/latex2arxiv/issues)
- [Changelog](https://github.com/YuZh98/latex2arxiv/blob/main/CHANGELOG.md)
- [License: MIT](https://github.com/YuZh98/latex2arxiv/blob/main/LICENSE)
