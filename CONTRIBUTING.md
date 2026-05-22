# Contributing to latex2arxiv

Thanks for your interest in contributing. This project follows a few
lightweight conventions that keep the codebase auditable and the
release process predictable.

## Quick start

```bash
git clone https://github.com/YuZh98/latex2arxiv
cd latex2arxiv
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[mcp]"
pip install pytest ruff
pytest
```

`pdflatex` (TeX Live or MacTeX) is only needed if you run the
`compile-smoke` tests locally. The default `pytest` invocation skips
anything that requires a working LaTeX install.

## Branch naming

```
<type>/<short-description>
```

Where `<type>` is one of:

`feat` · `fix` · `schema` · `config` · `refactor` · `test` · `docs` · `review` · `chore`

Examples: `feat/flatten-flag`, `fix/biblatex-subdir`, `docs/security-policy`.

## Commit messages

Conventional Commits, subject ≤ 72 characters in imperative mood. The
body explains *why* a change was made when the reason isn't obvious
from the subject. Example:

```
fix: deduplicate .bib files — prefer root-level over subdirectory copies

When a project ships both bib/refs.bib and refs.bib, we previously
included both, which arXiv rejects. Pick the root-level copy.
```

## Pull request flow

1. **Open a PR against `main`** with a clear summary and a test plan
   (manual steps, fixture additions, what you expect to break).
2. **CI must be green before merge.** No admin-bypass merges while
   checks are in progress or red.
3. **Behaviour-changing PRs get an independent review** before merge.
   Docs-only, dependabot grouped-minor/patch, and single-file typo
   fixes are exempt (note `audit-exempt: docs-only` etc. in the PR body).
4. **No `Co-Authored-By: Claude` trailers** or AI/agent process narrative
   in committed artefacts — readers care about the change, not the
   workflow that produced it.

## Tests

- All new pre-flight `[error]` / `[warn]` checks need a fixture in
  `tests/fixtures/` or a unit test in `tests/test_pipeline.py`.
- New CLI flags need a test that exercises both the happy path and at
  least one failure mode.
- Regressions get a pinning test in the same PR that fixes them.

## Filing issues

- **Bug reports**: include `latex2arxiv --version`, Python version, OS,
  and a minimal `.zip` reproducer if at all possible. Use the bug
  template.
- **Feature requests**: describe the problem first, the proposed
  solution second. Use the feature template.
- **Questions**: use [GitHub Discussions](https://github.com/YuZh98/latex2arxiv/discussions),
  not Issues.

## Security

Vulnerability reports go through GitHub Security Advisories — see
[SECURITY.md](SECURITY.md). Don't open a public issue.

## Code of Conduct

All participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Code style

- `ruff` is the formatter and linter. Run `ruff check . && ruff format .`
  before pushing.
- Type hints on all public functions (parameters and return values).
- No bare `print` debug statements in committed code — use the
  logging module or remove before pushing.
- Don't add backwards-compatibility shims for code that hasn't shipped.
- Single source of truth for constants, status values, and config keys;
  no scattered magic numbers.

## Releases

Releases are cut by the maintainer via the GitHub Actions `Release`
workflow (manual `workflow_dispatch`). After merging the version-bump
PR, a `v*` tag is pushed; the publish workflow handles PyPI, the GitHub
Release, and the Homebrew tap formula bump automatically.
