# CI / pre-commit integration

> **Note:** The GitHub Action and pre-commit hook are available from v0.7.0. For earlier versions, use `latex2arxiv` directly in your CI scripts.

For paper repos under version control, you can wire the pre-flight check into a hook so a bad submission can't be merged.

## GitHub Action

The recommended path for paper repos. Drop this into a workflow file (e.g. `.github/workflows/arxiv-check.yml`):

```yaml
name: arXiv pre-flight
on: [push, pull_request]

jobs:
  arxiv-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: YuZh98/latex2arxiv@v0.7.0
        with:
          input: paper/        # directory of .tex sources, or a .zip path
          main: main.tex       # optional; auto-detected from \documentclass
```

The action accepts a directory or a `.zip` for `input`. If a directory, it's zipped on the fly. By default it runs in `--dry-run` mode (no output written, but `[error]` lines fail the job). Set `dry-run: 'false'` to actually emit the cleaned zip — useful in a release workflow:

```yaml
      - uses: YuZh98/latex2arxiv@v0.7.0
        id: clean
        with:
          input: paper/
          dry-run: 'false'
      - uses: softprops/action-gh-release@v2
        with:
          files: ${{ steps.clean.outputs.cleaned-zip }}
```

| Input | Default | Description |
|---|---|---|
| `input` | (required) | Path to the input — `.zip` file or directory of LaTeX sources. |
| `main` | (auto-detect) | Main `.tex` filename. |
| `config` | (none) | Path to a YAML config for custom removal rules. |
| `dry-run` | `'true'` | If `'false'`, emit the cleaned zip alongside the input. |
| `version` | (latest) | Pin a specific `latex2arxiv` version (e.g. `'0.7.0'`). |
| `python-version` | `'3.12'` | Python version used to install `latex2arxiv`. |

**Output:** `cleaned-zip` — path to the cleaned zip when `dry-run: 'false'` (empty otherwise).

## `pre-commit` hook

For repos that keep a built submission zip checked in:

```yaml
repos:
  - repo: https://github.com/YuZh98/latex2arxiv
    rev: v0.7.0
    hooks:
      - id: latex2arxiv-dryrun
        files: paper\.zip$  # restrict to your submission zip
```

For paper repos that store `.tex` sources directly (the more common case), prefer the GitHub Action above — it can zip on the fly.
