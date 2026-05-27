# latex2arxiv for Overleaf

Chrome extension that runs [`latex2arxiv`](https://github.com/YuZh98/latex2arxiv) against an open Overleaf project: validates arXiv readiness, surfaces diagnostics in-page, and downloads a clean submission zip — no local install required.

## Status

**v0.1 scaffold — not yet store-ready.** The UI, content script, service worker, and Web Worker shell are wired end-to-end against the Overleaf project download endpoint. Two gates before Chrome Web Store submission:

1. The Pyodide-hosted pipeline is stubbed; full conversion lands in v0.1.1 once the upstream wheel ships the cross-platform regex-timeout fix.
2. Pyodide is currently loaded from the jsDelivr CDN. MV3 prohibits remotely-hosted code from extension contexts at review time, so v0.1.1 must also bundle the Pyodide runtime into the extension package.

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

No build step in v0.1. Source files are loaded as-is by the browser.

## Permissions

| Permission | Why |
|---|---|
| `host_permissions: https://www.overleaf.com/*` | Same-origin fetch of the project zip; content-script injection |
| `permissions: downloads` | Save the output zip via `chrome.downloads.download` |

No `<all_urls>`, no `tabs`, no `cookies`, no `nativeMessaging`, no `storage`, no `webRequest`. Reviewed for narrowness.

## Privacy

The extension is a thin client: project bytes go from the Overleaf tab to the in-browser Pyodide runtime and back to the user's chosen download path. Nothing is sent to a server we operate. Pyodide assets are loaded from the official jsDelivr CDN.
