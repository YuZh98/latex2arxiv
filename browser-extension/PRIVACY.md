# Privacy policy — latex2arxiv for Overleaf

_Last updated: 2026-05-29_

This extension processes your LaTeX project entirely inside your own browser.
**It does not send your project, your code, your manuscript, your account
information, or any usage telemetry to the extension author or to any third
party.**

## What the extension does

When you click **Validate** or **Clean for arXiv** on an Overleaf project
page, the extension:

1. Reads the current project's identifier from the page URL
   (`https://www.overleaf.com/project/<id>`).
2. Asks Overleaf for the project zip on your behalf, using the session
   cookie you are already authenticated with. This request goes from
   your browser to `overleaf.com` — no other server is contacted.
3. Runs the latex2arxiv pipeline locally inside a Pyodide WebAssembly
   runtime that ships inside the extension package. No network call leaves
   your machine during this step.
4. For **Clean for arXiv**, writes the cleaned zip to your computer through
   the standard Chrome download dialog.

The latex2arxiv pipeline itself is open source:
<https://github.com/YuZh98/latex2arxiv>.

## What the extension stores

- **`chrome.storage.local`** — three small values that describe the panel
  layout: whether the panel is expanded or collapsed, its top offset in
  pixels, and its height in pixels. About 30 bytes. Persists until you
  uninstall the extension or clear extension storage. Not shared with any
  server.
- **`chrome.storage.session`** — a short-lived mapping of in-flight
  download IDs to blob URLs, used to revoke each blob URL after the
  matching file finishes downloading. Cleared when you close the browser.

Neither store contains the contents of your project, your name, your email,
your Overleaf account information, or any other personal data.

## What the extension does NOT do

- It does not send your LaTeX source, your figures, your bibliography, or
  any other project content anywhere.
- It does not record analytics, usage statistics, click events, or error
  reports.
- It does not load remote code at runtime. The Pyodide WebAssembly runtime
  and the Python wheels it loads are bundled inside the extension package
  and verified against pinned SHA-256 hashes on install.
- It does not request `<all_urls>`, `tabs`, `cookies`, `webRequest`,
  `nativeMessaging`, `history`, or `bookmarks`. The only host permission
  it requests is `https://www.overleaf.com/*`, and that permission exists
  solely so the extension can fetch the project zip you asked it to
  process.

## Permissions used

| Permission | Why |
|---|---|
| `downloads` | Save the cleaned zip to your computer through the standard Chrome download dialog. |
| `storage` | Remember the panel's collapsed/expanded state and position across reloads (`chrome.storage.local`); track in-flight download IDs so blob URLs can be revoked (`chrome.storage.session`). |
| `offscreen` | Host the Pyodide WebAssembly runtime in an extension-private offscreen document. Required because Overleaf's content-security policy refuses to spawn workers from the extension's URL. |
| `host_permissions: https://www.overleaf.com/*` | Fetch the current project zip on your behalf using your already-authenticated Overleaf session. |

## Children's privacy

The extension is not directed at children and does not collect data of any
kind, so there is nothing further to disclose under children's privacy
regulations.

## Changes

If this policy changes, the new version will be committed to the
[`PRIVACY.md`](https://github.com/YuZh98/latex2arxiv/blob/main/browser-extension/PRIVACY.md)
file in the repository above, and the version in the Chrome Web Store
listing will be updated accordingly.

## Contact

Open an issue at <https://github.com/YuZh98/latex2arxiv/issues> for any
question about this policy or about the extension's behavior.
