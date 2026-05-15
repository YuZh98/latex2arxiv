# VS Code Extension Icon — Design Spec

**Date:** 2026-05-15
**Target:** `vscode-extension/icon.{svg,png}` for VS Code Marketplace publish (v1.0.0 release)
**Branch:** `feat/vscode-icon` (off `main`)

## Purpose

The latex2arxiv VS Code extension currently has no committed icon. The Marketplace listing requires a 128×128 PNG; without one, the listing falls back to a generic placeholder, hurting discoverability and trust at first impression. This icon is one of the blockers for the v1.0.0 release.

## Concept

A document with syntax-highlighted LaTeX command names, stamped bottom-right with an arXiv-red circular checkmark badge. The icon communicates:

- **What the extension validates:** LaTeX source (the dark page reads as an editor pane; the colored `\command` lines are unambiguously LaTeX to anyone who has written it)
- **Result of the extension:** a "passed" stamp (the checkmark)
- **Destination context:** arXiv (the badge fill is Cornell red, arXiv's signature colour)

The arXiv-red badge intentionally inverts the universal "red = error" convention; the *shape* is a checkmark, so the pass semantic survives, and the *colour* ties the extension visually to its destination without requiring an arXiv wordmark or logo (avoiding trademark concerns).

## Composition

128×128 square, opaque white background. Two foreground elements:

1. **Document (dark editor page)** — rounded rectangle, 64×84 (about one-third of the canvas), top-left biased, leaving room for the badge bottom-right. Contains four left-aligned text lines styled as syntax-highlighted LaTeX source.
2. **Badge (arXiv-red ✓)** — circle, radius 22, centred at (91, 91). Overlaps the document's bottom-right corner for a "stamp" feel. 2 px white stroke lifts the badge off the document edge and yields a 14 px visual margin on the right and bottom.

Margins are generous (≥14 px on all sides) so platforms that mask icons with rounded corners do not clip content.

## Colour palette

| Element | Colour | Note |
|---|---|---|
| Canvas background | `#ffffff` | Marketplace requires opaque |
| Document body | `#3f3f46` (zinc-700) | Editor-pane dark, not pure black |
| `\title` line | `#a78bfa` (violet-400) | Keyword purple, VS Code Dark+ adjacent |
| `\section` line | `#fbbf24` (amber-400) | Function/identifier yellow |
| `\input` line | `#67e8f9` (cyan-300) | Import/path cyan |
| `\cite` line | `#86efac` (green-300) | Reference green |
| Badge fill | `#b31b1b` | Cornell red / arXiv signature |
| Checkmark stroke | `#ffffff` | High contrast on red |
| Badge stroke (optional) | `#ffffff` 2 px | Lifts badge off document |

Colours chosen to evoke syntax highlighting without committing to a specific named theme. The set is drawn from VS Code Dark+ family palettes.

## Typography (in-SVG `<text>`)

- Family: `Menlo, ui-monospace, Consolas, monospace` (declared with fallbacks; no external font file).
- Size: 11 px.
- Weight: 600 (semibold).
- Lines: literal LaTeX commands rendered as `\title`, `\section`, `\input`, `\cite`.

The commands are chosen to be both recognisable to any LaTeX user and short enough to fit within the document at small icon sizes.

## Files

### `vscode-extension/icon.svg`

Hand-coded SVG, single file, vector source. Replaces the existing uncommitted `icon.svg` (page-stack design, not committed). The replacement is wholesale; no history is lost.

### `vscode-extension/icon.png`

128×128 PNG, generated from `icon.svg` via `rsvg-convert` (librsvg). Committed alongside the SVG. This is the file referenced by Marketplace.

### `vscode-extension/package.json`

Adds one field:

```json
"icon": "icon.png"
```

## Build pipeline

PNG generation chosen: **`rsvg-convert`** (from `librsvg`, installed via `brew install librsvg`). Rationale: one-shot CLI conversion, no extra `node_modules` weight in the published extension, no JS dependency to keep current. Alternative `sharp` (npm devDependency wired into a script) was considered and rejected for adding ~20 MB of transitive deps for a job that runs maybe twice a year.

Command (run manually when the icon changes; commit both files):

```sh
rsvg-convert -w 128 -h 128 vscode-extension/icon.svg -o vscode-extension/icon.png
```

This is not wired into CI or `npm run` scripts — the icon does not change often, and the SVG → PNG step is deterministic and trivial to re-run manually.

## Acceptance criteria

The icon ships when all of the following are true:

1. SVG renders identically in Chrome, Firefox, and Safari (no font fallback surprises — fonts declared with web-safe fallbacks, no external font file).
2. PNG `icon.png` size <30 KB (Marketplace soft preference).
3. At 16×16, the silhouette parses: colour stripes on a dark rectangle plus a red dot are still visible and distinct.
4. `vsce package` (run in `vscode-extension/`) succeeds with the new `package.json` and includes `icon.png` in the resulting `.vsix`.
5. `vsce ls` (or unzipping the `.vsix`) confirms `icon.png` is bundled.

## Non-goals (deferred)

- Dark-theme variant. Marketplace uses a single icon across themes.
- Animated / Lottie version.
- Adaptive icon (per-VS Code-theme background).
- Wiring SVG → PNG into CI.
- Changes to extension status-bar glyphs (those are codicons, not the package icon).

## Rollout

1. Author `icon.svg`.
2. Generate `icon.png` via `rsvg-convert`.
3. Add `"icon": "icon.png"` to `vscode-extension/package.json`.
4. Commit on a new branch `feat/vscode-icon` cut from `main` (the current `docs/vscode-status` branch is reserved for the extension-status doc update; the icon work stays separate).
5. PR → merge → use in v1.0.0 Marketplace publish.

## Out of scope for this design

The following are handled later, not part of the icon spec:

- `vsce login` / publisher account setup.
- Marketplace publish workflow itself.
- Extension version bump (`vscode-extension/package.json` `version` field).
- Repo-level `README.md` updates that link the published Marketplace listing.
