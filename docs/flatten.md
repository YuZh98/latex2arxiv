# `--flatten` — single-file output

`--flatten` inlines every `\input`, `\include`, and `\subfile` reference
reachable from the main `.tex` so the output zip contains a single source
`.tex` file (the zip still includes images, `.bib`, `.bbl`, and any
required class/style files). Use it when an arXiv reviewer or template
expects a single self-contained source.

```bash
latex2arxiv paper.zip --flatten
latex2arxiv paper.zip --flatten --dry-run         # preview
latex2arxiv paper.zip --flatten --json | jq .     # see inlined_files
```

## Behaviour

| Construct | Inlining rule |
|---|---|
| `\input{x}` | Resolve `x` (or `x.tex`) relative to project root; inline its raw content. |
| `\include{x}` | Same path resolution; inlined body is wrapped in `\clearpage` on both sides to preserve page-break semantics. |
| `\subfile{x}` | Resolve relative to the **including** file's own directory; strip the subfile's preamble and `\begin{document}` / `\end{document}` wrapper before inlining. |
| `\input{x.bib}` | Left alone (non-`.tex` extension). |
| `% \input{x}` (commented) | Left alone — no inlining, no missing-file warning. |

After flatten, the fragment files (`x.tex`, etc.) are pruned from the
output zip by the same loop that drops `.aux`, `.log`, and other build
artefacts.

## The `\clearpage` decision

`\include{x}` in vanilla LaTeX is defined as `\clearpage` + `\input{x}` +
`\clearpage`. We emit literal `\clearpage` lines around each inlined
`\include` body so the post-flatten PDF is byte-identical (or near-so)
to the pre-flatten PDF. Authors using `\include` for one-chapter-per-page
layouts get what they expect.

If this is undesirable (e.g., you want continuous flow after flatten),
edit the flattened `main.tex` and remove the `\clearpage` markers
manually — they're plainly visible in the output.

## Errors and warnings

| Trigger | Output |
|---|---|
| Referenced file missing on disk | `[warn]` — original `\input{...}` left in place. |
| Cycle (A inputs B inputs A) | `[warn]` — recursive reference left in place; no infinite loop. A file referenced from multiple non-recursive locations is re-inlined each time. |
| `\input{x}` where `x` has its own `\documentclass` | `[error]` — refuses to inline (would corrupt the preamble); use `\subfile` instead or remove the inner preamble. |
| Subfile missing `\begin{document}` / `\end{document}` | `[warn]` — raw content inlined as a fallback. |

## Known limitations (v1)

- **Conditional blocks are not parsed.** `\iffalse \input{draft} \fi`
  will still inline `draft.tex`. If you use conditional includes as a
  toggle, expand or remove them before flattening.
- **No verbatim awareness.** A `\verb|\input{x}|` inside the source
  could in principle be matched by the include detector; in practice
  this is rare. Flag it as a follow-up if you hit it.
- **`\\%` comment-detection edge case.** The comment scanner treats
  `\%` as an escaped percent (correct) but does not handle `\\%`
  (LaTeX line-break followed by a comment) — a `\input{x}` further
  along the same line after a `\\%` would be seen as live. Rare in
  practice; put `\input` commands on their own line.
- **Multi-line `\input{...}`** with the closing brace on a different
  line from `\input` is not detected — the regex requires the
  command and its argument on the same source line. Almost never
  written this way; keep them on one line.
- **Bibliography paths are not rewritten.** A subfile that references
  `\bibliography{../refs}` keeps that path verbatim after flatten,
  which may break if the subfile sat in a subdirectory. Move
  `\bibliography{...}` to the main file before flattening if needed.
- **Image paths from subdirectory subfiles are not rewritten.** A
  subfile in `chapters/` doing `\includegraphics{fig}` resolves to
  `chapters/fig.png` pre-flatten. After flatten the bare
  `\includegraphics{fig}` text lands in the merged main file at the
  project root; the image file is retained in the output zip (the
  pruner matches by basename) but `pdflatex` then looks in the root
  and fails to find it. Workaround: add `\graphicspath{{chapters/}}`
  to the main file before flattening, or move the images to the
  project root.
- **No source-map.** A `pdflatex` error after flatten points at a line
  in the merged `main.tex`, not the original fragment file. The
  `\clearpage` markers help locate the right `\include` block.

## Combining flags

- `--flatten --dry-run`: preview the inlining and the kept/removed
  file sets without writing the output zip.
- `--flatten --json`: machine-readable summary including
  `"flatten": true` and `"inlined_files": ["chap1.tex", "..."]`.
- `--flatten --compile`: flatten first, then `pdflatex` the merged
  file. Useful for validating the flattened source compiles
  identically.
