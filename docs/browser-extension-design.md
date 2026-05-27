# Browser extension design — `latex2arxiv-overleaf`

Status: **proposed**. Target: v0.1 of a Chrome extension that runs `latex2arxiv` against an open Overleaf project, surfaces diagnostics in-page, and produces an arXiv-ready zip with one click — no local install.

## Goal

Bring the full `latex2arxiv` flow (validate + clean + zip) into the Overleaf UI, so a user can go from "I'm writing in Overleaf" to "I have an arXiv-ready zip" without leaving the browser or installing anything locally.

## Non-goals (v0.1)

- Firefox / Edge / Safari support. Chrome-only first.
- Post-clean `pdflatex` / `bibtex` verification (browser sandbox cannot run them). The CLI's `--compile` flag has no browser analogue.
- Native-messaging fast path to a locally-installed CLI. Considered and rejected (see Alternatives).
- Editing the Overleaf project in-place. The extension is read-only against Overleaf state and outputs a zip the user uploads to arXiv themselves.

## Audience

Overleaf users overlap minimally with local-CLI users: people on Overleaf deliberately chose a hosted editor to avoid a local TeX install. Designing as if they will `pip install latex2arxiv` to use the extension defeats the value proposition. The extension must work standalone, with no user-side install beyond the extension itself.

## Architecture

Three execution contexts, each picked for a hard constraint:

| Context | Lives in | Responsibility | Why here |
|---|---|---|---|
| Content script | `*://*.overleaf.com/project/*` | Inject UI panel, same-origin fetch of project zip, message passing | Same-origin access to Overleaf endpoints; DOM injection |
| Web Worker | Spawned by content script | Run Pyodide, execute `latex2arxiv` pipeline on the zip bytes | Pyodide load + long-running CPU work; cannot live in service worker (MV3 service workers terminate aggressively) |
| Background service worker | Extension background | Call `chrome.downloads.download` for the output zip | `chrome.downloads.*` is unavailable to content scripts |

Data flow per run:

```
[content script] ──fetch /project/{id}/download/zip (same-origin)──▶ Overleaf
       │
       ├──postMessage(zipBytes)──▶ [web worker (Pyodide + latex2arxiv)]
       │                                  │
       │                                  └──postMessage({outputZip, diagnostics})──┐
       │                                                                            │
       ◀────────────────────────────────────────────────────────────────────────────┘
       │
       ├── render diagnostics in-page panel
       └──sendMessage(outputZip)──▶ [service worker]
                                          │
                                          └── chrome.downloads.download({ blob, suggestedFilename, saveAs: true })
```

## Engine choice: Pyodide

Pyodide loads CPython + stdlib + `latex2arxiv` wheel into the browser via WebAssembly. The same wheel published to PyPI runs unmodified (with two narrow exceptions, listed below).

Bundle cost: CPython + stdlib ~7 MB gzipped, Pillow ~2-3 MB, `latex2arxiv` wheel <100 KB. Total **~9-10 MB on first invocation**, cached afterward via standard HTTP caching of the Pyodide CDN assets.

### Alternatives considered

**Pure-JS rewrite of `pipeline/`.** Rejected. Re-implementing the regex-heavy preflight checks, dependency graph, flatten, and bibtex normalization in TypeScript is a multi-week effort and creates a permanent drift surface — every change to the Python pipeline needs a parallel JS change forever. Single-implementation-of-record is more valuable than a smaller bundle.

**Native Messaging to a locally-installed CLI.** Rejected for v0.1.
- Audience mismatch: Overleaf users disproportionately don't have a local Python/TeX stack.
- Setup is not trivial: requires a `latex2arxiv install-browser-host` subcommand that writes a per-browser, per-OS native-host manifest (macOS `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/`, Linux `~/.config/google-chrome/NativeMessagingHosts/`, Windows registry key under `HKCU\Software\Google\Chrome\NativeMessagingHosts`), with separate variants for Chrome/Edge/Brave.
- Chrome Web Store reviews native-messaging extensions more strictly, not less — native messaging is a remote-code-execution channel from the store's threat model.
- Install dialog warns "this extension can communicate with native applications on your computer." High friction for a tool a new user is trying for the first time.
- Possible re-introduction in v1.x as an opt-in fast path for power users who already have the CLI; not before the Pyodide path is validated.

## Prerequisite: ReDoS-guard rewrite

`pipeline/config.py` guards regex application with `signal.SIGALRM` / `signal.alarm`. This does not work in:

- WebAssembly (Pyodide has no Unix signals)
- Windows (no `SIGALRM`)

The guard is therefore already broken on Windows in the existing CLI — a real bug, not a browser-only concern. Fix lands as a **separate prerequisite PR on the main repo** before any browser-extension work. Replacement options:

- Run regex in a `concurrent.futures` worker with a timeout (works on Pyodide single-threaded too if the worker is the JS-side Web Worker, but adds complexity).
- Bound regex input size and complexity statically; drop runtime timeout.
- Use a platform-portable timeout via `threading.Timer` to set a flag that the regex loop polls.

Decision deferred to that PR. Acceptance criteria: the existing ReDoS test (`tests/test_redos.py`) passes on Linux, macOS, and Windows in CI, and the implementation has no `signal.*` references.

## Pipeline survival matrix in Pyodide

| Module | Imports of concern | Works in Pyodide? |
|---|---|---|
| `pipeline/preflight.py` | re, pathlib | Yes |
| `pipeline/deps.py` | re, pathlib | Yes |
| `pipeline/tex.py` | re | Yes |
| `pipeline/flatten.py` | re, pathlib | Yes |
| `pipeline/bibtex.py` | typing only | Yes |
| `pipeline/process.py` | calls into above + `pipeline/images` | Yes (Pillow available as Pyodide package) |
| `pipeline/images.py` | `PIL.Image` (soft dep, no-op if absent) | Yes with Pillow loaded; degraded no-op if not |
| `pipeline/guide.py` | `subprocess.run(['pdfinfo', …])` for page count | Falls back to raw-PDF byte regex on `/Type /Page`; degrades to `None` page count when no PDF (browser case) |
| `pipeline/config.py` | `signal.SIGALRM` | **Blocked** until prerequisite PR lands |
| `pipeline/build.py` | `subprocess` (pdflatex/bibtex/open) | Skipped — feature not exposed in browser UI |
| `pipeline/resolve.py` | `subprocess` (git clone), `zipfile`, `tempfile` | Git-URL branch unused in browser (input is in-memory zip from Overleaf); zipfile/tempfile fine |
| `converter.py` | `importlib.resources` for packaged demo + default config | Works if those resources are written into Pyodide's virtual FS at init |

## Overleaf project fetch

Primary endpoint: `GET https://www.overleaf.com/project/{projectId}/download/zip`.

- Same-origin from a content script injected on `https://www.overleaf.com/project/{projectId}` — no CORS workaround needed.
- Authenticated automatically by the user's existing `overleaf_session2` cookie (browser sends it on the same-origin request).
- No CSRF token required for the download endpoint (read-only).
- Confirmed by third-party tooling (`kdevo/overleaf-sync`, `iamhyc/Overleaf-Workshop`).

**Plan B if the endpoint becomes unstable:** Overleaf's documented Git integration with auth tokens. Heavier UX (requires user to mint a token) but is a documented contract Overleaf commits to, unlike the session-cookie download path. Not implemented in v0.1; design must not preclude adding it later.

## Project ID detection

Content script reads `window.location.pathname` and matches `/project/([0-9a-f]+)(?:/|$)`. The 24-hex pattern is the Overleaf project-id format. No reliance on DOM class names — Overleaf reworks markup without warning. Selectors that *do* need DOM (panel injection target, toolbar slot) use `aria-label` / role / structural queries, never CSS classes.

## Manifest + permissions

Manifest V3.

```jsonc
{
  "manifest_version": 3,
  "name": "latex2arxiv for Overleaf",
  "host_permissions": ["*://*.overleaf.com/*"],
  "permissions": ["downloads"],
  "content_scripts": [{
    "matches": ["*://*.overleaf.com/project/*"],
    "js": ["content.js"]
  }],
  "background": { "service_worker": "background.js" },
  "web_accessible_resources": [{
    "resources": ["pyodide/*", "worker.js"],
    "matches": ["*://*.overleaf.com/*"]
  }]
}
```

Permission rationale:
- `host_permissions` scoped to Overleaf only — required for same-origin fetch of the project zip and for content-script injection.
- `downloads` — required for `chrome.downloads.download`. No `downloads.open`, no `downloads.shelf`.
- No `tabs`, `storage`, `webRequest`, `cookies`, `nativeMessaging`, no `<all_urls>`. Narrowness matters for Chrome Web Store review velocity.

## UI

Panel injected into the Overleaf project toolbar area (target chosen by `aria-label`, not class name).

```
┌─ latex2arxiv ─────────────────────────────────┐
│  Output filename: [ paper-arxiv.zip       ]   │
│  Main .tex:       [ auto-detect ▼ ]           │
│  ☐ Flatten \input/\subfile into one .tex      │
│  ☐ Resize images (longest side ≤ 1600 px)     │
│  ☐ Write arXiv upload guide (.txt)            │
│  ▸ Advanced: custom arxiv_config.yaml         │
│                                               │
│  [ Clean for arXiv ]   [ Just validate ]      │
│                                               │
│  ── Diagnostics ──────────────────────────    │
│  ⚠  3 warnings · ✗ 0 errors                   │
│  • main.tex:42  \today inside \date{}         │
│  • figs/plot.eps  use .pdf for arXiv         │
│  • biblatex+biber detected → using bbl mode   │
└───────────────────────────────────────────────┘
```

Filename field is a *suggestion* only. Final save location is chosen by the user via the OS save dialog (`chrome.downloads.download({ saveAs: true })`). MV3 cannot pre-select a target folder; the suggested-filename parameter has a known intermittent ignore bug (chromium issues #40706258) — `saveAs: true` is the documented workaround.

Advanced row reveals a textarea that accepts the YAML contents of an `arxiv_config.yaml` (passed to the pipeline via the same code path as the CLI's `--config FILE`).

## Build sequence

1. **Prereq PR on `latex2arxiv`:** replace `signal.SIGALRM` ReDoS guard with a portable timeout. Land + release before any browser-extension code.
2. **Scaffold `browser-extension/`** parallel to `vscode-extension/`. Vite + TypeScript + a Web Worker entry that boots Pyodide and exports a single `runPipeline(zipBytes, opts) → { outputZip, diagnostics }` handler.
3. **Pyodide pipeline harness.** Load Pyodide, `micropip.install('latex2arxiv')` (or bundle the wheel), expose the Python entrypoint, smoke-test against a fixture project from `tests/`.
4. **Overleaf content script.** Same-origin fetch, project-id detection, message channel to worker, message channel to background.
5. **Background download handler.** `chrome.downloads.download` with `saveAs: true`.
6. **UI panel + diagnostics renderer.** Inject into Overleaf toolbar; preserve a fallback "open in standalone tab" path in case the toolbar slot disappears.
7. **End-to-end on a real Overleaf project** before opening Chrome Web Store submission.

## Testing strategy

CI must never depend on `overleaf.com` being live. Three test layers cover the surface; the dependency on real Overleaf is moved out of CI and into a release-time manual gate.

**Layer 1 — Worker logic (Pyodide pipeline). Pyodide-in-Node smoke tests.**

- Run Pyodide in Node (`pyodide` npm package), load the bundled `latex2arxiv` wheel, replay every fixture zip from `tests/fixtures/` through the worker entrypoint, snapshot the JSON diagnostics + a stable hash of the output zip contents.
- Compares against the canonical CLI output for the same fixtures (already produced by the existing pytest suite). Drift between the two is a test failure — that's the contract that makes the "same wheel, no drift" claim load-bearing.
- Catches Pyodide-specific breakage that the Python suite cannot see: missing stdlib in Pyodide, `signal` regressions, `importlib.resources` path differences, Pillow load failure.
- Runs in the existing CI matrix as a Node job. Fast (Pyodide cold-load is the only slow step; cache it).

**Layer 2 — Content script + UI. Playwright against a fixture page.**

- A minimal HTML fixture mimics the Overleaf DOM shape the panel targets (the toolbar slot, project-id in the URL). The extension is loaded unpacked by Playwright in a Chromium context.
- Playwright route-intercepts `*/project/*/download/zip` and serves a fixture zip from `tests/fixtures/`. The extension fetches, processes, and triggers the download — Playwright asserts the download fires with the expected filename and the in-page diagnostics panel renders the expected counts.
- This is the only place the extension's three contexts (content script ↔ worker ↔ service worker) are exercised together. Worth investing in.

**Layer 3 — Manifest + permissions snapshot test.**

- Trivial JSON-comparison test on `manifest.json`. Asserts permission set is exactly `["downloads"]`, host permissions is exactly `["*://*.overleaf.com/*"]`, no `<all_urls>`, no `nativeMessaging`, no `cookies`. Permission creep is silent and easy to miss in review; the snapshot makes it loud.

**Release-time manual gate (not CI).** Before each Chrome Web Store submission: load the unpacked extension in a real Chrome against a real Overleaf project (a test account holding a known-shape project lives in the maintainer's account, not in the repo). Confirm panel injection, fetch, conversion, download. One real-world smoke test catches Overleaf DOM/endpoint changes that fixtures cannot.

**Fixture discipline.** All fixtures live in `tests/fixtures/` and are shared with the pytest suite. Browser-extension tests must not introduce their own fixture set — duplication invites drift.

## Open questions

- Does Pyodide's regex performance on large `.tex` projects (300+ KB main file) meet "interactive feel" expectations, or does the worker need progress reporting? Benchmark in step 3 above; if slow, add a progress channel.
- Bundling strategy: ship `latex2arxiv` wheel inside the extension `.zip`, or `micropip.install` from PyPI on first run? Bundled = no PyPI dependency, larger `.zip`; micropip = smaller `.zip`, needs PyPI online on first run. Default to bundled for offline-friendliness.
- Versioning: lockstep with the main `latex2arxiv` package version, or independent? Lockstep is simpler and matches the `vscode-extension/` pattern.

## Risks

- **Overleaf endpoint stability.** Mitigation: Plan B Git integration sketched above; design keeps `fetchProjectZip()` behind a single function so the swap is local.
- **Pyodide initial load latency.** Mitigation: lazy-load on first action, show a "warming up" state; subsequent invocations are sub-second.
- **Chrome Web Store rejection.** Mitigation: narrow permissions, no native messaging, clear single-purpose listing.
- **Maintenance: Pyodide version drift, pinned vs latest.** Pin a known-good Pyodide release; bump deliberately as part of releases, not silently.
