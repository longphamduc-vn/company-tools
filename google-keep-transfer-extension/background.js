// Background Service Worker for Google Keep File Transfer
chrome.runtime.onInstalled.addListener(() => {
  console.log("Google Keep Text File Transfer Extension installed successfully.");
  // Initialize default settings if not exists
  chrome.storage.local.get(["chunkSize", "delayMs", "prefixTag"], (res) => {
    const defaults = {};
    if (!res.chunkSize) defaults.chunkSize = 10000;
    if (!res.delayMs) defaults.delayMs = 800;
    if (!res.prefixTag) defaults.prefixTag = "[KeepTransfer]";
    if (Object.keys(defaults).length > 0) {
      chrome.storage.local.set(defaults);
    }
  });
});

// Listener for background download requests (data URI or blob url)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "DOWNLOAD_FILE") {
    const { filename, content, mimeType = "text/plain;charset=utf-8" } = message;
    try {
      const blob = new Blob([content], { type: mimeType });
      const reader = new FileReader();
      reader.onloadend = function () {
        const dataUrl = reader.result;
        chrome.downloads.download({
          url: dataUrl,
          filename: filename || "keep_merged_export.txt",
          saveAs: true
        }, (downloadId) => {
          if (chrome.runtime.lastError) {
            sendResponse({ success: false, error: chrome.runtime.lastError.message });
          } else {
            sendResponse({ success: true, downloadId });
          }
        });
      };
      reader.readAsDataURL(blob);
      return true; // Keep channel open for async response
    } catch (err) {
      sendResponse({ success: false, error: err.message });
    }
  }

  if (message.type === "OPEN_KEEP_TAB") {
    chrome.tabs.query({ url: "*://keep.google.com/*" }, (tabs) => {
      if (tabs.length > 0) {
        chrome.tabs.update(tabs[0].id, { active: true });
        chrome.windows.update(tabs[0].windowId, { focused: true });
        sendResponse({ success: true, tabId: tabs[0].id });
      } else {
        chrome.tabs.create({ url: "https://keep.google.com/" }, (newTab) => {
          sendResponse({ success: true, tabId: newTab.id });
        });
      }
    });
    return true;
  }
});
