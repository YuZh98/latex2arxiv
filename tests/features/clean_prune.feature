Feature: Prune the project and clean the .tex sources
  As a paper author whose project has accumulated draft files, build artifacts,
  and stale notes
  I want one command to produce a submission-shaped tree
  So that I don't have to hand-curate what goes to arXiv

  Background:
    Given a LaTeX project zip containing a main "main.tex" plus build artifacts, unused figures, backup files, and inline draft annotations
    And the original input archive is never modified by the tool

  Scenario: Keep only files reachable from the main .tex
    When I run `latex2arxiv project.zip`
    Then the output zip contains "main.tex" and every file it transitively references via `\input`, `\include`, `\subfile`, `\includegraphics`, `\graphicspath`, and `\bibliography`
    And files not reachable from the main .tex are dropped

  Scenario: Remove build artifacts and editor leftovers
    Given the input contains "main.aux", "main.log", "main.out", "main.pdf", "main.bbl", ".DS_Store", "Thumbs.db", and "__pycache__/cache.pyc"
    When I run `latex2arxiv project.zip`
    Then none of those artifacts appear in the output zip

  Scenario: Strip line and block comments from .tex sources
    Given "main.tex" contains both `% line comments` and stretches of code preceded by an unescaped percent
    When I run `latex2arxiv project.zip`
    Then the cleaned "main.tex" in the output has those comments removed
    And `\%` (escaped percent) is preserved verbatim

  Scenario Outline: Remove built-in draft annotations with their content
    Given "main.tex" contains a `<command>{...}` invocation
    When I run `latex2arxiv project.zip`
    Then the entire `<command>{...}` (including nested braces) is removed from the cleaned "main.tex"

    # Built-in default annotation set; revision-tracking commands like
    # \added, \deleted, \textcolor{red} are not built-in — they are added
    # via --config (see custom_config.feature).
    Examples:
      | command   |
      | \todo     |
      | \hl       |
      | \note     |
      | \fixme    |

  Scenario: Nested braces inside removed commands are handled
    Given "main.tex" contains `\todo{see \cite{x}}`
    When I run `latex2arxiv project.zip`
    Then the whole `\todo{see \cite{x}}` block is removed
    And no dangling `}` is left behind

  Scenario Outline: Remove built-in draft packages
    Given the main .tex contains `\usepackage{<pkg>}`
    When I run `latex2arxiv project.zip`
    Then `\usepackage{<pkg>}` is removed from the cleaned main .tex

    Examples:
      | pkg            |
      | todonotes      |
      | changes        |
      | trackchanges   |
      | easy-todo      |
      | comment        |

  Scenario: Commented-out commands are ignored by dependency tracking
    Given "main.tex" contains `% \input{old_section.tex}` on a commented line
    And the file "old_section.tex" exists in the input
    When I run `latex2arxiv project.zip`
    Then "old_section.tex" is treated as unreferenced and dropped from the output

  Scenario: Silent fix — inject \pdfoutput=1
    Given the input "main.tex" does not declare `\pdfoutput`
    When I run `latex2arxiv project.zip`
    Then the cleaned "main.tex" includes `\pdfoutput=1` so arXiv selects pdfLaTeX

  Scenario: Silent fix — normalize an existing \pdfoutput
    Given the input "main.tex" contains `\pdfoutput=0`
    When I run `latex2arxiv project.zip`
    Then the cleaned "main.tex" contains `\pdfoutput=1`

  Scenario: Preserve 00README hints for arXiv processor
    Given the input contains a "00README" file at the project root
    When I run `latex2arxiv project.zip`
    Then the "00README" file is kept verbatim in the output zip
