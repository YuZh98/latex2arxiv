# Assumption Audit — 2026-05-17

Investigator: Task 1 of converter.py refactor (baseline anchor).
Worktree: .claude/worktrees/refactor+baseline-anchor (off main @ 3dd26c2).
Python: evidence gathered with Python 3.12 (matches CI coverage-run pin).
Tool path: /tmp/refactor-venv-312/bin/latex2arxiv (pip install -e . of the worktree).
Verified the venv resolves to the worktree converter via
  `python3 -c "import converter; print(converter.__file__)"`
  -> /Users/zhengyu/Desktop/Claude/Project/latex2arxiv/.claude/worktrees/refactor+baseline-anchor/converter.py

---

## A1 — Zip Output Determinism

Result: BYTES_DRIFT_CONTENT_STABLE

Procedure: ran the same fixture through `latex2arxiv` twice (no --dry-run, since
--dry-run skips the ZipFile write at converter.py:664-665 and never produces an
output file). Slept 2s between runs to maximize mtime drift. Verified on 2 of
the 10 fixtures — once on the trivial 01-minimal (single-member edge case),
once on the multi-file 10-multifile-graphicspath (3 members across nested
dirs). Not swept across all 10 fixtures; the mechanism (mtime carried via
`ZipFile.write(path)` from each on-disk staged file) is the same for every
fixture, so the generalization should hold, but this is the empirical scope.

### Evidence — fixture 01-minimal (single member)

Byte-level sha256:
  25c6fd2632e0eeba07cdc71d557fdeb104db33d95c5fc59ae11c39ca903f70f2  /tmp/out1.zip
  24da72c302d2fde864f84d455c589831c263cfcf54e59bf6f919fde6004fc899  /tmp/out2.zip
=> BYTES DIFFER.

Member ordering: identical
  out1.zip namelist: ['main.tex']
  out2.zip namelist: ['main.tex']

Per-member content sha256: identical
  out1.zip main.tex content_sha256=50e1826bf3347f74d0bdd6697a1ab22ccf47d3b3eec2c45345efdb7225fe95ea
  out2.zip main.tex content_sha256=50e1826bf3347f74d0bdd6697a1ab22ccf47d3b3eec2c45345efdb7225fe95ea

ZipInfo.date_time delta: +2 seconds (exactly the sleep gap)
  out1.zip main.tex date_time=(2026, 5, 17, 13, 15, 30)
  out2.zip main.tex date_time=(2026, 5, 17, 13, 15, 32)

### Evidence — fixture 10-multifile-graphicspath (3 members)

Byte-level sha256:
  65fae66cb7bd72955ffafa85585d96664320af527263ff6c8d80d7cc2a0f6ccc  /tmp/out_a.zip
  f10568e810ef76f8f5920184ddbd54903923c2e967f7842c002808482a42ae75  /tmp/out_b.zip
=> BYTES DIFFER.

Per-member content sha256 (first 16 hex):
  out_a.zip  figures/fig1.pdf     dt=(2026,5,17,13,15,48)  c=9bc957703ac9aeb2
  out_b.zip  figures/fig1.pdf     dt=(2026,5,17,13,15,50)  c=9bc957703ac9aeb2
  out_a.zip  main.tex             dt=(2026,5,17,13,15,48)  c=2d60f25b5cb3ac95
  out_b.zip  main.tex             dt=(2026,5,17,13,15,50)  c=2d60f25b5cb3ac95
  out_a.zip  sections/intro.tex   dt=(2026,5,17,13,15,48)  c=333dca9835f0b944
  out_b.zip  sections/intro.tex   dt=(2026,5,17,13,15,50)  c=333dca9835f0b944

Member ordering: identical across both runs (figures/fig1.pdf, main.tex,
sections/intro.tex).

### Conclusion

The zip's central directory carries `ZipInfo.date_time` from the source files'
on-disk mtimes (latex2arxiv writes via `ZipFile.write(path)` rather than
`writestr`, so each member inherits the OS mtime of the staged file at write
time). Re-running re-stages files into the tempdir → new mtimes → different
zip bytes, but identical member names, ordering, and content.

Decision: Detector D will hash MEMBER CONTENTS ONLY (sorted by member name)
and ignore ZipInfo.date_time / ZipInfo.create_system / extra-fields. Approach:

    import zipfile, hashlib
    def zip_content_digest(p):
        h = hashlib.sha256()
        with zipfile.ZipFile(p) as zf:
            for name in sorted(zf.namelist()):
                h.update(name.encode("utf-8"))
                h.update(b"\0")
                h.update(zf.read(name))
                h.update(b"\0")
        return h.hexdigest()

This is robust against the observed drift and still catches: missing/added
members, renamed members, content changes, and silent reordering (because
member name is part of the hash).

NOT BLOCKED. Refactor may proceed using content-hash baselines.

---

## A2 — Fixture Issue-Type Matrix

Scope of this audit: the 4 helper functions named in the task —
`_check_compliance` (L151), `_check_files` (L315), `_check_output_size`
(L362), `_check_uncompressed_size` (L372). A separate inline scan of the
`convert()` body found 3 more `issues.warn(...)` call sites that the refactor
will also move (L492, L636, L644); these are listed in the "Convert()-internal
emitters" section below and are also GAPs.

Observed (severity, message-prefix) pairs across all 10 fixtures (N = 11):

  errors    \usepackage{fontspec} requires XeLaTeX or LuaLaTeX           07-fontspec-xelatex
  errors    \usepackage{minted} requires shell-escape                    05-pre-flight-warnings
  errors    \usepackage{psfig}                                           05-pre-flight-warnings
  errors    \usepackage{unicode-math} requires XeLaTeX or LuaLaTeX       07-fontspec-xelatex
  warnings  .eps image found:                                            05-pre-flight-warnings
  warnings  'referee' or 'doublespace' option detected in \documentclass 05-pre-flight-warnings
  warnings  \printglossary used but no                                   05-pre-flight-warnings
  warnings  \printindex used but no                                      05-pre-flight-warnings
  warnings  \today used in \date — arXiv may rebuild the PDF             05-pre-flight-warnings
  warnings  \usepackage{xr} detected — file paths/locations differ       05-pre-flight-warnings
  warnings  biblatex detected but no main                                02-biblatex-biber

Fixtures emitting any issues: 02-biblatex-biber, 05-pre-flight-warnings,
07-fontspec-xelatex. Fixtures clean (0 issues): 01, 03, 04, 06, 08, 09, 10.

### Emitter audit (every issues.warn / issues.error in pre-flight functions)

Format: <file:line> [sev]  description  -> coverage marker

converter.py:162  [warn]   _check_compliance: 'referee'/'doublespace' \documentclass option
                  -> COVERED by 05 (matches "'referee' or 'doublespace' option")

converter.py:166  [warn]   _check_compliance: \doublespacing / \setstretch{2-9} commands
                  -> GAP. No fixture has either command. Same severity/category as
                     L162 but a separate detector trigger; an L162-only fixture
                     does not exercise this branch.

converter.py:170  [warn]   _check_compliance: \today inside \date{...}
                  -> COVERED by 05

converter.py:174  [warn]   _check_compliance: .eps image files (per-file, in rglob)
                  -> COVERED by 05 (photo.eps)

converter.py:188  [warn]   _check_compliance: \subfile{...} that contains \bibliographystyle
                  -> GAP. 09-flatten-subfile is the only fixture using \subfile,
                     and that subfile does not contain \bibliographystyle.

converter.py:203  [error]  _check_compliance: shell-escape pkgs (per _SHELL_ESCAPE_PKGS,
                            currently {"minted", "pst-pdf", "auto-pst-pdf"})
                  -> COVERED by 05 for minted only. Other names (pst-pdf,
                     auto-pst-pdf) and any future additions to _SHELL_ESCAPE_PKGS
                     are not separately exercised, but the emitter code path is
                     exercised so a regression in the iteration / dedup logic
                     would be caught.

converter.py:210  [error]  _check_compliance: \usepackage{svg}
                  -> GAP. No fixture loads `svg`.

converter.py:218  [error]  _check_compliance: \usepackage{psfig}
                  -> COVERED by 05

converter.py:228  [error]  _check_compliance: fontspec / unicode-math (per-package)
                  -> COVERED by 07 (both packages)

converter.py:239  [warn]   _check_compliance: \usepackage{xr} or \usepackage{xr-hyper}
                  -> COVERED by 05 (xr). xr-hyper alternative regex branch is
                     not separately exercised; minor sub-gap.

converter.py:248  [warn]   _check_compliance: main.tex not at submission root
                  -> GAP. All 10 fixtures put main.tex at the fixture root.

converter.py:257  [warn]   _check_compliance: \printindex without root-level .ind
                  -> COVERED by 05

converter.py:263  [warn]   _check_compliance: \printglossary / \printglossaries without .gls
                  -> COVERED by 05

converter.py:269  [warn]   _check_compliance: \printnomenclature without root-level .nls
                  -> GAP. No fixture uses \printnomenclature.

converter.py:284  [warn]   _check_compliance: biblatex / \addbibresource without pre-built .bbl
                  -> COVERED by 02-biblatex-biber

converter.py:296  [error]  _check_compliance: \tikzexternalize without pre-built *-figure*.pdf
                  -> GAP. No fixture uses \tikzexternalize.

converter.py:308  [warn]   _check_compliance: absolute path in \input / \include /
                            \includegraphics (Unix `/` or Windows `C:\`)
                  -> GAP. No fixture exercises an absolute path argument.

converter.py:334  [warn]   _check_files: directory name contains spaces
                  -> GAP. No fixture ships a directory with a space in its name.

converter.py:342  [warn]   _check_files: directory name contains non-ASCII chars
                  -> GAP. No fixture ships a directory with non-ASCII name.

converter.py:351  [warn]   _check_files: filename contains spaces
                  -> GAP. No fixture ships a file with a space in its name.

converter.py:357  [warn]   _check_files: filename contains non-ASCII chars
                  -> GAP. No fixture ships a file with a non-ASCII filename.

converter.py:366  [warn]   _check_output_size: compressed zip > SIZE_WARN_MB
                  -> GAP, AND UNREACHABLE VIA DETECTOR C. `_check_output_size`
                     is called at converter.py:676, AFTER the dry-run early-
                     return at L664-669, so it never runs in dry-run JSON
                     mode. Even a >10 MB fixture would not exercise this via
                     Detector C. A monkeypatched unit test is the only way to
                     cover this emitter.

converter.py:381  [warn]   _check_uncompressed_size: total kept files > SIZE_WARN_MB
                  -> GAP. `_check_uncompressed_size` IS called BEFORE the
                     dry-run early-return (at converter.py:602), so it is
                     reachable in dry-run — a >10 MB fixture would in fact
                     trigger it. But shipping bulky test inputs is impractical;
                     a monkeypatched unit test (SIZE_WARN_MB -> 0.001) is the
                     pragmatic option, same as for L366.

Summary: 23 in-scope emitters total. 10 covered (one with caveat that only
one of several alternations is exercised — L203 minted-only, L239 xr-only).
13 gaps, of which 11 are reasonably fixable with small TeX/file fixtures and
2 are size-threshold checks (L366 unreachable from dry-run; L381 reachable
but impractical).

### Convert()-internal emitters (out of the 4-helper scope but moved by the refactor)

converter.py:492  [warn]   convert(): tex file not valid UTF-8
                  -> GAP. No fixture ships a non-UTF-8 .tex.

converter.py:636  [warn]   convert(): undefined citation keys
                  -> GAP. No fixture has \cite{} keys missing from its .bib/.bbl.

converter.py:644  [warn]   convert(): kept .cls / .sty file (advisory)
                  -> GAP. No fixture ships a custom .cls or .sty.

Including these: 26 emitters total across the pre-flight + compile/resolve
extract surface, 10 covered, 16 GAP. The "10/23" headline above counts only
the 4 helpers the task named; the controller should plan baseline coverage
against the wider 26-emitter surface if Task 2/3 will also exercise the
extracted compile/resolve modules.

### Gaps requiring new fixtures (or an explicit accept-coverage decision)

Practical to add as small fixtures (recommend a single new fixture
"11-pre-flight-warnings-extra" carrying as many of these as compatible —
several are mutually compatible in one .tex tree):

  G1.  L166  warn   \doublespacing / \setstretch{2.0}
  G2.  L188  warn   \subfile{} containing \bibliographystyle
  G3.  L210  error  \usepackage{svg}
  G4.  L248  warn   main.tex placed in subdirectory of input
                    (-> would require a fixture whose `--main` points to e.g.
                     `paper/main.tex` while the input root is the parent)
  G5.  L269  warn   \printnomenclature without .nls
  G6.  L296  error  \tikzexternalize without *-figure*.pdf
  G7.  L308  warn   absolute path in \input / \includegraphics
                    (e.g. \input{/tmp/foo} or \includegraphics{C:/tmp/img})
  G8.  L334  warn   directory name containing a space
  G9.  L342  warn   directory name with non-ASCII chars
  G10. L351  warn   filename containing a space
  G11. L357  warn   filename with non-ASCII chars

Sub-gaps (alternation branches not separately exercised; same emitter is
covered by another input, so regression risk is lower):

  S1.  L203  error  Non-minted shell-escape pkgs (pst-pdf, auto-pst-pdf) —
                    iteration covered, second-element split not exercised.
  S2.  L239  warn   xr-hyper variant (xr is covered).

Impractical to add as routine fixtures (would require multi-MB binaries):

  X1.  L366  warn   compressed output > SIZE_WARN_MB (10 MB).
                    UNREACHABLE from dry-run anyway — `_check_output_size` is
                    called after the dry-run early-return. A monkeypatched
                    unit test is the ONLY option (not just the better option).
  X2.  L381  warn   uncompressed total > SIZE_WARN_MB. Reachable from dry-run,
                    but a multi-MB fixture is impractical; monkeypatched unit
                    test recommended.

Convert()-internal emitters (also need new fixtures or unit tests):

  C1.  L492  warn   convert(): non-UTF-8 .tex file (ship a Latin-1 .tex).
  C2.  L636  warn   convert(): undefined citation keys (ship a .tex with
                    \cite{nonexistent} and a .bib lacking that key).
  C3.  L644  warn   convert(): custom .cls/.sty file kept (ship any .cls
                    or .sty in the project root).

### Recommendation to controller

The 11 G-gaps + 3 C-gaps mean Detector C (issues-list baseline) cannot
regression-catch a behavior change in 16 of 26 emitter sites across the
pre-flight + compile/resolve extract surface. Two options for Task 2/3:

  Option A — Plug the gaps first.
    Add 1–2 new fixtures covering G1–G11 before generating the baseline.
    Cost: ~1 small TeX tree + a couple of pathological-name files.
    Benefit: Detector C catches a regression in any preflight check, not just
    the 10 currently covered.

  Option B — Accept the coverage hole; baseline what we have.
    Generate baselines now from the 10 existing fixtures. Detector D
    (zip-content hash) still catches output drift on the existing fixtures,
    and Detector C catches drift in the 10 covered emitters. The 13 uncovered
    emitters rely on code-level review during the extract.
    Cost: blind spot for 13 emitters during the refactor.
    Benefit: unblocks Task 2/3 immediately.

Recommendation: Option A is cheap and removes a structural blind spot exactly
where the refactor is most likely to introduce a regression (pre-flight is
what's being extracted). Suggest adding fixture `11-pre-flight-extras` for
G1, G2, G3, G5, G6, G7 (all .tex-only, can coexist) plus fixture
`12-pathological-names` for G8–G11. G4 (subdirectory main.tex) needs its own
fixture because it changes the input root semantics. X1/X2 covered by a
monkeypatched unit test.

---

## A4 — CI Python Pin

Decision: pin baseline test to Python 3.12 (matches existing coverage-run pin
in .github/workflows/test.yml). Evidence in this report was gathered on
Python 3.12 from /opt/homebrew/bin/python3.12 via a dedicated venv at
/tmp/refactor-venv-312, so the determinism finding above is on the pinned
baseline version, not the system default.

---

## Status

DONE_WITH_CONCERNS

Concerns (for controller decision before Task 2/3):
  1. 13 of 23 pre-flight emitter call sites in the 4 named helpers are not
     exercised by any of the 10 existing fixtures. See "Gaps requiring new
     fixtures" above for the two options (plug now vs. accept and ship).
  2. 3 additional emitter sites inside `convert()` itself (L492, L636, L644)
     are also extracted by the refactor and are also GAPs. Bringing the
     total surface to 26 emitters with 10 covered / 16 uncovered.
  3. Two emitter alternations (shell-escape pkg list iteration, xr-hyper
     variant) are partially covered — same emitter code path exercised by
     a sibling input, lower priority than the G-gaps.
  4. L366 (`_check_output_size`) is UNREACHABLE from dry-run because it is
     called after the dry-run early-return. Detector C cannot ever cover it.
     A monkeypatched unit test is mandatory, not optional.
  5. L381 (`_check_uncompressed_size`) is reachable from dry-run but only
     with a >10 MB fixture; monkeypatched unit test recommended for the same
     pragmatic reason.

Not blocking. Detector D design is settled (content-hash, not byte-hash).
