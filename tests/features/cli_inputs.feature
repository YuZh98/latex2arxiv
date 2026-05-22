Feature: Accept LaTeX projects from any common input form
  As a paper author preparing an arXiv submission
  I want to point latex2arxiv at whatever I have on hand
  So that I don't have to reshape my project to fit the tool

  Background:
    Given the `latex2arxiv` CLI is installed and on PATH

  Scenario: Zip archive input
    Given a file "paper.zip" containing a compilable LaTeX project
    When I run `latex2arxiv paper.zip`
    Then a file "paper_arxiv.zip" is written next to the input
    And the original "paper.zip" is unchanged
    And the process exits with code 0

  Scenario: Directory input
    Given a directory "paper/" containing a compilable LaTeX project
    When I run `latex2arxiv paper/`
    Then a file "paper_arxiv.zip" is written in the current directory
    And the directory "paper/" is unchanged

  Scenario: Git URL input over https
    Given a public git repository at "https://github.com/u/p.git" containing a LaTeX project
    When I run `latex2arxiv https://github.com/u/p.git`
    Then the repository is cloned to a temp location with `--depth 1`
    And a file "p_arxiv.zip" is written in the current directory
    And the temp clone is removed before the process exits

  Scenario: Built-in demo
    When I run `latex2arxiv --demo`
    Then no input argument is required
    And the bundled demo project is processed
    And a file "demo_project_arxiv.zip" is written in the current directory

  Scenario: Explicit output path
    Given a file "paper.zip" containing a compilable LaTeX project
    When I run `latex2arxiv paper.zip out.zip`
    Then the cleaned output is written to "out.zip"
    And no file "paper_arxiv.zip" is created

  Scenario: Auto-detect main .tex via \documentclass
    Given a zip whose only file containing `\documentclass` is "main_v2.tex"
    When I run `latex2arxiv paper.zip`
    Then "main_v2.tex" is selected as the main file
    And the process exits with code 0

  Scenario: Explicit main file overrides auto-detection
    Given a zip with multiple files containing `\documentclass`
    When I run `latex2arxiv paper.zip --main JASA_main.tex`
    Then "JASA_main.tex" is used as the main file regardless of auto-detection

  Scenario: Missing input argument without --demo
    When I run `latex2arxiv` with no input and no `--demo`
    Then the process exits non-zero
    And stderr contains "the following arguments are required: input"

  Scenario: Nonexistent input path
    When I run `latex2arxiv does_not_exist.zip`
    Then the process exits non-zero
    And stderr explains that the input path was not found

  Scenario: --version prints the installed version and exits
    When I run `latex2arxiv --version`
    Then stdout contains "latex2arxiv " followed by a semver-shaped string
    And the process exits with code 0

  Scenario: Zip-slip protection — member path escapes extraction root
    Given a malicious "evil.zip" whose entries include "../escape.tex"
    When I run `latex2arxiv evil.zip`
    Then no file is written outside the extraction root
    And the process exits non-zero
    And stderr explains that extraction was refused due to an escaping path

  Scenario: Zip-bomb protection — uncompressed size exceeds the safety cap
    Given a "bomb.zip" whose total uncompressed size exceeds the safety cap
    When I run `latex2arxiv bomb.zip`
    Then no extraction occurs
    And the process exits non-zero
    And stderr explains that extraction was refused due to the size cap
