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
  "log": "  main tex: main.tex\n  ..."
}
```

### `clean_submission`

Full conversion: prunes, cleans, and produces an arXiv-ready zip.

**Parameters:** Same as `validate_submission`.

**Returns:**
```json
{
  "success": true,
  "errors": [],
  "warnings": [],
  "log": "...",
  "output_zip": "/tmp/paper_arxiv.zip"
}
```

## Example Agent Interaction

> **User:** Check if my paper at `~/papers/icml2025/` is ready for arXiv.
>
> **Agent** calls `validate_submission(path="~/papers/icml2025/")` and gets:
> ```json
> {
>   "success": false,
>   "errors": ["\\usepackage{minted} requires shell-escape — arXiv compiles without it"],
>   "warnings": ["biblatex detected but no main.bbl shipped"]
> }
> ```
>
> **Agent:** Your paper has 1 error blocking submission: `minted` requires `--shell-escape` which arXiv doesn't run. You'll need to replace `minted` with `listings` or `verbatim`. Also, consider shipping a `.bbl` file as a fallback for biblatex.
