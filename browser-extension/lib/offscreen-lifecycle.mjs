// Offscreen-document singleton helper. Chrome allows exactly one offscreen
// document per extension; concurrent createDocument calls fail with
// "Only a single offscreen document may be created." This helper wraps the
// has/create dance in a module-level Promise so multiple callers (e.g., two
// SW message handlers waking the SW at nearly the same time) share one
// creation call and resolve together.
//
// Side effects are routed through injected callbacks so a Node:test can verify
// the singleton behavior with in-memory stubs of chrome.offscreen.*.

export function makeOffscreenManager({ hasDocument, createDocument }) {
  let creating = null;
  return async function ensureOffscreen() {
    if (await hasDocument()) return;
    if (!creating) {
      creating = createDocument().finally(() => {
        creating = null;
      });
    }
    return creating;
  };
}
