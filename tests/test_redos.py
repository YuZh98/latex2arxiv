"""Tests for ReDoS protection in apply_config replacements."""
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import apply_config, _REGEX_TIMEOUT_SECONDS


class TestReDoSProtection:
    def _replacements_config(self, pattern: str, replacement: str = "") -> dict:
        return {"replacements": [{"pattern": pattern, "replacement": replacement}]}

    def test_benign_replacement_works(self):
        config = self._replacements_config(r"\bfoo\b", "bar")
        result = apply_config("foo baz foo", config)
        assert result == "bar baz bar"

    def test_catastrophic_backtracking_completes_within_limit(self):
        # (a+)+ applied to a non-matching string triggers exponential backtracking.
        evil_pattern = r"(a+)+$"
        evil_input = "a" * 30 + "b"  # 30 chars causes exponential backtracking on Python 3.13
        config = self._replacements_config(evil_pattern, "x")

        deadline = _REGEX_TIMEOUT_SECONDS + 3.0  # generous wall-clock budget
        start = time.monotonic()
        result = apply_config(evil_input, config)
        elapsed = time.monotonic() - start

        assert elapsed < deadline, (
            f"apply_config took {elapsed:.1f}s — ReDoS guard did not fire in time"
        )
        # Source is returned unchanged when the rule times out.
        assert result == evil_input

    def test_redos_timeout_skips_rule_leaves_source_intact(self, capsys):
        evil_pattern = r"(a+)+$"
        source = "a" * 30 + "b"
        config = self._replacements_config(evil_pattern, "REPLACED")

        result = apply_config(source, config)

        assert result == source
        captured = capsys.readouterr()
        assert "timed out" in captured.out

    def test_invalid_regex_still_warns(self, capsys):
        config = self._replacements_config(r"[unclosed")
        result = apply_config("hello", config)
        assert result == "hello"
        captured = capsys.readouterr()
        assert "invalid regex" in captured.out

    def test_normal_regex_timeout_not_triggered(self):
        # A straightforward substitution must not be falsely timed out.
        config = self._replacements_config(r"\\todo\{[^}]*\}", "")
        source = r"Some text \todo{fix this} more text."
        result = apply_config(source, config)
        assert r"\todo" not in result
