# latex2arxiv — VS Code extension

arXiv pre-flight validation for LaTeX projects, surfaced as VS Code diagnostics.

## Requirements

The Python CLI must be on `PATH`:

```sh
pip install latex2arxiv
```

If it's not on `PATH`, set `latex2arxiv.executablePath` in settings to its absolute path.

## Commands

| Command | What it does |
|---|---|
| `latex2arxiv: Validate` | Runs `latex2arxiv --dry-run` on the workspace; surfaces `[error]` / `[warn]` lines in the Problems panel and status bar. |
| `latex2arxiv: Clean for arXiv` | Runs the full conversion; on success, shows the output zip with a "Reveal in Explorer" action. |

## Settings

| Setting | Type | Default | Description |
|---|---|---|---|
| `latex2arxiv.executablePath` | string | `"latex2arxiv"` | Path to the CLI. |
| `latex2arxiv.validateOnSave` | boolean | `false` | Re-validate when a `.tex` file is saved. |

## Status bar

- `$(check) arXiv` — no issues.
- `$(warning) arXiv: 3W` — warnings only.
- `$(error) arXiv: 2E 3W` — errors block submission.
- `$(warning) arXiv: not installed` — CLI not found on PATH.

Click the item to re-run validation.

## Diagnostic mapping

Diagnostics are mapped to file:line by regex-searching `.tex` sources for the pattern that triggered each check (e.g. `\usepackage{minted}`, `\today` inside `\date`, `.eps` filename in `\includegraphics`). Issues without a precise location (size warnings, encoding warnings on directories, etc.) are routed to the **Output → latex2arxiv** channel.

## Develop

```sh
npm install
npm run compile
```

Press <kbd>F5</kbd> in VS Code to launch the Extension Development Host. Open a folder with `.tex` files (e.g. `tests/fixtures/05-pre-flight-warnings/` from the `latex2arxiv` repo) and run **latex2arxiv: Validate** from the command palette.
