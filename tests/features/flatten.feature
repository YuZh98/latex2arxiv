Feature: Inline included files into a single main .tex
  As a paper author who wants the simplest possible upload
  I want every \input / \include / \subfile inlined into the main .tex
  So that the submission is a single .tex file plus its assets

  # Canonical behavior: docs/flatten.md.

  Background:
    Given the `latex2arxiv` CLI is installed
    And a LaTeX project "paper.zip" whose "main.tex" contains
      `\input{sec/intro}`, `\include{sec/methods}`, and `\subfile{sec/appendix}`

  Scenario: --flatten produces a single .tex
    When I run `latex2arxiv paper.zip --flatten`
    Then the output zip contains exactly one .tex file at the root
    And that file is the inlined "main.tex"
    And the original fragment files (intro.tex, methods.tex, appendix.tex)
      are not in the output zip

  Scenario: Inlined output preserves figure references unchanged
    When I run `latex2arxiv paper.zip --flatten`
    Then `\includegraphics` paths in the inlined .tex still resolve relative
      to the new root
    And every referenced figure file is present in the output zip

  Scenario: --flatten + --json lists the inlined fragments
    When I run `latex2arxiv paper.zip --flatten --json`
    Then the JSON field `flatten` is `true`
    And the JSON field `inlined_files` is a non-empty list containing the
      paths of the fragment .tex files that were inlined

  Scenario: --flatten with no \input/\include/\subfile is a no-op
    Given the main .tex has no inclusion commands
    When I run `latex2arxiv paper.zip --flatten --json`
    Then the JSON field `flatten` is `true`
    And `inlined_files` is an empty list
    And the output zip is structurally equivalent to a non-flattened run

  Scenario: Commented-out \input is not inlined
    Given the main .tex contains a `% \input{old_section}` on a commented line
    When I run `latex2arxiv paper.zip --flatten`
    Then "old_section.tex" content does not appear in the inlined output
