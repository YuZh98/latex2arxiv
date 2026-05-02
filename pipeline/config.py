import re
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def load_config(config_path: Path) -> dict:
    if not HAS_YAML:
        print("  [warn] pyyaml not installed; --config ignored. Install with: pip install pyyaml")
        return {}
    with open(config_path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def apply_config(source: str, config: dict) -> str:
    """Apply user-defined removal rules from config."""

    # 1. commands_to_delete: remove \cmd{...} entirely (including argument)
    for cmd in config.get('commands_to_delete', []):
        cmd = cmd.lstrip('\\')
        # Handle \cmd[opt]{arg} and \cmd{arg}
        source = re.sub(
            r'\\' + re.escape(cmd) + r'(?:\[[^\]]*\])?\{[^{}]*\}',
            '', source
        )
        # Also handle bare switches like \color{red} with no following braces
        source = re.sub(r'\\' + re.escape(cmd) + r'\b', '', source)

    # 2. commands_to_unwrap: remove \cmd but keep its argument text
    for cmd in config.get('commands_to_unwrap', []):
        cmd = cmd.lstrip('\\')
        # \cmd{text} → text
        source = re.sub(
            r'\\' + re.escape(cmd) + r'(?:\[[^\]]*\])?\{([^{}]*)\}',
            r'\1', source
        )
        # bare switch \cmd → ''
        source = re.sub(r'\\' + re.escape(cmd) + r'\b', '', source)

    # 3. environments_to_delete: remove \begin{env}...\end{env}
    for env in config.get('environments_to_delete', []):
        source = re.sub(
            r'\\begin\{' + re.escape(env) + r'\}.*?\\end\{' + re.escape(env) + r'\}',
            '', source, flags=re.DOTALL
        )

    # 4. replacements: raw regex find/replace
    for rule in config.get('replacements', []):
        source = re.sub(rule['pattern'], rule.get('replacement', ''), source)

    return source
