# Pre-flight check reference

Before producing the output zip, latex2arxiv validates the project against [arXiv's LaTeX submission guide](https://info.arxiv.org/help/submit_tex.html). `[error]` lines block submission (the tool exits non-zero); `[warn]` lines are advisory.

## Checks

| Severity | Trigger | Why it matters |
|---|---|---|
| 🛑 error | `\usepackage{minted}` / `pythontex` / `shellesc` | Require `--shell-escape`; arXiv compiles without it. |
| 🛑 error | `\usepackage{psfig}` | arXiv no longer supports the psfig package. |
| 🛑 error | `\usepackage{fontspec}` / `unicode-math` | Require XeLaTeX or LuaLaTeX; arXiv defaults to pdfLaTeX. |
| ⚠️ warn | `\usepackage{xr}` or `xr-hyper` | File paths/locations differ on arXiv; external-document references break. |
| ⚠️ warn | Main `.tex` not at the submission root | arXiv compiles from root; subdirectory main files aren't found. |
| ⚠️ warn | `\printindex` / `\printglossary` / `\printnomenclature` without matching `.ind` / `.gls` / `.nls` | arXiv doesn't run makeindex or glossary processors; the printed section silently disappears. |
| ⚠️ warn | `\usepackage{biblatex}` (or `\addbibresource`) without `<main>.bbl` shipped | If arXiv can't resolve any `.bib` file, your submission is blocked. |
| ⚠️ warn | `\documentclass[referee]` / `[doublespace]` / `\doublespacing` | arXiv requires single-spaced submissions. |
| ⚠️ warn | `\today` inside `\date{...}` | arXiv may rebuild the PDF; the date will change. |
| ⚠️ warn | `\subfile`'d document containing `\bibliographystyle` | Likely a standalone supplement; remove the `\subfile` line to avoid duplicate bibliography commands. |
| ⚠️ warn | `.eps` images shipped | `pdflatex` doesn't support `.eps`; convert to `.pdf` or `.png`. |
| ⚠️ warn | Custom `.cls` / `.sty` files | Verify they aren't already provided by TeX Live. |
| ⚠️ warn | Filename has spaces or non-ASCII characters | Breaks `\input` and `\includegraphics` resolution. |
| ⚠️ warn | Output `.zip` larger than 50 MB | arXiv has size limits; consider `--resize` or splitting supplementary materials. |

## Silent fixes

In addition to surfacing issues, the conversion silently fixes common pitfalls:

- Inserts `\pdfoutput=1` (or normalizes any `\pdfoutput=N`) in the main `.tex`, so arXiv selects pdfLaTeX.
- Preserves `00README` / `00README.XXX` files at root for arXiv processor hints.
- Strips comments and standard draft annotations (`\todo`, `\hl`, ...) and packages (`todonotes`, `comment`, ...).
