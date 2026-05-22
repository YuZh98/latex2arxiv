Feature: Downscale large raster images to fit arXiv soft limits
  As a paper author whose figures came out of a high-DPI export
  I want a one-flag way to shrink images that would balloon the submission
  So that I can stay under arXiv's size and pixel limits without manual editing

  Background:
    Given the `latex2arxiv` CLI is installed
    And `Pillow` is available in the environment
    And a LaTeX project zip "paper.zip" containing raster figures

  Scenario: --resize PX caps the longest side at PX pixels
    Given a figure "big.png" is 8000x6000 pixels
    When I run `latex2arxiv paper.zip --resize 1600`
    Then "big.png" in the output zip has a longest side equal to 1600 pixels
    And the aspect ratio of "big.png" is preserved

  Scenario: --resize without a value uses the project default
    When I run `latex2arxiv paper.zip --resize`
    Then images are resized to the project's `DEFAULT_MAX_PX` value
    And the process exits with code 0

  Scenario: Small images are not upscaled
    Given a figure "small.png" is 800x600 pixels
    When I run `latex2arxiv paper.zip --resize 1600`
    Then "small.png" in the output zip is still 800x600 pixels

  Scenario: PDF figures are not resampled
    Given a vector figure "diagram.pdf"
    When I run `latex2arxiv paper.zip --resize 1600`
    Then "diagram.pdf" is copied verbatim into the output zip

  Scenario: --resize without Pillow installed is a silent no-op
    Given `Pillow` is not installed
    When I run `latex2arxiv paper.zip --resize 1600`
    Then no images in the output zip are resized
    And the process still completes the rest of the pipeline normally
