// Service worker. Sole responsibility: dispatch chrome.downloads.download for
// the output zip. The content script builds the Blob URL (chrome.runtime
// .sendMessage uses JSON serialization, which would corrupt a Uint8Array)
// and passes only the URL string here.

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
