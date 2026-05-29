// Service worker. Three responsibilities:
//   1. Spawn and manage the offscreen document that hosts the Pyodide worker.
//      Worker cannot live in the content script (overleaf.com's CSP refuses
//      chrome-extension:// workers) and cannot live in the SW (MV3 SW
//      lifecycle is too aggressive). Offscreen is the MV3-official answer.
//   2. Relay run requests from the content script to the offscreen document,
//      then forward the result (or any error) back to the originating tab.
//   3. Dispatch chrome.downloads.download for the output blob URL the
//      offscreen produced, and route the revoke handshake back through the
//      offscreen after the download lands.
//
// Singleton offscreen. Chrome allows only one offscreen document per
// extension; `creatingOffscreen` is a module-level Promise that all
// concurrent ensureOffscreen() callers await so a SW eviction + re-wake
// race cannot trigger "Only a single offscreen document may be created."

import { dispatchRevoke } from "./lib/revoke.mjs";
import { makeOffscreenManager } from "./lib/offscreen-lifecycle.mjs";

const OFFSCREEN_PATH = "offscreen.html";
const OFFSCREEN_REASONS = ["WORKERS"];
const OFFSCREEN_JUSTIFICATION = "Host the Pyodide worker that runs the latex2arxiv pipeline.";

const ensureOffscreen = makeOffscreenManager({
  hasDocument: () => chrome.offscreen.hasDocument(),
  createDocument: () =>
    chrome.offscreen.createDocument({
      url: OFFSCREEN_PATH,
      reasons: OFFSCREEN_REASONS,
      justification: OFFSCREEN_JUSTIFICATION,
    }),
});

const sessionStore = {
  get: (key) => chrome.storage.session.get(key),
  set: (obj) => chrome.storage.session.set(obj),
  remove: (key) => chrome.storage.session.remove(key),
};

// dispatchRevoke's callback shape takes (tabId, msg). The offscreen has no
// tabId, so this adapter ignores the first argument and broadcasts via
// chrome.runtime.sendMessage — the offscreen picks it up by message type.
const messageOffscreen = (_tabId, msg) =>
  chrome.runtime.sendMessage({ type: "l2a-revoke", url: msg.url });

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== "l2a-run-request") return false;
  (async () => {
    try {
      await ensureOffscreen();
      const result = await chrome.runtime.sendMessage({ type: "l2a-run", payload: msg.payload });
      if (result && result.error) {
        sendResponse({ error: result.error });
        return;
      }
      if (result && result.blobUrl) {
        // Clean mode produced an output. Hand the blob URL to chrome.downloads.
        chrome.downloads.download(
          {
            url: result.blobUrl,
            filename: result.filename || "paper-arxiv.zip",
            saveAs: true,
          },
          (downloadId) => {
            const lastError = chrome.runtime.lastError;
            if (downloadId === undefined) {
              // saveAs dismissed — revoke the URL immediately so the offscreen
              // does not pin the bytes for the rest of the session.
              chrome.runtime.sendMessage({ type: "l2a-revoke", url: result.blobUrl }).catch(() => {});
              sendResponse({
                diagnostics: result.diagnostics,
                mainTex: result.mainTex,
                summary: result.summary,
                guideText: result.guideText,
                downloadDispatched: false,
                error: lastError && lastError.message,
              });
              return;
            }
            sessionStore.set({ [String(downloadId)]: { url: result.blobUrl } });
            sendResponse({
              diagnostics: result.diagnostics,
              mainTex: result.mainTex,
              summary: result.summary,
              guideText: result.guideText,
              downloadDispatched: true,
            });
          },
        );
        return;
      }
      // Validate mode (no output zip) — just relay diagnostics.
      sendResponse({
        diagnostics: result.diagnostics,
        mainTex: result.mainTex,
        summary: result.summary,
        guideText: result.guideText,
        downloadDispatched: false,
      });
    } catch (err) {
      sendResponse({ error: err && err.message ? String(err.message) : String(err) });
    }
  })();
  return true;
});

chrome.downloads.onChanged.addListener((change) => {
  // Best-effort: downloads.onChanged has no waitUntil API, so an in-flight
  // dispatchRevoke can be cut short if the SW is evicted between the storage
  // read and the offscreen message. Unlikely in practice — the SW just
  // handled the download and is still warm — and a missed revoke only
  // re-leaks one blob.
  dispatchRevoke({
    downloadId: change.id,
    change,
    sessionStore,
    messageTab: messageOffscreen,
  });
});
