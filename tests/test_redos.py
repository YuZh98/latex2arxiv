"""Tests for ReDoS protection in apply_config replacements.

The guard is implemented via the ``regex`` package's ``timeout=`` parameter,
which works on Linux, macOS, Windows, and Pyodide (WebAssembly). The library's
matching engine is robust enough that classic textbook ReDoS patterns no longer
trigger an actual ``TimeoutError`` — the catastrophic-backtracking test below
asserts only the user-visible contract (the conversion does not hang), and the
timeout-handler branch is exercised via monkeypatch.
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import config as config_mod
from pipeline.config import apply_config, _REGEX_TIMEOUT_SECONDS


class TestReDoSProtection:
    def _replacements_config(self, pattern: str, replacement: str = "") -> dict:
        return {"replacements": [{"pattern": pattern, "replacement": replacement}]}

    def test_benign_replacement_works(self):
        config = self._replacements_config(r"\bfoo\b", "bar")
        result = apply_config("foo baz foo", config)
        assert result == "bar baz bar"

    def test_catastrophic_backtracking_completes_within_limit(self):
        evil_pattern = r"(a+)+$"
        evil_input = "a" * 30 + "b"
        config = self._replacements_config(evil_pattern, "x")

        deadline = _REGEX_TIMEOUT_SECONDS + 3.0
        start = time.monotonic()
        apply_config(evil_input, config)
        elapsed = time.monotonic() - start

        assert elapsed < deadline, f"apply_config took {elapsed:.1f}s — ReDoS guard did not fire in time"

    def test_timeout_path_skips_rule_and_warns(self, monkeypatch, capsys):
        def fake_sub(*_args, **_kwargs):
            raise TimeoutError

        monkeypatch.setattr(config_mod.regex, "sub", fake_sub)

        source = "anything"
        config = self._replacements_config(r"x", "y")
        result = apply_config(source, config)

        assert result == source
        assert "timed out" in capsys.readouterr().err

    def test_invalid_regex_still_warns(self, capsys):
        config = self._replacements_config(r"[unclosed")
        result = apply_config("hello", config)
        assert result == "hello"
        assert "invalid regex" in capsys.readouterr().err

    def test_normal_regex_not_falsely_timed_out(self):
        config = self._replacements_config(r"\\todo\{[^}]*\}", "")
        source = r"Some text \todo{fix this} more text."
        result = apply_config(source, config)
        assert r"\todo" not in result

    def test_no_signal_module_used(self):
        """Guard against regressions reintroducing the Unix-only signal-based mechanism."""
        import pipeline.config as cfg

        assert not hasattr(cfg, "signal"), "pipeline.config must not import signal — broken on Windows + Pyodide"
