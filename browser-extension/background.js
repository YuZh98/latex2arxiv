// Service worker. Two responsibilities:
//   1. Dispatch chrome.downloads.download for the output zip that the content
//      script built as a blob URL. (chrome.runtime.sendMessage uses JSON
//      serialization, which would corrupt a Uint8Array, so the content script
//      builds the Blob URL on its side and passes only the URL string here.)
//   2. After the download lands, route a "revoke" message back to the
//      originating tab so it can release the blob URL. Without this the
//      content script accumulates one multi-MB blob per "Clean" press.
//
// MV3 SW lifecycle note: this worker terminates after ~30s idle. The
// (downloadId → {tabId, url}) bookkeeping lives in chrome.storage.session so
// it survives restarts within the browser session. The onChanged listener
// re-registers automatically when the SW wakes.

import { dispatchRevoke } from "./lib/revoke.mjs";

const sessionStore = {
  get: (key) => chrome.storage.session.get(key),
  set: (obj) => chrome.storage.session.set(obj),
  remove: (key) => chrome.storage.session.remove(key),
};

const messageTab = (tabId, msg) => chrome.tabs.sendMessage(tabId, msg);

function revokeNow(tabId, url) {
  // User dismissed the saveAs dialog: the download never started, no onChanged
  // will ever fire, so revoke immediately or the URL leaks for the page's life.
  chrome.tabs.sendMessage(tabId, { type: "revoke", url }).catch(() => {});
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== "download" || typeof msg.url !== "string") return false;
  const tabId = sender.tab && sender.tab.id;
  chrome.downloads.download(
    {
      url: msg.url,
      filename: msg.suggestedFilename || "paper-arxiv.zip",
      saveAs: true,
    },
    (downloadId) => {
      const err = chrome.runtime.lastError;
      if (downloadId === undefined) {
        // saveAs dialog dismissed or download refused. Revoke and bail.
        if (tabId !== undefined) revokeNow(tabId, msg.url);
        sendResponse({ downloadId: null, error: err && err.message });
        return;
      }
      if (tabId !== undefined) {
        sessionStore.set({ [String(downloadId)]: { tabId, url: msg.url } });
      }
      sendResponse({ downloadId, error: err && err.message });
    },
  );
  return true;
});

chrome.downloads.onChanged.addListener((change) => {
  // Best-effort: downloads.onChanged has no waitUntil API, so an in-flight
  // dispatchRevoke can be cut short if the SW is evicted between the storage
  // read and the tab message. Unlikely in practice — the SW just handled the
  // download and is still warm — and a missed revoke only re-leaks one blob.
  dispatchRevoke({
    downloadId: change.id,
    change,
    sessionStore,
    messageTab,
  });
});
