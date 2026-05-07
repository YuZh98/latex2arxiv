import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import { promisify } from 'util';

const execFile = promisify(cp.execFile);

let diagnosticCollection: vscode.DiagnosticCollection;
let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;

interface ParsedIssue {
    severity: vscode.DiagnosticSeverity;
    message: string;
}

export function activate(context: vscode.ExtensionContext) {
    diagnosticCollection = vscode.languages.createDiagnosticCollection('latex2arxiv');
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.command = 'latex2arxiv.validate';
    outputChannel = vscode.window.createOutputChannel('latex2arxiv');

    context.subscriptions.push(
        diagnosticCollection,
        statusBarItem,
        outputChannel,
        vscode.commands.registerCommand('latex2arxiv.validate', () => validate()),
        vscode.commands.registerCommand('latex2arxiv.clean', () => clean()),
        vscode.workspace.onDidSaveTextDocument(doc => {
            const cfg = vscode.workspace.getConfiguration('latex2arxiv');
            if (cfg.get<boolean>('validateOnSave') && doc.languageId === 'latex') {
                validate();
            }
        }),
    );

    setIdleStatus();
    statusBarItem.show();

    if (vscode.workspace.workspaceFolders?.length) {
        validate();
    }
}

export function deactivate() {}

function getExecutable(): string {
    return vscode.workspace
        .getConfiguration('latex2arxiv')
        .get<string>('executablePath') || 'latex2arxiv';
}

function getWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
    return vscode.workspace.workspaceFolders?.[0];
}

async function validate(): Promise<void> {
    const folder = getWorkspaceFolder();
    if (!folder) {
        vscode.window.showWarningMessage('latex2arxiv: open a folder to validate');
        return;
    }

    const exe = getExecutable();
    let stdout = '';
    let stderr = '';

    try {
        const r = await execFile(exe, [folder.uri.fsPath, '--dry-run'], {
            cwd: folder.uri.fsPath,
            maxBuffer: 16 * 1024 * 1024,
        });
        stdout = r.stdout;
        stderr = r.stderr;
    } catch (err) {
        const e = err as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
        // Non-zero exit (errors found) still produces stdout we can parse.
        if (e && (e.stdout != null || e.stderr != null)) {
            stdout = e.stdout || '';
            stderr = e.stderr || '';
        } else {
            vscode.window.showErrorMessage(
                `latex2arxiv: failed to invoke '${exe}'. Install via 'pip install latex2arxiv' or set 'latex2arxiv.executablePath'.`,
            );
            setBrokenStatus();
            diagnosticCollection.clear();
            return;
        }
    }

    outputChannel.replace(stdout + (stderr ? `\n--- stderr ---\n${stderr}` : ''));

    const issues = parseIssues(stdout);
    const { located, unlocated } = await mapIssuesToFiles(issues, folder.uri.fsPath);
    applyDiagnostics(located, unlocated);

    const errors = issues.filter(i => i.severity === vscode.DiagnosticSeverity.Error).length;
    const warnings = issues.filter(i => i.severity === vscode.DiagnosticSeverity.Warning).length;
    setResultStatus(errors, warnings);
}

async function clean(): Promise<void> {
    const folder = getWorkspaceFolder();
    if (!folder) {
        vscode.window.showWarningMessage('latex2arxiv: open a folder to clean');
        return;
    }
    const exe = getExecutable();

    await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'latex2arxiv: converting…' },
        async () => {
            try {
                const r = await execFile(exe, [folder.uri.fsPath], {
                    cwd: folder.uri.fsPath,
                    maxBuffer: 16 * 1024 * 1024,
                });
                outputChannel.replace(r.stdout);
                const out = parseOutputZip(r.stdout, folder.uri.fsPath);
                const action = await vscode.window.showInformationMessage(
                    out
                        ? `latex2arxiv: created ${path.basename(out)}`
                        : 'latex2arxiv: conversion complete',
                    ...(out ? ['Reveal in Explorer'] : []),
                    'Show Output',
                );
                if (action === 'Reveal in Explorer' && out) {
                    await vscode.commands.executeCommand('revealFileInOS', vscode.Uri.file(out));
                } else if (action === 'Show Output') {
                    outputChannel.show();
                }
            } catch (err) {
                const e = err as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
                outputChannel.replace((e.stdout || '') + (e.stderr ? `\n--- stderr ---\n${e.stderr}` : ''));
                if (e.stdout == null && e.stderr == null) {
                    vscode.window.showErrorMessage(
                        `latex2arxiv: failed to invoke '${exe}'. Install via 'pip install latex2arxiv' or set 'latex2arxiv.executablePath'.`,
                    );
                    return;
                }
                const action = await vscode.window.showErrorMessage(
                    'latex2arxiv: conversion blocked by pre-flight errors. See Output for details.',
                    'Show Output',
                );
                if (action === 'Show Output') outputChannel.show();
            }
        },
    );
}

function parseIssues(stdout: string): ParsedIssue[] {
    const out: ParsedIssue[] = [];
    const re = /^\s*\[(error|warn)\]\s+(.+)$/gm;
    let m: RegExpExecArray | null;
    while ((m = re.exec(stdout))) {
        out.push({
            severity:
                m[1] === 'error'
                    ? vscode.DiagnosticSeverity.Error
                    : vscode.DiagnosticSeverity.Warning,
            message: m[2].trim(),
        });
    }
    return out;
}

function parseOutputZip(stdout: string, cwd: string): string | undefined {
    const m = stdout.match(/Converting\s+\S+\s+→\s+(\S+)/);
    if (!m) return undefined;
    const out = m[1];
    return path.isAbsolute(out) ? out : path.join(cwd, out);
}

async function mapIssuesToFiles(
    issues: ParsedIssue[],
    workspaceRoot: string,
): Promise<{
    located: Map<string, vscode.Diagnostic[]>;
    unlocated: ParsedIssue[];
}> {
    const texFiles = await findTexFiles(workspaceRoot);
    const sources = new Map<string, string>();
    for (const f of texFiles) {
        try {
            sources.set(f, fs.readFileSync(f, 'utf-8'));
        } catch {
            /* unreadable file — skip */
        }
    }

    const located = new Map<string, vscode.Diagnostic[]>();
    const unlocated: ParsedIssue[] = [];

    for (const issue of issues) {
        const placed = tryPlace(issue, sources, located, workspaceRoot);
        if (!placed) unlocated.push(issue);
    }
    return { located, unlocated };
}

async function findTexFiles(workspaceRoot: string): Promise<string[]> {
    // Scope the glob to this folder; otherwise multi-root workspaces leak .tex
    // files from sibling folders that path.resolve(workspaceRoot, ...) would
    // then misinterpret as relative paths.
    const include = new vscode.RelativePattern(workspaceRoot, '**/*.tex');
    const uris = await vscode.workspace.findFiles(include, '**/{node_modules,.git}/**');
    return uris.map(u => u.fsPath);
}

function tryPlace(
    issue: ParsedIssue,
    sources: Map<string, string>,
    located: Map<string, vscode.Diagnostic[]>,
    workspaceRoot: string,
): boolean {
    // 1. Issues that name a file path explicitly.
    const fileMatch = issue.message.match(/^filename contains [^:]+:\s*(\S+)/);
    if (fileMatch) {
        const target = path.resolve(workspaceRoot, fileMatch[1]);
        if (fs.existsSync(target)) {
            push(located, target, new vscode.Range(0, 0, 0, 0), issue);
            return true;
        }
    }

    const subMatch = issue.message.match(/^(\S+)\s+\(via \\subfile\)\s+contains\s+\\bibliographystyle/);
    if (subMatch) {
        const target = resolveRel(workspaceRoot, subMatch[1], sources);
        if (target) {
            const src = sources.get(target)!;
            const idx = src.search(/\\bibliographystyle\{/);
            const range = idx >= 0
                ? rangeAt(src, idx, '\\bibliographystyle'.length)
                : new vscode.Range(0, 0, 0, 0);
            push(located, target, range, issue);
            return true;
        }
    }

    const mainTexMatch = issue.message.match(/^main tex '([^']+)' is not at the submission root/);
    if (mainTexMatch) {
        const target = resolveRel(workspaceRoot, mainTexMatch[1], sources);
        if (target) {
            push(located, target, new vscode.Range(0, 0, 0, 0), issue);
            return true;
        }
    }

    const utfMatch = issue.message.match(/^(\S+)\s+is not valid UTF-8/);
    if (utfMatch) {
        const target = resolveRel(workspaceRoot, utfMatch[1], sources);
        if (target) {
            push(located, target, new vscode.Range(0, 0, 0, 0), issue);
            return true;
        }
    }

    // 2. Generic content locator: regex-search every .tex source.
    const locator = locatorFor(issue.message);
    if (locator) {
        for (const [file, src] of sources) {
            const m = locator.exec(src);
            locator.lastIndex = 0;
            if (m) {
                push(located, file, rangeAt(src, m.index, m[0].length), issue);
                return true;
            }
        }
    }
    return false;
}

function locatorFor(msg: string): RegExp | null {
    // \usepackage{PKG}
    const pkgMatch = msg.match(/\\usepackage\{([^}]+)\}/);
    if (pkgMatch) {
        const pkg = escapeRegex(pkgMatch[1]);
        return new RegExp(`\\\\usepackage(?:\\[[^\\]]*\\])?\\{[^}]*\\b${pkg}\\b[^}]*\\}`);
    }
    if (msg.includes('\\today used in \\date')) return /\\date\s*\{[^}]*\\today/;

    const epsMatch = msg.match(/\.eps image found:\s*(\S+)/);
    if (epsMatch) return new RegExp(escapeRegex(epsMatch[1]));

    if (msg.startsWith('\\printindex used')) return /\\printindex\b/;
    if (msg.startsWith('\\printglossary used')) return /\\printglossar(?:y|ies)\b/;
    if (msg.startsWith('\\printnomenclature used')) return /\\printnomenclature\b/;
    if (msg.startsWith('\\tikzexternalize used')) return /\\tikzexternalize\b/;

    if (msg.includes("'referee' or 'doublespace'")) {
        return /\\documentclass\[[^\]]*\b(?:referee|doublespace)\b/;
    }
    if (msg.startsWith('double-spacing command detected')) {
        return /\\(?:doublespacing|setstretch\s*\{[2-9])/;
    }
    if (msg.startsWith('biblatex detected but no')) {
        return /\\(?:usepackage(?:\[[^\]]*\])?\{[^}]*\bbiblatex\b|addbibresource)/;
    }

    const absMatch = msg.match(/absolute path in \\input\/\\includegraphics:\s*'([^']+)'/);
    if (absMatch) return new RegExp(escapeRegex(absMatch[1]));

    const xrMatch = msg.match(/\\usepackage\{(xr-hyper|xr)\}/);
    if (xrMatch) {
        const pkg = escapeRegex(xrMatch[1]);
        return new RegExp(`\\\\usepackage(?:\\[[^\\]]*\\])?\\{[^}]*\\b${pkg}\\b[^}]*\\}`);
    }

    return null;
}

function escapeRegex(s: string): string {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function rangeAt(src: string, offset: number, length: number): vscode.Range {
    const before = src.slice(0, offset);
    const line = (before.match(/\n/g) || []).length;
    const lastNl = before.lastIndexOf('\n');
    const col = offset - (lastNl + 1);
    return new vscode.Range(line, col, line, col + length);
}

function resolveRel(workspaceRoot: string, rel: string, sources: Map<string, string>): string | undefined {
    const abs = path.resolve(workspaceRoot, rel);
    if (sources.has(abs)) return abs;
    if (fs.existsSync(abs)) return abs;
    // Fallback: match by basename / suffix.
    for (const f of sources.keys()) {
        if (f === abs || f.endsWith(path.sep + rel) || f.endsWith('/' + rel)) return f;
    }
    return undefined;
}

function push(
    located: Map<string, vscode.Diagnostic[]>,
    file: string,
    range: vscode.Range,
    issue: ParsedIssue,
): void {
    const arr = located.get(file) || [];
    const d = new vscode.Diagnostic(range, issue.message, issue.severity);
    d.source = 'latex2arxiv';
    arr.push(d);
    located.set(file, arr);
}

function applyDiagnostics(
    located: Map<string, vscode.Diagnostic[]>,
    unlocated: ParsedIssue[],
): void {
    diagnosticCollection.clear();
    for (const [file, diags] of located) {
        diagnosticCollection.set(vscode.Uri.file(file), diags);
    }
    if (unlocated.length > 0) {
        outputChannel.appendLine('');
        outputChannel.appendLine('--- Issues without a file:line location ---');
        for (const u of unlocated) {
            const tag = u.severity === vscode.DiagnosticSeverity.Error ? 'error' : 'warn';
            outputChannel.appendLine(`[${tag}] ${u.message}`);
        }
    }
}

function setIdleStatus(): void {
    statusBarItem.text = '$(search) arXiv';
    statusBarItem.tooltip = 'latex2arxiv: click to validate';
    statusBarItem.backgroundColor = undefined;
}

function setBrokenStatus(): void {
    statusBarItem.text = '$(warning) arXiv: not installed';
    statusBarItem.tooltip = "latex2arxiv executable not found. Install: pip install latex2arxiv";
    statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
}

function setResultStatus(errors: number, warnings: number): void {
    if (errors === 0 && warnings === 0) {
        statusBarItem.text = '$(check) arXiv';
        statusBarItem.tooltip = 'latex2arxiv: no issues — click to re-run';
        statusBarItem.backgroundColor = undefined;
    } else if (errors > 0) {
        statusBarItem.text = `$(error) arXiv: ${errors}E ${warnings}W`;
        statusBarItem.tooltip = 'latex2arxiv: pre-flight errors block submission — click to re-run';
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    } else {
        statusBarItem.text = `$(warning) arXiv: ${warnings}W`;
        statusBarItem.tooltip = 'latex2arxiv: warnings — click to re-run';
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    }
}
