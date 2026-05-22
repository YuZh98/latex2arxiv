Feature: Generate a step-by-step arXiv upload guide
  As a paper author who has never used the arXiv upload form
  I want a copy-paste-ready walkthrough generated from my project
  So that I don't have to guess what to enter in each field

  Background:
    Given the `latex2arxiv` CLI is installed
    And a compilable LaTeX project zip "paper.zip"

  Scenario: --guide writes an upload guide alongside the output
    When I run `latex2arxiv paper.zip --guide`
    Then a plain-text file is written next to the output zip
    And its filename clearly identifies it as the upload guide

  Scenario: Guide contains extracted paper metadata
    Given the main .tex contains a `\title{...}`, `\author{...}`, and `\begin{abstract}` block
    When I run `latex2arxiv paper.zip --guide`
    Then the guide contains a "Title:" section with the extracted title
    And the guide contains an "Authors:" section with the extracted author list
    And the guide contains an "Abstract:" section with the extracted abstract

  Scenario: Guide includes a "Comments:" line with counts
    When I run `latex2arxiv paper.zip --compile --guide`
    Then the guide contains a "Comments:" section like "<N> pages, <F> figures, <T> tables"

  Scenario: Guide enumerates the numbered submission steps
    When I run `latex2arxiv paper.zip --guide`
    Then the guide contains numbered steps covering:
      | starting a new submission |
      | choosing a license        |
      | selecting a category      |
      | uploading files           |
      | checking processing       |
      | filling in metadata       |
      | preview and submit        |

  Scenario: Guide lists files in the cleaned zip
    When I run `latex2arxiv paper.zip --guide`
    Then the guide contains a "Files in your zip:" listing
    And the main .tex is annotated as "← main file"

  Scenario: --guide without --compile still works
    When I run `latex2arxiv paper.zip --guide`
    Then the guide is still generated using static project inspection
    And the page / figure / table counts may be omitted if not derivable

  Scenario: --guide combined with --dry-run writes nothing
    When I run `latex2arxiv paper.zip --guide --dry-run`
    Then no output zip is written
    And no guide file is written
