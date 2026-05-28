// Blob URL revoke logic for the download service worker. Kept pure so the
// SW glue stays thin and the decision logic is unit-testable without a
// chrome.* shim. Real Chrome wiring lives in background.js.

// Decide whether a chrome.downloads.onChanged delta is a terminal state that
// means the streamed download is finished and the source blob URL can now be
// revoked safely. Returns false on transient state changes (in_progress,
// pause/resume) and on deltas with no state field.
export function planRevoke(change) {
  const current = change && change.state && change.state.current;
  return current === "complete" || current === "interrupted";
}

// Orchestrator. Looks up the (tabId, url) recorded when the download was
// started, messages the originating tab to revoke the URL, and clears the
// session entry. Side effects are routed through injected callbacks so a
// node:test can verify behavior with in-memory stubs.
export async function dispatchRevoke({ downloadId, change, sessionStore, messageTab }) {
  if (!planRevoke(change)) return;
  const key = String(downloadId);
  const stored = await sessionStore.get(key);
  const entry = stored[key];
  if (!entry) return;
  // Best-effort: try to message the tab so it can revoke. If the page has torn
  // down, swallow the failure — clearing the entry is still correct because
  // the URL dies with the page either way.
  try {
    await messageTab(entry.tabId, { type: "revoke", url: entry.url });
  } catch (_) {
    // Tab gone; nothing to do.
  }
  await sessionStore.remove(key);
}
