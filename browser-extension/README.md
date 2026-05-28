# latex2arxiv for Overleaf

Chrome extension that runs [`latex2arxiv`](https://github.com/YuZh98/latex2arxiv) against an open Overleaf project: validates arXiv readiness, surfaces diagnostics in-page, and downloads a clean submission zip — no local install required.

## Status

**v0.1 — working end-to-end in unpacked-dev mode, not yet store-ready.** The UI, content script, service worker, and Web Worker run the full `latex2arxiv` pipeline via Pyodide against an open Overleaf project. One gate remains before Chrome Web Store submission:

- Pyodide itself still loads from the jsDelivr CDN, with no SRI on the fetched assets. MV3 prohibits remotely-hosted code from extension contexts at Web Store review. Production v0.1.1 must vendor the Pyodide runtime (`pyodide.js`, `pyodide.asm.*`, the built-in package set) into the extension package and point `indexURL` at `chrome.runtime.getURL("pyodide/")`. The application wheels (`latex2arxiv`, `bibtexparser`, `pyparsing`) are already bundled under `wheels/`.

> **Dev-only warning:** because v0.1 loads Pyodide and its package wheels from a third-party CDN, every "Clean for arXiv" run depends on the integrity of that supply chain. Do not load this extension against sensitive or pre-publication Overleaf projects until v0.1.1 vendors Pyodide locally and pins SHA-256 hashes for every bundled wheel.

Design rationale, dismissed alternatives, and the full build plan: `docs/browser-extension-design.md`.

## Architecture

Three execution contexts, each picked for a hard browser constraint:

| Context | File | Responsibility |
|---|---|---|
| Content script | `content.js` | Inject panel UI; same-origin fetch of project zip; message routing |
| Web Worker | `worker.js` | Run Pyodide + the `latex2arxiv` Python pipeline |
| Service worker | `background.js` | Dispatch `chrome.downloads.download` for the output zip |

Design rationale + dismissed alternatives: see [`docs/browser-extension-design.md`](../docs/browser-extension-design.md) at the repo root.

## Development

Load the extension unpacked in Chrome:

1. Visit `chrome://extensions/`.
2. Toggle **Developer mode** on.
3. Click **Load unpacked** and pick this directory.
4. Open any Overleaf project. The panel appears at the bottom-right.

No build step in v0.1. Source files and bundled wheels are loaded as-is.

## Bundled wheels

`wheels/` contains the Python packages installed into Pyodide on first run:

| Wheel | Why bundled |
|---|---|
| `latex2arxiv-*.whl` | This project's own pipeline. Built from local source on this branch; version label matches the most recent PyPI release but the code is ahead by any unreleased changes on `main` until the next PyPI cut |
| `bibtexparser-*.whl` | Used by `pipeline/bibtex.py`; PyPI ships sdist only, and micropip cannot build sdists in-browser |
| `pyparsing-*.whl` | Transitive dep of `bibtexparser` |

Pillow, PyYAML, and `regex` are pulled from Pyodide's own package index at first install.

Rebuild the wheels with:

```sh
# from repo root
python -m build --wheel --outdir /tmp/l2a-wheel/ .
pip wheel 'bibtexparser>=1.4,<2' pyparsing --no-deps -w browser-extension/wheels/
cp /tmp/l2a-wheel/latex2arxiv-*.whl browser-extension/wheels/
```

## Tests

`tests/pyodide-smoke.mjs` boots Pyodide in Node, installs the bundled wheels, runs `converter.convert()` against a fixture from `tests/fixtures/`, and asserts the output zip is non-trivial.

```sh
cd browser-extension/tests
npm install
npm run smoke
```

## Permissions

| Permission | Why |
|---|---|
| `host_permissions: https://www.overleaf.com/*` | Same-origin fetch of the project zip; content-script injection |
| `permissions: downloads` | Save the output zip via `chrome.downloads.download` |

No `<all_urls>`, no `tabs`, no `cookies`, no `nativeMessaging`, no `storage`, no `webRequest`. Reviewed for narrowness.

## Privacy

The extension is a thin client: project bytes go from the Overleaf tab to the in-browser Pyodide runtime and back to the user's chosen download path. Nothing is sent to a server we operate. Pyodide assets are loaded from the official jsDelivr CDN.
