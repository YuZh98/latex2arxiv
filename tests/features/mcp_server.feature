Feature: MCP server exposes arXiv validation to AI agents
  As a user of an AI coding assistant (Claude Desktop, Cursor, etc.)
  I want my agent to call validate_submission / clean_submission as tools
  So that I can ask the agent to check and fix my paper conversationally

  # Server entry point: `latex2arxiv-mcp` (stdio).
  # Tool surface: mcp_server.py.

  Background:
    Given the `latex2arxiv-mcp` stdio server is running
    And the safe-root is the current working directory (or $LATEX2ARXIV_MCP_BASE_DIR if set)

  Scenario: validate_submission on a clean project returns success
    Given a directory "paper/" containing a valid LaTeX project
    When the agent calls `validate_submission(path="paper")`
    Then the response is `{"success": true, "errors": [], "warnings": [...], "log": ""}`

  Scenario: validate_submission reports pre-flight errors
    Given a directory "paper/" whose main .tex contains `\usepackage{minted}`
    When the agent calls `validate_submission(path="paper")`
    Then the response has `success: false`
    And `errors[]` contains the minted shell-escape message
    And no output zip is created on disk

  Scenario: clean_submission writes a zip and returns its path
    Given a directory "paper/" containing a valid LaTeX project
    When the agent calls `clean_submission(path="paper")`
    Then the response has `success: true`
    And `output_zip` is a path to a written .zip file
    And the caller is responsible for cleaning up that file

  Scenario: clean_submission honors a caller-supplied output_path
    Given a directory "paper/" and an existing parent directory "out/"
    When the agent calls `clean_submission(path="paper", output_path="out/paper.zip")`
    Then "out/paper.zip" is written
    And `output_zip` in the response equals the resolved "out/paper.zip"
    And on subsequent failures the file is not auto-deleted by the server

  Scenario: clean_submission rejects an output_path whose parent does not exist
    Given a directory "paper/" containing a valid LaTeX project
    When the agent calls `clean_submission(path="paper", output_path="missing/out.zip")`
    Then the response has `success: false`
    And `errors[]` mentions that the output directory does not exist

  Scenario Outline: Paths outside the safe root are rejected
    When the agent calls `validate_submission(path="<bad>")`
    Then the response has `success: false`
    And `errors[]` contains "Path outside allowed base directory"

    Examples:
      | bad                 |
      | ../escape            |
      | /etc/passwd          |
      | ~/secret             |

  Scenario: Nonexistent path returns a clear error
    When the agent calls `validate_submission(path="not_a_real_dir")`
    Then the response has `success: false`
    And `errors[]` contains "Path not found"

  Scenario: Symlinked directories inside a project dir are excluded with a warning
    Given a directory "paper/" containing a symlinked subdirectory "ext -> /tmp/elsewhere"
    When the agent calls `clean_submission(path="paper")`
    Then `warnings[]` contains a "symlinked directory was excluded" notice
    And no files from outside "paper/" leak into the output zip

  Scenario: Symlinks escaping the project root are dropped with a warning
    Given a directory "paper/" containing a symlinked file pointing outside "paper/"
    When the agent calls `clean_submission(path="paper")`
    Then `warnings[]` contains a "symlink escapes project root" notice
    And the escaped target is not in the output zip

  Scenario: ConverterError from the pipeline is surfaced cleanly
    Given an input that causes a fatal converter error (e.g. unreadable zip)
    When the agent calls `validate_submission(path="broken.zip")`
    Then the response has `success: false`
    And `errors[]` contains a human-readable description of the failure
    And no Python traceback leaks into the response

  Scenario: Pipeline progress does not pollute the JSON-RPC stream
    When the agent calls `clean_submission(path="paper")`
    Then any pipeline progress lines go to stderr
    And stdout contains only valid MCP JSON-RPC frames
