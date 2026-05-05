import re
from pathlib import Path

from pipeline.tex import remove_cmd, remove_bare_cmd, unwrap_cmd

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


_KNOWN_KEYS = frozenset({
    'commands_to_delete',
    'commands_to_unwrap',
    'environments_to_delete',
    'replacements',
})


def load_config(config_path: Path) -> dict:
    text = config_path.read_text(encoding='utf-8')
    if HAS_YAML:
        cfg = yaml.safe_load(text) or {}
    else:
        cfg = _parse_simple_yaml(text)
    if not isinstance(cfg, dict):
        # User wrote a top-level list/string/scalar instead of a mapping; downstream
        # config.get(...) calls would raise AttributeError.
        print(f"  [warn] config root must be a mapping (got {type(cfg).__name__}); "
              "ignoring the file")
        return {}
    for key in cfg:
        if key not in _KNOWN_KEYS:
            # Typos like 'command_to_delete' (singular) silently no-op otherwise,
            # so a paper full of revision markup ships unchanged.
            print(f"  [warn] unknown config key '{key}' — expected one of: "
                  f"{', '.join(sorted(_KNOWN_KEYS))}")
    return cfg


def _make_cmd_pattern(cmd: str) -> str:
    """Build a regex that matches \\cmd or \\cmd{arg} as written in the config."""
    cmd = cmd.lstrip('\\')
    return '\\\\' + re.escape(cmd)


def apply_config(source: str, config: dict) -> str:
    """Apply user-defined removal rules from config.

    Uses ``config.get(key) or []`` so a YAML null (``commands_to_delete:`` with
    no value, parsing as ``None``) is treated the same as an absent key.
    """

    # 1. commands_to_delete: remove \cmd{...} entirely (including argument).
    # Brace-balanced so nested braces (e.g. \deleted{see \cite{x}}) are handled.
    for cmd in config.get('commands_to_delete') or []:
        base = _make_cmd_pattern(cmd)
        source = remove_cmd(source, re.compile(base + r'(?:\[[^\]]*\])?'))
        # remove_bare_cmd (instead of plain re.sub) so a bare \cmd inside
        # a definition context (\newcommand{\cmd}, \def\cmd, ...) survives.
        source = remove_bare_cmd(source, re.compile(base))

    # 2. commands_to_unwrap: remove \cmd but keep its argument text.
    # Brace-balanced; falls back to bare-switch removal when no arg follows.
    for cmd in config.get('commands_to_unwrap') or []:
        base = _make_cmd_pattern(cmd)
        source = unwrap_cmd(source, re.compile(base + r'(?:\[[^\]]*\])?'))

    # 3. environments_to_delete
    for env in config.get('environments_to_delete') or []:
        source = re.sub(
            r'\\begin\{' + re.escape(env) + r'\}.*?\\end\{' + re.escape(env) + r'\}',
            '', source, flags=re.DOTALL
        )

    # 4. replacements: raw regex find/replace.
    # Per-rule try/except so one malformed pattern doesn't crash the conversion.
    for i, rule in enumerate(config.get('replacements') or []):
        if not isinstance(rule, dict):
            print(f"  [warn] replacements rule #{i} skipped — expected a mapping "
                  f"with 'pattern' and 'replacement', got {type(rule).__name__}")
            continue
        pattern = rule.get('pattern', '')
        if not pattern:
            # Empty pattern would re.sub at every position — silent corruption.
            print(f"  [warn] replacements rule #{i} skipped — missing or empty 'pattern'")
            continue
        replacement = rule.get('replacement', '')
        try:
            source = re.sub(pattern, replacement, source)
        except re.error as e:
            print(f"  [warn] replacements rule #{i} skipped — invalid regex "
                  f"{pattern!r}: {e}")

    return source
