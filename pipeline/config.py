import re
from pathlib import Path

from pipeline.tex import remove_cmd, unwrap_cmd

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _parse_simple_yaml(text: str) -> dict:
    """Minimal YAML parser for our config format.
    Supports top-level keys with list values and mapping list values.
    No dependency on pyyaml.
    """
    result = {}
    current_key = None
    current_list = None

    for line in text.splitlines():
        # Skip comments and blank lines
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0 and stripped.endswith(':'):
            # Top-level key
            current_key = stripped[:-1]
            current_list = []
            result[current_key] = current_list
        elif indent > 0 and stripped.startswith('- ') and current_list is not None:
            value = stripped[2:].strip()
            # Strip inline comments (text after unquoted #)
            value = re.sub(r'\s+#.*$', '', value).strip()
            if not value:
                continue
            # Check if this starts a mapping (next lines may have key: value)
            if ':' not in value:
                current_list.append(value)
            else:
                # Inline mapping item like "- pattern: '...'"
                mapping = {}
                k, v = value.split(':', 1)
                mapping[k.strip()] = v.strip().strip("'\"")
                current_list.append(mapping)
        elif indent > 2 and ':' in stripped and current_list and isinstance(current_list[-1], dict):
            # Continuation of a mapping item
            k, v = stripped.split(':', 1)
            current_list[-1][k.strip()] = v.strip().strip("'\"")

    return result


def load_config(config_path: Path) -> dict:
    text = config_path.read_text(encoding='utf-8')
    if HAS_YAML:
        return yaml.safe_load(text) or {}
    return _parse_simple_yaml(text)


def _make_cmd_pattern(cmd: str) -> str:
    """Build a regex that matches \\cmd or \\cmd{arg} as written in the config."""
    cmd = cmd.lstrip('\\')
    return '\\\\' + re.escape(cmd)


def apply_config(source: str, config: dict) -> str:
    """Apply user-defined removal rules from config."""

    # 1. commands_to_delete: remove \cmd{...} entirely (including argument).
    # Brace-balanced so nested braces (e.g. \deleted{see \cite{x}}) are handled.
    for cmd in config.get('commands_to_delete', []):
        base = _make_cmd_pattern(cmd)
        source = remove_cmd(source, re.compile(base + r'(?:\[[^\]]*\])?'))
        source = re.sub(base, '', source)

    # 2. commands_to_unwrap: remove \cmd but keep its argument text.
    # Brace-balanced; falls back to bare-switch removal when no arg follows.
    for cmd in config.get('commands_to_unwrap', []):
        base = _make_cmd_pattern(cmd)
        source = unwrap_cmd(source, re.compile(base + r'(?:\[[^\]]*\])?'))

    # 3. environments_to_delete
    for env in config.get('environments_to_delete', []):
        source = re.sub(
            r'\\begin\{' + re.escape(env) + r'\}.*?\\end\{' + re.escape(env) + r'\}',
            '', source, flags=re.DOTALL
        )

    # 4. replacements: raw regex find/replace
    for rule in config.get('replacements', []):
        source = re.sub(rule['pattern'], rule.get('replacement', ''), source)

    return source
