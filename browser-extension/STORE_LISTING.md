# Chrome Web Store listing — copy-paste ready

Paste each field below into the matching form input at
<https://chrome.google.com/webstore/devconsole>.

## Item details

### Name
```
latex2arxiv for Overleaf
```

### Summary (132 characters max — currently 79)
```
arXiv pre-flight validation and one-click zip cleaning, in the Overleaf editor.
```

### Category
**Developer Tools** (primary). Productivity is an acceptable alternative.

### Language
English (United States)

### Detailed description

```
latex2arxiv adds an arXiv pre-flight check and a one-click "Clean for arXiv" button to the Overleaf editor. Every check runs locally in your browser — your manuscript never leaves your machine.

What it does
------------

• Validate: run the same pre-flight checks arXiv runs (forbidden packages, missing .bbl, oversized figures, hidden files, deprecated commands) and surface every problem in a side panel, without producing a zip.

• Clean for arXiv: strip TODO comments, remove unreferenced figures, flatten \input/\subfile, optionally downsize images, and emit a clean .zip ready for arXiv upload.

• Upload guide: optionally produce a short .txt walk-through (paper title, authors, abstract, page count, kept-files list) you can save alongside the zip.

• Main file override: pick a different .tex when the auto-detect heuristic picks the wrong one. A bare filename like "paper" works the same as "paper.tex".

How it works (privacy)
----------------------

The entire pipeline runs inside an offscreen Pyodide WebAssembly runtime that ships inside the extension package. Your LaTeX source, your figures, and your bibliography never leave your browser. No analytics, no telemetry, no third-party servers.

The only network call the extension makes is to overleaf.com — to fetch the current project zip on your behalf using the session you are already signed in to. The cleaned zip is saved to your computer through the standard Chrome download dialog.

Open source
-----------

The pipeline is open source under the MIT license:
https://github.com/YuZh98/latex2arxiv

Issue tracker, full source for the extension and the underlying CLI:
https://github.com/YuZh98/latex2arxiv

Privacy policy
--------------

https://github.com/YuZh98/latex2arxiv/blob/main/browser-extension/PRIVACY.md
```

## Privacy

### Single-purpose description (required)
```
Validate and clean LaTeX projects for arXiv submission, directly inside the Overleaf editor, without sending project contents off the user's machine.
```

### Permission justifications

Paste each into the matching field on the **Privacy practices** tab.

#### `downloads`
```
Used to save the cleaned arXiv-ready .zip to the user's computer through the standard Chrome download dialog after the user clicks "Clean for arXiv". The extension does not download anything except files the user has explicitly asked to produce.
```

#### `storage`
```
chrome.storage.local persists the panel layout (collapsed-or-expanded state, vertical position, height) so the user's preferred layout survives across page refreshes. About 30 bytes; no personal data, no project content. chrome.storage.session holds a short-lived mapping of in-flight downloadId to blob URL so each download blob can be revoked after Chrome finishes writing the file; cleared on browser session end.
```

#### `offscreen`
```
chrome.offscreen.createDocument hosts the Pyodide WebAssembly runtime that runs the latex2arxiv pipeline. The offscreen document is required because Overleaf's content-security policy refuses to spawn Web Workers from the extension's chrome-extension:// origin in a content-script context; an offscreen document owns its own CSP and bypasses the restriction. No DOM is rendered to the user from the offscreen document.
```

#### `host_permissions: https://www.overleaf.com/*`
```
Used to fetch the current Overleaf project zip on the user's behalf, using the session cookie they are already authenticated with. The extension never reads any other site. No request leaves the user's browser to any host other than overleaf.com, and even those requests only happen when the user explicitly clicks Validate or Clean for arXiv.
```

### Remote code use (required)
**No.** Select "No, I am not using remote code."

Justification (paste if asked):
```
The Pyodide WebAssembly runtime (~13 MB), every Python wheel the pipeline loads, and the Python entrypoint script all ship inside the extension package. The contents of pyodide/ and wheels/ are verified against pinned SHA-256 hashes at install time (browser-extension/pyodide/integrity.json and browser-extension/wheels/integrity.json). The extension does not download or execute any code that is not part of the published package.
```

### Data usage disclosures

On the **Privacy practices** form, declare:

- **Personally identifiable information:** No
- **Health information:** No
- **Financial and payment information:** No
- **Authentication information:** No
- **Personal communications:** No
- **Location:** No
- **Web history:** No
- **User activity:** No
- **Website content:** **Yes** — the extension reads the LaTeX project the user has opened in Overleaf, processes it locally, and never transmits it anywhere.

Then check the three certifications:
- "I do not sell or transfer user data to third parties …"
- "I do not use or transfer user data for purposes that are unrelated to my item's single purpose."
- "I do not use or transfer user data to determine creditworthiness or for lending purposes."

## Distribution

### Visibility
**Public** (recommended) — listed in the Chrome Web Store and discoverable by search.

### Regions
**All regions** (recommended).

### Pricing
Free.

## Assets to upload (you must produce these on your machine)

| Asset | Size | Required | Notes |
|---|---|---|---|
| Icon | 128 × 128 PNG | ✓ | already in repo: `browser-extension/icon.png` |
| Screenshots | 1280 × 800 (preferred) or 640 × 400 | ≥ 1, ≤ 5 | screen-capture an active Overleaf project with the panel expanded; aim for 2–3 |
| Small promo tile | 440 × 280 PNG | optional | improves discovery in the Web Store; can skip for first submission |
| Marquee promo tile | 1400 × 560 PNG | optional | only used if the extension is featured |

### Suggested screenshots (2–3)
1. The panel expanded over an Overleaf editor with diagnostics listed (after a Validate run that finds at least one issue).
2. The panel after a successful Clean for arXiv run, with the green "Upload guide ready" row and the Save-as-.txt button.
3. The pill collapsed on the right edge of the editor — shows the minimized state.

## Package

Build the upload zip with:

```
./browser-extension/scripts/build-store-zip.sh
```

The zip lands at `browser-extension/dist/latex2arxiv-overleaf-<version>.zip`.
It excludes `tests/`, `scripts/`, `node_modules/`, `package*.json`,
`PRIVACY.md`, `STORE_LISTING.md`, and the `dist/` folder itself.

## After submission

Chrome Web Store review typically takes 1–3 business days for a new
extension that does not request `<all_urls>`. If the reviewer flags a
permission, link this `STORE_LISTING.md` and the `PRIVACY.md` from your
reply.
