# latex2arxiv for Overleaf

Chrome extension that runs [`latex2arxiv`](https://github.com/YuZh98/latex2arxiv) against an open Overleaf project: validates arXiv readiness, surfaces diagnostics in-page, and downloads a clean submission zip — no local install required.

## Status

**v0.1.1 — Chrome Web Store gates closed.** The UI, content script, service worker, and Web Worker run the full `latex2arxiv` pipeline via Pyodide against an open Overleaf project. The Pyodide runtime + the four packages it ships are vendored under `pyodide/` (~13 MB) so the extension package is self-contained per MV3 remote-code policy; every bundled wheel and runtime file is sha256-pinned and re-verified in CI.

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
| `latex2arxiv-*.whl` | This project's own pipeline |
| `bibtexparser-*.whl` | Used by `pipeline/bibtex.py`; PyPI ships sdist only, and micropip cannot build sdists in-browser |
| `pyparsing-*.whl` | Transitive dep of `bibtexparser` |

Pillow, PyYAML, `regex`, and `micropip` ship under `pyodide/` alongside the runtime so `indexURL` resolves them locally — no network at first install.

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

## Vendored Pyodide

`pyodide/` holds a pinned subset of the Pyodide 0.29.4 release tarball: the runtime core plus the four packages our pipeline transitively needs. `pyodide/integrity.json` records sha256 for every file; `tests/vendored-integrity.test.mjs` re-verifies in CI.

To refresh after a Pyodide bump:

```sh
# from this directory
./scripts/vendor-pyodide.sh
```

The script is idempotent: a no-op if `integrity.json` already verifies.

Only the four wheels the pipeline transitively needs (`micropip`, `pillow`, `pyyaml`, `regex`) are vendored. The bundled `pyodide-lock.json` references many more packages — if a future `latex2arxiv` release pulls another Pyodide-managed dep, add the wheel filename to `PKG_WHEELS` in `scripts/vendor-pyodide.sh` and re-run the script.

Pyodide is © its contributors and distributed under the [Mozilla Public License 2.0](https://github.com/pyodide/pyodide/blob/main/LICENSE).

## Permissions

| Permission | Why |
|---|---|
| `host_permissions: https://www.overleaf.com/*` | Same-origin fetch of the project zip; content-script injection |
| `permissions: downloads` | Save the output zip via `chrome.downloads.download` |
| `permissions: storage` | `chrome.storage.session` tracks `downloadId → blob URL` so the service worker can revoke the URL after the download lands |

No `<all_urls>`, no `tabs`, no `cookies`, no `nativeMessaging`, no `webRequest`. Reviewed for narrowness.

## Privacy

The extension is a thin client: project bytes go from the Overleaf tab to the in-browser Pyodide runtime and back to the user's chosen download path. Nothing is sent to a server we operate. The Pyodide runtime and every bundled wheel ship inside the extension package — there is no third-party CDN call at runtime.
