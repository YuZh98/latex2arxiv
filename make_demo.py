#!/usr/bin/env python3
"""Generate demo_project.zip for testing latex2arxiv converter."""
import struct
import zlib
import zipfile

files = {}

files['main.tex'] = r"""\documentclass[12pt]{article}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{todonotes} % draft only

% \input{unused_section.tex}

\title{Demo Paper}
\author{Author Name}
\date{}

\begin{document}
\maketitle

\section{Introduction}
This is the introduction. % TODO: expand this
\todo{Add more content here.}

See Figure~\ref{fig:example} for an illustration.

\begin{figure}[h]
  \centering
  \includegraphics[width=0.5\textwidth]{figures/example}
  \caption{An example figure.}
  \label{fig:example}
\end{figure}

\section{Method}
We propose a method~\cite{smith2020}.

\input{sections/results.tex}

\bibliographystyle{plain}
\bibliography{refs}

\end{document}
"""

files['sections/results.tex'] = r"""
\section{Results}
% This section summarizes results.
Our method achieves state-of-the-art performance.
\hl{Check these numbers before submission.}
"""

# Unused tex file — should be removed
files['sections/old_draft.tex'] = r"""
\section{Old Draft}
This section was removed.
"""

files['refs.bib'] = r"""@article{smith2020,
  author    = {Smith, John and Doe, Jane},
  title     = {A Great Method},
  journal   = {Journal of Examples},
  year      = {2020},
  volume    = {10},
  pages     = {1--10},
  doi       = {10.1234/example},
  abstract  = {This is a private abstract that should be removed.},
  file      = {smith2020.pdf},
}

@article{smith2020duplicate,
  author    = {Smith, John and Doe, Jane},
  title     = {A Great Method},
  journal   = {Journal of Examples},
  year      = {2020},
  doi       = {10.1234/example},
}
"""


def _make_png() -> bytes:
    """Create a minimal valid 1x1 white PNG."""
    def chunk(name, data):
        c = struct.pack('>I', len(data)) + name + data
        return c + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff'))
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
