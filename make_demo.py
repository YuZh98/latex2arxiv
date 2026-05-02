#!/usr/bin/env python3
"""Generate demo_project.zip for testing latex2arxiv converter."""
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
This document is the built-in demo for \texttt{latex2arxiv}.
Run it with:
\begin{verbatim}
latex2arxiv --demo --compile
\end{verbatim}
The converter processes \texttt{demo\_project.zip} and opens the cleaned PDF.
Each section below demonstrates one pipeline stage or CLI feature.
The source contains intentional draft artifacts; the output PDF is the cleaned version.
\end{abstract}

\input{sections/pruning.tex}
\input{sections/comments.tex}
\input{sections/annotations.tex}
\input{sections/custom_rules.tex}
\input{sections/bibtex.tex}
\input{sections/pdfoutput.tex}
\input{sections/warnings.tex}
\input{sections/cli_tools.tex}

\bibliographystyle{plain}
\bibliography{refs}

\end{document}
"""

# ── Section 1: File pruning ────────────────────────────────────────────────────
files['sections/pruning.tex'] = r"""
\section{Stage 1 — File Pruning}

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
\bottomrule
\end{tabular}
\end{table}

The used figure (Figure~\ref{fig:example}) is kept because it is referenced.

\begin{figure}[h]
  \centering
  \includegraphics[width=0.45\textwidth]{figures/example}
  \caption{This figure is referenced and therefore kept.}
  \label{fig:example}
\end{figure}
"""

# ── Section 2: Comment stripping ──────────────────────────────────────────────
files['sections/comments.tex'] = r"""
\section{Stage 2 — Comment Stripping}

All \texttt{\%} line comments are removed from \texttt{.tex} files.
The source of this section contains several comments that do not appear here.
% This comment is invisible in the output PDF.
% So is this one.

Comments inside \verb|verbatim| environments are preserved:
\begin{verbatim}
% This comment is inside verbatim and is kept as-is.
\end{verbatim}

Escaped percent signs like 100\% are not affected.

\begin{comment}
This entire block is inside a \begin{comment} environment.
It will be removed by the converter.
The reader cannot see this text in the output PDF.
\end{comment}

The \verb|\begin{comment}| block above has also been removed.
\iffalse
  This \iffalse...\fi block is also removed.
  It is another common way to comment out large sections.
\fi
And the \verb|\iffalse...\fi| block above is gone too.
"""

# ── Section 3: Draft annotation removal ───────────────────────────────────────
files['sections/annotations.tex'] = r"""
\section{Stage 3 — Draft Annotation Removal}

Common draft commands are removed automatically.
The source contains the following, none of which appear in the output:

\begin{itemize}
  \item \verb|\todo{...}| — \todo{This todo is removed from the output.}
        removed (the box you do not see was here)
  \item \verb|\hl{...}| — highlighted text is \hl{unwanted in submission}
        (the highlight is gone in the output)
  \item \verb|\note{...}| and \verb|\fixme{...}| — similarly removed
  \item \verb|\usepackage{todonotes}| — the package itself is stripped
\end{itemize}
"""

# ── Section 4: Custom rules ────────────────────────────────────────────────────
files['sections/custom_rules.tex'] = r"""
\section{Stage 4 — Custom Rules (\texttt{--config})}

For project-specific revision markup, use a YAML config file.
This section's source uses \verb|\color{red}| for revision text.
When the converter is run with \texttt{--config arxiv\_config.yaml},
the color command is unwrapped and the text is preserved in black.

Example config:
\begin{verbatim}
commands_to_unwrap:
  - color{red}
  - textcolor{red}
\end{verbatim}

Without the config, {\color{red}this text would appear red in the PDF}.
With the config, the \verb|\color{red}| switch is stripped and the text
appears in the normal body color.

You can also delete commands entirely (text lost), remove environments,
or apply raw regex replacements. See \texttt{arxiv\_config.yaml} for a
full template.
"""

# ── Section 5: BibTeX normalization ───────────────────────────────────────────
files['sections/bibtex.tex'] = r"""
\section{Stage 5 — BibTeX Normalization}

The \texttt{refs.bib} file in this demo contains:
\begin{itemize}
  \item A duplicate entry (same DOI) — one copy is removed~\cite{arxiv_submission}
  \item Private fields (\texttt{abstract}, \texttt{file}) — stripped before submission
  \item Fields reordered to a canonical format
\end{itemize}

Install \texttt{bibtexparser} to enable this stage:
\begin{verbatim}
pip install bibtexparser
\end{verbatim}
"""

# ── Section 6: pdfoutput injection ────────────────────────────────────────────
files['sections/pdfoutput.tex'] = r"""
\section{Stage 6 — \texttt{\textbackslash pdfoutput=1} Injection}

arXiv requires \verb|\pdfoutput=1| to appear before \verb|\documentclass|
to force PDF output mode.
The converter injects it automatically if it is missing.

The source of this demo does \emph{not} contain \verb|\pdfoutput=1|.
After conversion, the output \texttt{main.tex} begins with:
\begin{verbatim}
\pdfoutput=1
\documentclass[12pt]{article}
...
\end{verbatim}

If \verb|\pdfoutput=1| is already present, the converter leaves it unchanged
and does not insert a duplicate.
"""

# ── Section 7: Compliance warnings ────────────────────────────────────────────
files['sections/warnings.tex'] = r"""
\section{Stage 7 — Compliance Warnings}

The converter prints warnings for common arXiv submission issues.
This demo triggers the following warning:

\begin{itemize}
  \item \textbf{\texttt{\textbackslash today} in \texttt{\textbackslash date}} —
        arXiv occasionally rebuilds PDFs, so the displayed date will change.
        Use a fixed date for stable submissions.
\end{itemize}

Other warnings (not triggered in this demo):
\begin{itemize}
  \item Referee/double-space mode detected in \verb|\documentclass|
  \item Custom \texttt{.cls}/\texttt{.sty} file included in the project
  \item \texttt{.eps} images found (not supported by pdflatex)
\end{itemize}
"""

# ── Section 8: CLI tools ───────────────────────────────────────────────────────
files['sections/cli_tools.tex'] = r"""
\section{CLI Tools}

\subsection{\texttt{--dry-run}: Preview Without Writing}

Pass \texttt{--dry-run} to see exactly what the converter would do,
without writing any output file:
\begin{verbatim}
latex2arxiv paper.zip --dry-run
\end{verbatim}
The terminal will list every file that would be removed or processed,
then print:
\begin{verbatim}
[dry-run] No output written. Would have created: paper_arxiv.zip
\end{verbatim}
This is useful for a quick sanity check before committing to the conversion.

\subsection{\texttt{--resize}: Shrink Images for the 50\,MB Limit}

arXiv enforces a 50\,MB submission limit.
If your project contains high-resolution figures, use \texttt{--resize}
to cap the longest side of every image at a given pixel count:
\begin{verbatim}
latex2arxiv paper.zip --resize 1600 --compile
\end{verbatim}
Requires \texttt{Pillow} (\texttt{pip install Pillow}).
The converter resizes \texttt{.png}, \texttt{.jpg}, \texttt{.pdf},
and other supported formats in-place in the output zip.

\subsection{\texttt{--demo}: Run the Built-In Demo}

No input file needed:
\begin{verbatim}
latex2arxiv --demo --compile
\end{verbatim}
The converter locates the bundled \texttt{demo\_project.zip} from the
installed package, processes it, and opens the resulting PDF —
the document you are reading right now.
"""

# ── Unused tex file (should be removed) ───────────────────────────────────────
files['sections/old_draft.tex'] = r"""
\section{Old Draft}
This section is not reachable from main.tex and will be deleted.
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
