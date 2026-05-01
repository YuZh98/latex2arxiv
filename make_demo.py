#!/usr/bin/env python3
"""Generate demo_project.zip for testing latex2arxiv converter."""
import zipfile

files = {}

files['main.tex'] = r"""\documentclass[12pt]{article}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{todonotes} % draft only -- will be removed by converter

% \input{unused_section.tex}  % commented out -- converter will ignore this

\title{\texttt{latex2arxiv}: Prepare Your LaTeX Project for arXiv Submission}
\author{Demo Author}
\date{}

\begin{document}
\maketitle

\begin{abstract}
Submitting a paper to arXiv requires cleaning up your LaTeX project:
removing draft annotations, stripping comments, pruning unused files,
and normalizing references.
\texttt{latex2arxiv} automates all of these steps.
This document is itself a demo input --- run the converter on it and
inspect the output to see what changes are made.
\end{abstract}

% ---- Introduction ----
\section{Introduction}

When exporting a project from Overleaf, the resulting \texttt{.zip} typically
contains build artifacts, editor files, unused images, and draft annotations
that should not be submitted to arXiv. % TODO: cite arXiv submission guidelines
\todo{Double-check submission requirements.}

\texttt{latex2arxiv} converts the raw Overleaf export into a clean,
submission-ready \texttt{.zip} in one command:

\begin{verbatim}
python3 converter.py paper.zip --main main.tex --compile
\end{verbatim}

% ---- What the converter does ----
\section{What the Converter Does}

Table~\ref{tab:features} summarizes the pipeline stages.

\begin{table}[h]
\centering
\caption{Pipeline stages applied by \texttt{latex2arxiv}.}
\label{tab:features}
\begin{tabular}{lp{8cm}}
\toprule
\textbf{Stage} & \textbf{Action} \\
\midrule
File pruning    & Removes unused \texttt{.tex}, \texttt{.bib}, and image files,
                  plus all non-essential files (build artifacts, cover letters, etc.) \\
Comment stripping & Removes \texttt{\% ...} comments from all \texttt{.tex} files \\
Draft cleanup   & Removes \verb|\todo{}|, \verb|\hl{}|, \verb|\note{}|,
                  \verb|\fixme{}|, and draft-only packages \\
BibTeX normalization & Canonical field ordering, deduplication, private field removal \\
\texttt{\textbackslash pdfoutput=1} & Injected before \verb|\documentclass| if missing \\
Compile check   & Optional: compiles with \texttt{pdflatex} and opens the PDF \\
\bottomrule
\end{tabular}
\end{table}

\input{sections/results.tex}

% ---- References ----
\bibliographystyle{plain}
\bibliography{refs}

\end{document}
"""

files['sections/results.tex'] = r"""
\section{What Gets Removed in This Demo}

The following files are included in \texttt{demo\_project.zip} but will be
\textbf{removed} by the converter:

\begin{itemize}
  \item \texttt{sections/old\_draft.tex} --- unused \texttt{.tex} file
        (not reachable from \texttt{main.tex})
  \item \texttt{figures/unused\_plot.png} --- image not referenced by any
        \verb|\includegraphics| or \verb|\begin{overpic}|
  \item \texttt{main.aux}, \texttt{main.log} --- build artifacts
  \item \texttt{.DS\_Store} --- macOS metadata
  \item \texttt{cover\_letter.md} --- non-\LaTeX{} file
\end{itemize}

The following \textbf{edits} are made to kept files:

\begin{itemize}
  \item \verb|\pdfoutput=1| injected at the top of \texttt{main.tex}
  \item \verb|\usepackage{todonotes}| removed
  \item All \texttt{\%} comments stripped
  \item \verb|\todo{...}| commands removed
  \item Duplicate BibTeX entry deduplicated; private fields
        (\texttt{abstract}, \texttt{file}) stripped
\end{itemize}

Figure~\ref{fig:example} shows a sample figure that \textbf{is} kept,
since it is referenced in the source.

\begin{figure}[h]
  \centering
  \includegraphics[width=0.5\textwidth]{figures/example}
  \caption{A sample figure included via \texttt{\textbackslash includegraphics}.
           The converter detects this reference and keeps the file.}
  \label{fig:example}
\end{figure}
"""

# Unused tex file — should be removed
files['sections/old_draft.tex'] = r"""
\section{Old Draft}
This section was removed.
"""

files['refs.bib'] = r"""@misc{arxiv_submission,
  author  = {{arXiv}},
  title   = {Submission Guidelines for TeX/LaTeX},
  year    = {2024},
  url     = {https://info.arxiv.org/help/submit_tex.html},
  note    = {Accessed 2024},
  abstract = {This is a private field that will be stripped by the converter.},
  file     = {arxiv_guidelines.pdf},
}

@misc{arxiv_submission_duplicate,
  author  = {{arXiv}},
  title   = {Submission Guidelines for TeX/LaTeX},
  year    = {2024},
  url     = {https://info.arxiv.org/help/submit_tex.html},
}
"""


def _make_png(width=200, height=150) -> bytes:
    """Create a simple gray gradient PNG for demo purposes."""
    import struct, zlib
    def chunk(name, data):
        c = struct.pack('>I', len(data)) + name + data
        return c + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
    # Build raw image: gray gradient left-to-right
    raw = b''
    for y in range(height):
        raw += b'\x00'  # filter type: None
        for x in range(width):
            v = int(80 + 120 * x / width)
            raw += bytes([v, v, v])
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    idat = chunk(b'IDAT', zlib.compress(raw))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


# Used image
files['figures/example.png'] = _make_png()
# Unused image — should be removed
files['figures/unused_plot.png'] = _make_png()

# Junk files — should be removed
files['main.aux'] = 'aux content'
files['main.log'] = 'log content'
files['.DS_Store'] = 'mac junk'
files['cover_letter.md'] = 'Dear Editor...'

with zipfile.ZipFile('demo_project.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
    for name, content in files.items():
        if isinstance(content, str):
            content = content.encode('utf-8')
        zf.writestr(name, content)

print("Created demo_project.zip")
print("\nExpected converter output:")
print("  KEPT:    main.tex, sections/results.tex, refs.bib, figures/example.png")
print("  REMOVED: sections/old_draft.tex, figures/unused_plot.png,")
print("           main.aux, main.log, .DS_Store, cover_letter.md")
print("  CLEANED: comments, \\todo{}, \\hl{}, todonotes package, \\pdfoutput=1 added")
