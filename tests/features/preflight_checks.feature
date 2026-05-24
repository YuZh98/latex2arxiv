Feature: Catch arXiv submission blockers before upload
  As a paper author who has not submitted to arXiv before
  I want the tool to flag rejection-causing problems with severity
  So that I can fix them locally instead of finding out from arXiv after upload

  # Severity contract: `[error]` triggers exit code 1; `[warn]` is advisory and
  # does not affect exit code. See docs/pre-flight.md for the canonical table.

  Background:
    Given the `latex2arxiv` CLI is installed
    And a LaTeX project zip ready for inspection

  Scenario Outline: Shell-escape-only packages produce errors
    Given the main .tex contains `\usepackage{<pkg>}`
    When I run `latex2arxiv project.zip --dry-run`
    Then stdout contains a line starting with "[error]" mentioning "<pkg>"
    And the process exits with code 1

    Examples:
      | pkg          |
      | minted       |
      | pythontex    |
      | shellesc     |
      | auto-pst-pdf |
      | pst-pdf      |
      | svg          |
      | psfig        |

  @xfail_preflight_gap
  Scenario: Shipped psfig.sty file is rejected
    Given the input contains "psfig.sty" at any depth
    When I run `latex2arxiv project.zip --dry-run`
    Then a "[error]" mentions that arXiv forbids user-supplied psfig.sty
    And the process exits with code 1

  Scenario: fontspec / unicode-math require XeLaTeX hint
    Given the main .tex contains `\usepackage{fontspec}`
    And no "00README" with `compiler: xelatex` is shipped
    When I run `latex2arxiv project.zip --dry-run`
    Then an "[error]" mentions that XeLaTeX or LuaLaTeX is required
    And the process exits with code 1

  Scenario: fontspec accepted with a 00README compiler hint
    Given the main .tex contains `\usepackage{fontspec}`
    And a "00README" at the project root contains `compiler: xelatex`
    When I run `latex2arxiv project.zip --dry-run`
    Then no fontspec-related "[error]" is emitted

  Scenario: \tikzexternalize without pre-built figures is blocked
    Given the main .tex contains `\tikzexternalize`
    And no `*-figure*.pdf` files are present
    When I run `latex2arxiv project.zip --dry-run`
    Then an "[error]" instructs the user to externalize TikZ figures locally
    And the process exits with code 1

  Scenario: \bibliography reference with missing .bib and no .bbl
    Given the main .tex contains `\bibliography{refs}`
    And neither "refs.bib" nor any "*.bbl" file is in the project
    When I run `latex2arxiv project.zip --dry-run`
    Then an "[error]" notes the missing .bib without a fallback .bbl
    And the process exits with code 1

  Scenario: biblatex without shipped .bbl emits a warning
    Given the main .tex contains `\usepackage{biblatex}` or `\addbibresource{...}`
    And no `<main>.bbl` is shipped in the project
    When I run `latex2arxiv project.zip --dry-run`
    Then a "[warn]" recommends shipping the `.bbl` as a fallback
    And the process exits with code 0

  @xfail_preflight_gap
  Scenario: Main .tex not at the submission root
    Given the only file containing `\documentclass` is "src/main.tex"
    When I run `latex2arxiv project.zip --dry-run`
    Then a "[warn]" notes that arXiv compiles from root
    And the process exits with code 0

  Scenario Outline: print-index / glossary / nomenclature without index data
    Given the main .tex contains `<directive>`
    And the matching `<sidecar>` file is not shipped
    When I run `latex2arxiv project.zip --dry-run`
    Then a "[warn]" notes the section will silently disappear on arXiv

    Examples:
      | directive            | sidecar |
      | \printindex          | .ind    |
      | \printglossary       | .gls    |
      | \printnomenclature   | .nls    |

  Scenario: \today inside \date{} warns about rebuilt-PDF drift
    Given the main .tex contains `\date{\today}`
    When I run `latex2arxiv project.zip --dry-run`
    Then a "[warn]" notes that arXiv may rebuild the PDF and the date will change

  Scenario: Output zip exceeds 50 MB
    Given the cleaned output would exceed 50 megabytes
    When I run `latex2arxiv project.zip`
    Then a "[warn]" notes the size and recommends `--resize` or splitting
    And the process still exits with code 0 if no errors are present

  Scenario: .eps source under pdflatex mode (no compiler hint)
    Given the project contains "fig1.eps"
    And no "00README" specifies `compiler: latex`
    When I run `latex2arxiv project.zip --dry-run`
    Then a "[warn]" recommends converting .eps or switching compilers

  Scenario: Filename with spaces or non-ASCII characters
    Given the project contains a file named "my figure.pdf"
    When I run `latex2arxiv project.zip --dry-run`
    Then a "[warn]" notes that `\input`/`\includegraphics` resolution will break

  Scenario: \today + missing .bbl + oversized output coexist
    Given a project that triggers a \today warning, a biblatex .bbl warning, and an oversized-output warning at the same time
    When I run `latex2arxiv project.zip`
    Then all three "[warn]" lines are emitted independently
    And the process exits with code 0

  Scenario Outline: Additional advisory warnings from the canonical table
    Given the project condition "<condition>" holds
    When I run `latex2arxiv project.zip --dry-run`
    Then a "[warn]" mentioning "<topic>" is emitted
    And the process exits with code 0

    # Mirrors rows from docs/pre-flight.md not already covered above.
    Examples:
      | condition                                                 | topic                              |
      | main .tex contains `\usepackage{xr}` or `xr-hyper`         | external-document references break |
      | `\documentclass[referee]` or `[doublespace]` or `\doublespacing` | single-spaced submissions required |
      | main .tex contains `\includeonly{...}`                    | includeonly restricts compilation  |
      | a `\subfile`'d document contains `\bibliographystyle`     | duplicate bibliography command     |
      | `\input`/`\include`/`\includegraphics` uses an absolute path | build server can't resolve absolute paths |
      | the source tree contains `*-eps-converted-to.pdf` artifacts | eps→pdf artifacts in source        |
      | the output zip contains a dot-file or dot-directory       | arXiv deletes files starting with `.` |
      | a `.png` figure exceeds 34 megapixels                     | oversized PNG; consider `--resize` |
      | a `.tex` file is not valid UTF-8                          | re-save as UTF-8                   |
      | a filename or directory name contains non-ASCII characters | non-ASCII filename                 |
      | a directory name contains spaces                          | spaces in directory name           |
