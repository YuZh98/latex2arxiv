Feature: Compile the cleaned output and open the resulting PDF
  As a paper author about to upload to arXiv
  I want the tool to compile the cleaned project locally and show me the PDF
  So that I can visually confirm the output matches my source before uploading

  Background:
    Given the `latex2arxiv` CLI is installed
    And `pdflatex` is available on PATH

  Scenario: --compile produces a PDF and opens it
    Given a compilable LaTeX project "paper.zip"
    When I run `latex2arxiv paper.zip --compile`
    Then the cleaned output zip is written
    And `pdflatex` is invoked on the cleaned main .tex
    And a PDF file is produced alongside the output
    And the platform's default PDF viewer is launched on that PDF
    And the process exits with code 0

  Scenario: --compile reports pdflatex failure on stdout but does not flip exit code
    Given a LaTeX project whose main .tex contains an unrecoverable syntax error
    When I run `latex2arxiv paper.zip --compile`
    Then the cleaned output zip is still written
    And stdout surfaces the `pdflatex` failure with a "[compile] pdflatex errors:" tail
    # The compile failure alone does not flip the exit code; the process exits
    # 0 unless a separate pre-flight error is present.

  Scenario: --compile is skipped if pdflatex is not on PATH
    Given `pdflatex` is not installed
    When I run `latex2arxiv paper.zip --compile`
    Then stdout clearly states that `pdflatex` was not found with install hints
    And the cleaned output zip is still written for later use
    # The missing-pdflatex case does not by itself flip the exit code; the
    # process exits 0 unless a separate pre-flight error is present.

  Scenario: --compile + pre-flight error
    Given the project triggers a `[error]` (e.g. `\usepackage{minted}`)
    When I run `latex2arxiv paper.zip --compile`
    Then the pre-flight error is reported on stdout
    And the process exits with code 1
    # --compile is not gated by pre-flight errors; pdflatex still runs and may
    # emit its own diagnostics. The non-zero exit comes from the pre-flight
    # error, not from --compile.
