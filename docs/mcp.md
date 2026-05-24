# MCP Server

`latex2arxiv` ships an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server so AI agents can validate and clean arXiv submissions directly.

## Installation

```bash
pip install "latex2arxiv[mcp]"
```

## Usage with Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "latex2arxiv": {
      "command": "latex2arxiv-mcp"
    }
  }
}
```

## Usage with Cursor

Add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "latex2arxiv": {
      "command": "latex2arxiv-mcp"
    }
  }
}
```

## Usage with VS Code (Copilot Chat)

Add to `.vscode/mcp.json` in your workspace (or user settings):

```json
{
  "servers": {
    "latex2arxiv": {
      "command": "latex2arxiv-mcp"
    }
  }
}
```

## Usage with Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "latex2arxiv": {
      "command": "latex2arxiv-mcp"
    }
  }
}
```

## Usage with Zed

Install the `latex2arxiv` extension from Zed's Extensions panel. The extension launches `latex2arxiv-mcp` automatically — no JSON config needed.

> Requires `latex2arxiv-mcp` on PATH (`pip install "latex2arxiv[mcp]"`).


## Available Tools

### `validate_submission`

Dry-run pre-flight check. Returns errors and warnings without producing output.

**Parameters:**
- `path` (required): Path to a `.zip` file or directory containing the LaTeX project.
- `main_tex` (optional): Filename of the main `.tex` file.
- `config` (optional): Path to a YAML config file for custom removal rules.

**Returns:**
```json
{
  "success": true,
  "errors": [],
  "warnings": ["\\today used in \\date — arXiv may rebuild the PDF..."],
  "log": ""
}
```

> Pipeline progress is written to stderr. Structured findings are in `errors` and `warnings`.

### `clean_submission`

Full conversion: prunes, cleans, and produces an arXiv-ready zip.

**Parameters:**
- `path` (required): Path to a `.zip` file or directory containing the LaTeX project.
- `main_tex` (optional): Filename of the main `.tex` file.
- `config` (optional): Path to a YAML config file for custom removal rules.
- `output_path` (optional): Path where the output zip should be written. When provided, the caller owns the file and is responsible for cleanup. If omitted, a temporary file is created and its path is returned in `output_zip`; the caller must delete it after use.

**Returns:**
```json
{
  "success": true,
  "errors": [],
  "warnings": [],
  "log": "",
  "output_zip": "/tmp/paper_arxiv.zip"
}
```

> `output_zip` is present only on success with `dry_run=false`. Pipeline progress is written to stderr.

## Security: Path Restriction

Both tools resolve the `path` argument relative to a sandboxed root. The root is controlled by the `LATEX2ARXIV_MCP_BASE_DIR` environment variable:

- **If set:** all paths are resolved under that directory; any attempt to escape it is rejected.
- **If unset:** the root falls back to `cwd` at server start-up. Claude Desktop launches MCP servers from the user's home directory, so the entire `$HOME` tree becomes reachable by any agent that calls these tools.

**Always set `LATEX2ARXIV_MCP_BASE_DIR` to a specific papers directory.**

### Claude Desktop

```json
{
  "mcpServers": {
    "latex2arxiv": {
      "command": "latex2arxiv-mcp",
      "env": {
        "LATEX2ARXIV_MCP_BASE_DIR": "/path/to/papers"
      }
    }
  }
}
```

### Cursor

```json
{
  "mcpServers": {
    "latex2arxiv": {
      "command": "latex2arxiv-mcp",
      "env": {
        "LATEX2ARXIV_MCP_BASE_DIR": "/path/to/papers"
      }
    }
  }
}
```

## Example Agent Interaction

> **User:** Check if my paper at `/home/user/papers/icml2025/` is ready for arXiv.
>
> **Agent** calls `validate_submission(path="/home/user/papers/icml2025/")` and gets:
> ```json
> {
>   "success": false,
>   "errors": ["\\usepackage{minted} requires shell-escape — arXiv compiles without it"],
>   "warnings": ["biblatex detected but no main.bbl shipped"]
> }
> ```
>
> **Agent:** Your paper has 1 error blocking submission: `minted` requires `--shell-escape` which arXiv doesn't run. You'll need to replace `minted` with `listings` or `verbatim`. Also, consider shipping a `.bbl` file as a fallback for biblatex.
