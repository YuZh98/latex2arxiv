// Service worker. Sole responsibility: dispatch chrome.downloads.download for
// the output zip. The content script builds the Blob URL (chrome.runtime
// .sendMessage uses JSON serialization, which would corrupt a Uint8Array)
// and passes only the URL string here.
//
// v0.1.1 follow-up:
//   1. Smoke-test in a real Chrome that content-script-created blob URLs
//      resolve from the service-worker process. The blob registry has been
//      per-renderer historically; if MV3 breaks the cross-process resolve,
//      fall back to fetching the blob in the content script, converting to
//      an ArrayBuffer, and passing a data: URL.
//   2. Reclaim the blob URL after the download finishes. Listen on
//      chrome.downloads.onChanged for state === "complete"/"interrupted",
//      then chrome.tabs.sendMessage back to the content script which calls
//      URL.revokeObjectURL. Without that, repeated "Clean" presses leak
//      one multi-MB blob per run until the page tears down.

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "download" && typeof msg.url === "string") {
    chrome.downloads.download(
      {
        url: msg.url,
        filename: msg.suggestedFilename || "paper-arxiv.zip",
        saveAs: true,
      },
      (downloadId) => {
        // Note: do NOT revoke the URL here. Chrome streams the download
        // asynchronously from the blob URL; revoking immediately can
        // truncate or fail the download. The URL lives until the content
        // script's page context tears down.
        sendResponse({ downloadId, error: chrome.runtime.lastError?.message });
      },
    );
    return true;
  }
  return false;
});
