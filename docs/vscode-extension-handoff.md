# VS Code Extension Implementation Handoff

## Context

`latex2arxiv` is a Python CLI tool that validates and cleans LaTeX projects for arXiv submission. It's published on PyPI (`pip install latex2arxiv`). The repo is at `/Users/zhengyu/Desktop/Claude/Project/latex2arxiv`.

The tool already has:
- CLI: `latex2arxiv paper.zip --dry-run` (prints `[error]` and `[warn]` lines)
- MCP server: `latex2arxiv-mcp` (exposes `validate_submission` and `clean_submission` tools)
- GitHub Action + pre-commit hook

We now want a **VS Code extension** that surfaces pre-flight diagnostics directly in the editor.

## What to build

A VS Code extension called `latex2arxiv` that:

1. **Command: "latex2arxiv: Validate"** — runs pre-flight on the current workspace, shows results as VS Code Diagnostics (Problems panel)
2. **Command: "latex2arxiv: Clean for arXiv"** — runs full conversion, shows notification with output zip path
3. **Status bar item** — shows "arXiv: ✓" (green) or "arXiv: 2 errors, 3 warnings" (red/yellow)
4. **Auto-validate on save** (optional, off by default, configurable via `latex2arxiv.validateOnSave`)

## Architecture

```
vscode-latex2arxiv/
├── package.json          # Extension manifest, commands, config
├── tsconfig.json
├── src/
│   └── extension.ts      # Main entry point
├── .vscodeignore
└── README.md
```

### How it works

1. Extension calls `latex2arxiv --dry-run` (or `latex2arxiv --dry-run --json` if we add that) as a child process on the workspace root
2. Parses stdout for `[error]` and `[warn]` lines
3. For each diagnostic, does a regex search in the workspace `.tex` files to find the matching line (e.g., searches for `\usepackage{minted}` to locate the line number)
4. Creates `vscode.Diagnostic` objects and sets them on a `DiagnosticCollection`
5. Updates the status bar

### Key design decisions

- **Requires `latex2arxiv` installed in PATH** (or user-configured path via `latex2arxiv.executablePath` setting)
- **Workspace-level** — validates the entire project, not individual files
- **Diagnostics mapped by regex** — since the CLI doesn't output line numbers, the extension searches for the pattern that triggered each check:
  - `[error] \usepackage{minted}...` → search for `\usepackage{minted}` or `\usepackage{...minted...}` in .tex files
  - `[warn] .eps image found: photo.eps` → search for `photo.eps` in \includegraphics commands
  - Warnings without a locatable pattern (e.g., "output > 50 MB") → show as workspace-level diagnostics with no file/line

### Parsing the CLI output

Each line from `latex2arxiv --dry-run` looks like:
```
  [error] \usepackage{minted} requires shell-escape — arXiv compiles without it; this submission will fail to build
  [warn] \today used in \date — arXiv may rebuild the PDF and the date will change
  [warn] .eps image found: photo.eps — pdflatex does not support .eps; convert to .pdf or .png
  remove: unused.tex
  main tex: main.tex
Summary: 2 removed, 5 kept | 2 errors, 3 warnings
```

Parse with regex: `/\s+\[(error|warn)\]\s+(.+)/`

### Pattern-to-line mapping table

| CLI output pattern | Search regex in .tex files |
|---|---|
| `\usepackage{PKG}` | `\\usepackage(\[.*?\])?\{[^}]*\bPKG\b` |
| `\today used in \date` | `\\date\s*\{[^}]*\\today` |
| `.eps image found: FILE` | `FILE` in any `\includegraphics` |
| `\printindex` | `\\printindex` |
| `\printglossary` | `\\printglossar` |
| `\tikzexternalize` | `\\tikzexternalize` |
| `absolute path` | the path string itself |
| `referee` or `doublespace` | `\\documentclass\[.*?(referee|doublespace)` |
| Others (size, encoding, etc.) | Workspace-level diagnostic (no file/line) |

## package.json key fields

```json
{
  "name": "latex2arxiv",
  "displayName": "latex2arxiv",
  "description": "arXiv pre-flight validation for LaTeX projects",
  "version": "0.1.0",
  "publisher": "YuZh98",
  "engines": { "vscode": "^1.85.0" },
  "categories": ["Linters"],
  "activationEvents": ["workspaceContains:**/*.tex"],
  "main": "./out/extension.js",
  "contributes": {
    "commands": [
      { "command": "latex2arxiv.validate", "title": "latex2arxiv: Validate" },
      { "command": "latex2arxiv.clean", "title": "latex2arxiv: Clean for arXiv" }
    ],
    "configuration": {
      "title": "latex2arxiv",
      "properties": {
        "latex2arxiv.executablePath": {
          "type": "string",
          "default": "latex2arxiv",
          "description": "Path to the latex2arxiv executable"
        },
        "latex2arxiv.validateOnSave": {
          "type": "boolean",
          "default": false,
          "description": "Run validation automatically when a .tex file is saved"
        }
      }
    }
  }
}
```

## Implementation outline for extension.ts

```typescript
import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

let diagnosticCollection: vscode.DiagnosticCollection;
let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
    diagnosticCollection = vscode.languages.createDiagnosticCollection('latex2arxiv');
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
    statusBarItem.command = 'latex2arxiv.validate';
    statusBarItem.show();

    context.subscriptions.push(
        vscode.commands.registerCommand('latex2arxiv.validate', validate),
        vscode.commands.registerCommand('latex2arxiv.clean', clean),
        diagnosticCollection,
        statusBarItem,
    );

    // Optional: validate on save
    if (vscode.workspace.getConfiguration('latex2arxiv').get('validateOnSave')) {
        vscode.workspace.onDidSaveTextDocument(doc => {
            if (doc.languageId === 'latex') validate();
        });
    }

    // Initial validation
    validate();
}

async function validate() {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!workspaceFolder) return;

    const executable = vscode.workspace.getConfiguration('latex2arxiv').get<string>('executablePath') || 'latex2arxiv';

    try {
        const { stdout } = await execFileAsync(executable, [workspaceFolder, '--dry-run'], {
            cwd: workspaceFolder,
        });
        const diagnostics = parseDiagnostics(stdout, workspaceFolder);
        applyDiagnostics(diagnostics);
    } catch (err: any) {
        // Non-zero exit means errors found — still parse stdout
        if (err.stdout) {
            const diagnostics = parseDiagnostics(err.stdout, workspaceFolder);
            applyDiagnostics(diagnostics);
        }
    }
}

async function clean() {
    // Similar to validate but without --dry-run
    // Show output zip path in notification
}

function parseDiagnostics(stdout: string, workspaceFolder: string) {
    // Parse [error] and [warn] lines
    // For each, search .tex files for the pattern to find file + line
    // Return Map<uri, Diagnostic[]>
}

function applyDiagnostics(diagnostics: Map<vscode.Uri, vscode.Diagnostic[]>) {
    diagnosticCollection.clear();
    for (const [uri, diags] of diagnostics) {
        diagnosticCollection.set(uri, diags);
    }
    // Update status bar
    const errors = /* count */;
    const warnings = /* count */;
    if (errors === 0 && warnings === 0) {
        statusBarItem.text = '$(check) arXiv';
        statusBarItem.backgroundColor = undefined;
    } else {
        statusBarItem.text = `$(alert) arXiv: ${errors}E ${warnings}W`;
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    }
}
```

## Testing

1. `npm install && npm run compile`
2. Press F5 in VS Code to launch Extension Development Host
3. Open a folder with `.tex` files (use `tests/fixtures/05-pre-flight-warnings/`)
4. Run "latex2arxiv: Validate" from command palette
5. Check Problems panel for diagnostics

## What NOT to do

- Don't bundle Python or latex2arxiv inside the extension — require it installed externally
- Don't try to parse LaTeX yourself — let the CLI do the work
- Don't make it async-heavy — one subprocess call per validation is fine
- Don't publish to Marketplace until manually tested

## Future improvements (not for v0.1)

- `--json` output mode in the CLI for precise file:line:col diagnostics
- Quick-fix actions (e.g., "Replace psfig with graphicx")
- Webview panel showing the full pre-flight report
- Integration with the MCP server instead of CLI subprocess
