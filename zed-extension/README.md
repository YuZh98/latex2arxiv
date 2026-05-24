# latex2arxiv — Zed Extension

MCP server extension that exposes [latex2arxiv](https://github.com/YuZh98/latex2arxiv) tools to Zed's Agent Panel.

## Tools provided

- **validate_submission** — Run pre-flight checks on a LaTeX project
- **clean_submission** — Produce an arXiv-ready zip from a LaTeX project

## Prerequisites

Install the `latex2arxiv` CLI with MCP support:

```bash
pip install "latex2arxiv[mcp]"
```

Verify the MCP server is available:

```bash
latex2arxiv-mcp --help
```

## Installation

Search for "latex2arxiv" in Zed's Extensions panel and click Install.

## Usage

1. Open a workspace containing your LaTeX project
2. Open the Agent Panel (⌘⇧A on macOS)
3. Ask the agent to validate or clean your paper:
   - "Validate my paper for arXiv submission"
   - "Clean this project for arXiv"

## Development

```bash
# Install Rust via rustup (required)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install as dev extension in Zed:
# 1. Open Zed
# 2. Command Palette → "zed: install dev extension"
# 3. Select this directory
```

## License

MIT
