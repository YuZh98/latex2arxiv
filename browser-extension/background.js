// Service worker. Sole responsibility: dispatch chrome.downloads.download for
// the output zip. The content script cannot call the downloads API directly.

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "download") {
    const blob = new Blob([msg.zipBytes], { type: "application/zip" });
    const url = URL.createObjectURL(blob);
    chrome.downloads.download(
      {
        url,
        filename: msg.suggestedFilename || "paper-arxiv.zip",
        saveAs: true,
      },
      (downloadId) => {
        URL.revokeObjectURL(url);
        sendResponse({ downloadId, error: chrome.runtime.lastError?.message });
      },
    );
    return true;
  }
  return false;
});
