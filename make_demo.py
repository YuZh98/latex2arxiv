#!/usr/bin/env python3
"""Generate demo_project.zip for testing latex2arxiv converter.

The demo is a self-documenting paper. Sections are ordered by user value,
not by pipeline order: pruning headline → arXiv compatibility → tex cleanup
→ revision markup → BibTeX → CLI tools.
"""
import struct
import zlib
import zipfile

files = {}

# ── Main tex file ──────────────────────────────────────────────────────────────
files['main.tex'] = r"""\documentclass[12pt]{article}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{comment}
\usepackage{todonotes}  % draft-only package — will be removed

% \input{unused_section.tex}  % commented out — converter ignores this

\title{\texttt{latex2arxiv}: A Self-Documenting Demo}
\author{Demo Author}
\date{\today}  % \today triggers a compliance warning

\begin{document}
\maketitle

\begin{abstract}
\texttt{latex2arxiv} converts a LaTeX \texttt{.zip} project into an arXiv-ready
\texttt{.zip} in one command. On a real statistics paper it took
\textbf{950 files / 82\,MB} down to \textbf{40 files / 3\,MB} in seconds.
This document is the bundled demo. Run it with:
\begin{verbatim}
latex2arxiv --demo --compile
\end{verbatim}
The tool processes \texttt{demo\_project.zip} and opens the cleaned PDF.
The sections below are ordered by user value: what the tool removes, what it
checks for arXiv compatibility, then progressively narrower features.
\end{abstract}

\input{sections/pruning.tex}
\input{sections/compatibility.tex}
\input{sections/tex_cleanup.tex}
\input{sections/revision_markup.tex}
\input{sections/bibtex.tex}
\input{sections/cli_tools.tex}

\bibliographystyle{plain}
\bibliography{refs}

\end{document}
"""

# ── §1: What gets removed ─────────────────────────────────────────────────────
files['sections/pruning.tex'] = r"""
\section{What Gets Removed}

The converter keeps only files that are provably needed to compile the paper.
Everything else is deleted.
Table~\ref{tab:pruned} lists what was removed from this demo zip.

\begin{table}[h]
\centering
\caption{Files removed from \texttt{demo\_project.zip} by the converter.}
\label{tab:pruned}
\begin{tabular}{ll}
\toprule
\textbf{File} & \textbf{Reason removed} \\
\midrule
\texttt{sections/old\_draft.tex}  & Not reachable from \texttt{main.tex} \\
\texttt{figures/unused\_plot.png} & Not referenced by any \verb|\includegraphics| \\
\texttt{main.aux}, \texttt{main.log} & Build artifacts \\
\texttt{.DS\_Store}               & macOS metadata \\
\texttt{cover\_letter.md}         & Non-\LaTeX{} file \\
\texttt{arxiv\_config.yaml}       & Working config (used, then dropped from output) \\
\bottomrule
\end{tabular}
\end{table}

Dependency tracking respects \verb|\input|, \verb|\include|, \verb|\subfile|,
\verb|\includegraphics|, \verb|\graphicspath|, and \verb|\bibliography|.
Commented-out commands are ignored, so a stray
\texttt{\% \textbackslash input\{old\_draft\}} will not pull in dead code.
The used figure (Figure~\ref{fig:example}) is kept because it is referenced.

\begin{figure}[h]
  \centering
  \includegraphics[width=0.45\textwidth]{figures/example}
  \caption{This figure is referenced and therefore kept.}
  \label{fig:example}
\end{figure}
"""

# ── §2: arXiv compatibility (pre-flight + auto-fixes + warnings) ──────────────
# Note: command-name mentions use \texttt{\textbackslash ...} rather than
# \verb|...| so that the literal trigger patterns (\documentclass,
# \usepackage{minted}, \usepackage{biblatex}) do not appear in the source —
# otherwise find_main_tex and the pre-flight regexes would fire on them.
files['sections/compatibility.tex'] = r"""
\section{arXiv Compatibility}

The converter runs pre-flight checks and auto-fixes against arXiv's submission
requirements. The terminal output uses two severities:

\begin{itemize}
  \item \texttt{[error]} — the submission will fail; tool exits non-zero
  \item \texttt{[warn]}  — likely a problem; review before submitting
\end{itemize}

\subsection*{Auto-fixes (silent)}

\begin{itemize}
  \item \texttt{\textbackslash pdfoutput=1} is injected before
        \texttt{\textbackslash documentclass} if missing (arXiv requires it for
        PDF mode). The cleaned \texttt{main.tex} starts with it even though the
        source does not.
  \item Unused draft-only packages (\texttt{todonotes}, \texttt{changes}, etc.)
        are removed.
\end{itemize}

\subsection*{Pre-flight errors (block submission)}

\begin{itemize}
  \item \texttt{\textbackslash usepackage\{minted\}} /
        \texttt{pythontex} / \texttt{shellesc} —
        require \texttt{-{}-shell-escape}; arXiv compiles without it, so these
        always fail to build on arXiv.
\end{itemize}

\subsection*{Pre-flight warnings (review before submitting)}

\begin{itemize}
  \item \texttt{\textbackslash usepackage\{biblatex\}} or
        \texttt{\textbackslash addbibresource} without a
        \texttt{.bbl} shipped — if a referenced \texttt{.bib} is missing,
        arXiv will block your submission. Ship the \texttt{.bbl} as a fallback.
  \item Output zip $> 50$\,MB — consider \texttt{-{}-resize} or splitting
        supplementary materials.
  \item Filenames with spaces or non-ASCII characters — rename to ASCII.
  \item \texttt{\textbackslash today} in \texttt{\textbackslash date} — this
        demo triggers it; arXiv may rebuild the PDF and the displayed date
        will change.
  \item \texttt{referee} / \texttt{doublespace} option — arXiv requires
        single-spaced submissions.
  \item Custom \texttt{.cls} / \texttt{.sty} included — verify it is not
        already provided by TeX Live.
  \item \texttt{.eps} images — \texttt{pdflatex} cannot render them.
\end{itemize}

The demo intentionally does not trigger any pre-flight errors.
"""

# ── §3: Cleanup of your .tex (comments + draft annotations) ────────────────────
files['sections/tex_cleanup.tex'] = r"""
\section{Cleanup of Your \texttt{.tex}}

\subsection*{Comment stripping}

All \texttt{\%} line comments are removed from \texttt{.tex} files.
The source of this section contains several comments that do not appear here.
% This comment is invisible in the output PDF.
% So is this one.

Comments inside \verb|verbatim| environments are preserved:
\begin{verbatim}
% This comment is inside verbatim and is kept as-is.
\end{verbatim}

Escaped percent signs like 100\% are not affected.

\subsection*{Comment environments}

\begin{comment}
This entire block is inside a comment environment.
It will be removed by the converter.
\end{comment}

The \texttt{\textbackslash begin\{comment\}} block above has been removed.
\iffalse
  This entire block is also removed by the converter.
\fi
And the \texttt{\textbackslash iffalse...\textbackslash fi} block above is gone too.

\subsection*{Draft annotations}

Common draft commands are removed automatically:

\begin{itemize}
  \item \texttt{\textbackslash todo\{...\}} — \todo{This todo is removed from the output.}
        the box you do not see was here
  \item \texttt{\textbackslash hl\{...\}} — \hl{this highlight is gone in the output}
        no highlighted text appears here in the cleaned PDF
  \item \texttt{\textbackslash note\{...\}} and
        \texttt{\textbackslash fixme\{...\}} — similarly removed
\end{itemize}

Nested braces are handled correctly:
\texttt{\textbackslash todo\{fix \textbackslash textbf\{this\}\}} and
\texttt{\textbackslash todo\{see \textbackslash cite\{key\}\}} are both fully
removed using a brace-balanced matcher, not a simple regex.
"""

# ── §4: Revision markup with --config (actually exercises the config) ────────
files['sections/revision_markup.tex'] = r"""
\section{Revision Markup with \texttt{-{}-config}}

For project-specific revision markup, ship a YAML config file.
This section's source contains live revision markup that the bundled config
removes or unwraps. Compare the source (\texttt{sections/revision\_markup.tex}
in \texttt{demo\_project.zip}) with the rendered text below.

\subsection*{Bundled config}

\begin{verbatim}
commands_to_delete:
  - deleted

commands_to_unwrap:
  - added
  - textcolor{red}
\end{verbatim}

\subsection*{What the rules do, live}

\begin{itemize}
  \item \deleted{This entire reviewer-flagged sentence with a \cite{arxiv_submission} inside is removed.}
        The line you should see starts with ``The line you should see''.
  \item \added{This added text, including \emph{nested emphasis}, is unwrapped — the \texttt{\textbackslash added} wrapper disappears but the words remain.}
  \item \textcolor{red}{This sentence is wrapped in \texttt{\textbackslash textcolor\{red\}\{...\}} but reads as plain body text in the output because the wrapper was unwrapped.}
\end{itemize}

The brace-balanced matcher correctly handles nested commands inside
\texttt{\textbackslash deleted\{...\}} and
\texttt{\textbackslash added\{...\}}, including
\texttt{\textbackslash cite\{\}}, \texttt{\textbackslash emph\{\}},
\texttt{\textbackslash textbf\{\}}, and arbitrary nesting depth.

When the demo runs (\texttt{latex2arxiv --demo}), the bundled
\texttt{arxiv\_config.yaml} is auto-applied; you do not need to pass
\texttt{--config} explicitly.
The config file itself is dropped from the output zip (it is a working file,
not a submission file).
"""

# ── §5: BibTeX cleanup ─────────────────────────────────────────────────────────
files['sections/bibtex.tex'] = r"""
\section{BibTeX Cleanup}

The \texttt{refs.bib} file in this demo contains:
\begin{itemize}
  \item A duplicate entry (same DOI) — one copy is removed~\cite{arxiv_submission}
  \item Private fields (\texttt{abstract}, \texttt{file}) — stripped before submission
  \item Fields reordered to a canonical format
\end{itemize}

When multiple entries share the same DOI or title, the converter prefers the
entry whose key is actually cited in the \texttt{.tex} sources, so cleanup
never breaks a working \verb|\cite{...}|.

Install \texttt{bibtexparser} to enable this stage:
\begin{verbatim}
pip install bibtexparser
\end{verbatim}
Without it, the \texttt{.bib} file is passed through unchanged.
"""

# ── §6: CLI tools & summary line ──────────────────────────────────────────────
files['sections/cli_tools.tex'] = r"""
\section{CLI Tools}

\subsection*{Summary line}

Every run ends with a one-line summary, for example:
\begin{verbatim}
Summary: 6 removed, 11 kept | 0.0 MB → 0.0 MB | 0 errors, 1 warning
\end{verbatim}
Read left to right: file counts (removed/kept), input/output size, then
issue counts from the pre-flight checks.
The MB segment is omitted in \texttt{--dry-run}.

\subsection*{\texttt{-{}-dry-run}: preview without writing}

\begin{verbatim}
latex2arxiv paper.zip --dry-run
\end{verbatim}
Lists every file that would be removed or processed, then prints
\texttt{[dry-run] No output written}.
Useful as a sanity check before committing to the conversion.

\subsection*{\texttt{-{}-resize}: shrink images for the size limit}

\begin{verbatim}
latex2arxiv paper.zip --resize 1600 --compile
\end{verbatim}
Caps the longest side of every image at the given pixel count. Requires
\texttt{Pillow} (\texttt{pip install Pillow}). Combined with the size warning
(\S2), this is the typical fix for an oversized submission.

\subsection*{\texttt{-{}-demo}: this document}

\begin{verbatim}
latex2arxiv --demo --compile
\end{verbatim}
No input file needed. Locates the bundled \texttt{demo\_project.zip},
processes it, and opens the resulting PDF — what you are reading right now.
"""

# ── Unused tex file (should be removed) ───────────────────────────────────────
files['sections/old_draft.tex'] = r"""
\section{Old Draft}
This section is not reachable from main.tex and will be deleted.
"""

# ── Bundled config ─────────────────────────────────────────────────────────────
# Auto-loaded by the --demo path; exercises the brace-balanced config code path.
files['arxiv_config.yaml'] = r"""# Demo config — auto-applied when running `latex2arxiv --demo`.
commands_to_delete:
  - deleted

commands_to_unwrap:
  - added
  - textcolor{red}
"""

# ── BibTeX ─────────────────────────────────────────────────────────────────────
files['refs.bib'] = r"""@misc{arxiv_submission,
  author   = {{arXiv}},
  title    = {Submission Guidelines for TeX/LaTeX},
  year     = {2024},
  url      = {https://info.arxiv.org/help/submit_tex.html},
  abstract = {Private field — will be stripped by the converter.},
  file     = {arxiv_guidelines.pdf},
}

@misc{arxiv_submission_duplicate,
  author = {{arXiv}},
  title  = {Submission Guidelines for TeX/LaTeX},
  year   = {2024},
  url    = {https://info.arxiv.org/help/submit_tex.html},
}
"""

# ── Images ─────────────────────────────────────────────────────────────────────
def _make_png(width=200, height=150) -> bytes:
    """Create a simple gray gradient PNG."""
    def chunk(name, data):
        c = struct.pack('>I', len(data)) + name + data
        return c + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
    raw = b''
    for y in range(height):
        raw += b'\x00'
        for x in range(width):
            v = int(80 + 120 * x / width)
            raw += bytes([v, v, v])
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    idat = chunk(b'IDAT', zlib.compress(raw))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend

files['figures/example.png'] = _make_png()       # used — kept
files['figures/unused_plot.png'] = _make_png()   # unused — removed

# ── Junk files (should be removed) ────────────────────────────────────────────
files['main.aux'] = 'aux content'
files['main.log'] = 'log content'
files['.DS_Store'] = 'mac junk'
files['cover_letter.md'] = 'Dear Editor...'

# ── Write zip ──────────────────────────────────────────────────────────────────
with zipfile.ZipFile('demo_project.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
    for name, content in files.items():
        if isinstance(content, str):
            content = content.encode('utf-8')
        zf.writestr(name, content)

print("Created demo_project.zip")
print("\nRun the demo:")
print("  latex2arxiv --demo --compile")
print("  latex2arxiv --demo --dry-run")
