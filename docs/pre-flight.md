# Pre-flight check reference

Before producing the output zip, latex2arxiv validates the project against [arXiv's LaTeX submission guide](https://info.arxiv.org/help/submit_tex.html). `[error]` lines block submission (the tool exits non-zero); `[warn]` lines are advisory.

## Checks

| Severity | Trigger | Why it matters |
|---|---|---|
| 🛑 error | `\usepackage{minted}` / `pythontex` / `shellesc` | Require `--shell-escape`; arXiv compiles without it. |
| 🛑 error | `\usepackage{auto-pst-pdf}` / `pst-pdf` | Require `--shell-escape` to convert PostScript figures; arXiv compiles without it. |
| 🛑 error | `\usepackage{svg}` | Shells out to Inkscape; arXiv does not provide it. Convert `.svg` to `.pdf` or `.png`. |
| 🛑 error | `\usepackage{psfig}` | arXiv no longer supports the psfig package. |
| 🛑 error | Shipped `psfig.sty` in submission | arXiv forbids user-supplied `psfig.sty`; it will cause the build to fail. |
| 🛑 error | `\usepackage{fontspec}` / `unicode-math` | Require XeLaTeX or LuaLaTeX; arXiv defaults to pdfLaTeX. Ship a `00README` with `compiler: xelatex` (or legacy `00README.XXX` with `nohypertex,xelatex`). |
| 🛑 error | `\tikzexternalize` without pre-built `*-figure*.pdf` | arXiv can't run shell-escape to externalize TikZ figures; build them locally first. |
| 🛑 error | `\bibliography{foo}` but `foo.bib` missing and no `.bbl` shipped | arXiv will block the submission if referenced `.bib` files are missing and no pre-built `.bbl` is provided. |
| ⚠️ warn | `\usepackage{xr}` or `xr-hyper` | File paths/locations differ on arXiv; external-document references break. |
| ⚠️ warn | Main `.tex` not at the submission root | arXiv compiles from root; subdirectory main files aren't found. |
| ⚠️ warn | `\printindex` / `\printglossary` / `\printnomenclature` without matching `.ind` / `.gls` / `.nls` | arXiv doesn't run makeindex or glossary processors; the printed section silently disappears. |
| ⚠️ warn | `\usepackage{biblatex}` (or `\addbibresource`) without `<main>.bbl` shipped | arXiv can run Biber natively (since late 2025), but biblatex/Biber version mismatches (currently TL2025, bbl format 3.3) may break the bibliography; ship the `.bbl` as a fallback. |
| ⚠️ warn | `\documentclass[referee]` / `[doublespace]` / `\doublespacing` | arXiv requires single-spaced submissions. |
| ⚠️ warn | `\today` inside `\date{...}` | arXiv may rebuild the PDF; the date will change. |
| ⚠️ warn | `\includeonly` detected | Restricts which chapters arXiv compiles; remove it so the full paper appears. |
| ⚠️ warn | `\subfile`'d document containing `\bibliographystyle` | Likely a standalone supplement; remove the `\subfile` line to avoid duplicate bibliography commands. |
| ⚠️ warn | Absolute path in `\input` / `\include` / `\includegraphics` | Build server can't resolve `/abs/...` or `C:\...`; use a path relative to the submission root. |
| ⚠️ warn | `-eps-converted-to.pdf` artifacts in source | arXiv does not perform on-the-fly eps→pdf conversion; convert figures yourself and update `\includegraphics` paths. |
| ⚠️ warn | `.eps` images shipped (pdflatex mode) | `pdflatex` doesn't support `.eps`; convert to `.pdf` or `.png`, or use `latex+dvips` via `00README`. Suppressed when `00README` specifies `compiler: latex`. |
| ⚠️ warn | Hidden files (dot-files/directories) in output | arXiv deletes files starting with `.` upon announcement; if your build depends on them, rename. |
| ⚠️ warn | PNG image exceeds 34 megapixels | arXiv flags oversized PNGs (since Feb 2026); consider `--resize` to downscale. |
| ⚠️ warn | `.tex` source not valid UTF-8 | Re-save as UTF-8 to avoid corrupted accented/special characters. |
| ⚠️ warn | Filename or directory name has spaces or non-ASCII characters | Breaks `\input` and `\includegraphics` resolution. |
| ⚠️ warn | Output `.zip` larger than 50 MB | arXiv has size limits; consider `--resize` or splitting supplementary materials. |
| ⚠️ warn | Uncompressed project larger than 50 MB | arXiv soft limit for source size; consider `--resize` or splitting supplementary materials. |

## Silent fixes

In addition to surfacing issues, the conversion silently fixes common pitfalls:

- Inserts `\pdfoutput=1` (or normalizes any `\pdfoutput=N`) in the main `.tex`, so arXiv selects pdfLaTeX.
- Preserves `00README` / `00README.XXX` files at root for arXiv processor hints.
- Strips comments and standard draft annotations (`\todo`, `\hl`, ...) and packages (`todonotes`, `comment`, ...).
