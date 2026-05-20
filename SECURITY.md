# Security Policy

## Supported versions

As of v1.0, `latex2arxiv` supports the latest two minor versions for at
least 6 months each. The currently supported lines are:

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |
| 0.11.x  | :white_check_mark: |
| < 0.11  | :x:                |

Once 1.1 ships, the 0.11.x line moves to end-of-life.

## Reporting a vulnerability

Please **do not open a public issue** for security reports.

Use GitHub's private "Report a vulnerability" flow:

1. Visit https://github.com/YuZh98/latex2arxiv/security/advisories/new
2. Describe the vulnerability, ideally with a minimal reproducer
   (a sample `.zip` project, the `latex2arxiv` command you ran, and
   the observed vs. expected behaviour).
3. A maintainer will respond within 7 days with an acknowledgement
   and triage plan.

If GitHub Security Advisories is unavailable to you, email
`hugh.stats@gmail.com` with subject prefix `[latex2arxiv security]`.

## In scope

- Arbitrary file write or read outside the project root during extraction
  (zip-slip; already mitigated by member-path validation).
- Command injection via crafted filenames passed to `--compile`
  (which invokes `pdflatex`/`biber`/`bibtex` as subprocesses).
- Resource exhaustion (excessive memory, infinite loops, gigantic output)
  triggered by a crafted but otherwise-valid LaTeX project.
- Bypass of the pre-flight `[error]` exit code (CI gating relies on it).

## Out of scope

- Vulnerabilities in `pdflatex`, `biber`, `bibtex`, or the TeX Live
  toolchain itself — report those upstream.
- Vulnerabilities in transitive Python dependencies — handled via
  Dependabot; standalone reports against `bibtexparser`, `Pillow`,
  `pyparsing`, or `pyyaml` belong on their respective trackers.
- Issues that require an attacker to control the local filesystem
  outside the input zip / project directory.
