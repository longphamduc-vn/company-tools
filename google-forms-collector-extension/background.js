// Google Forms Question Collector - Background Service Worker

chrome.runtime.onInstalled.addListener(() => {
  // Set default settings if not exists
  chrome.storage.local.get(['settings'], (res) => {
    if (!res.settings) {
      chrome.storage.local.set({
        settings: {
          autoAccumulate: true,
          showFloatingWidget: true,
          bypassRequiredForAutoCrawl: true,
          exportFormat: 'text',
          optionPrefix: 'letter' // 'letter' (A, B, C, D) or 'number' (1, 2, 3, 4)
        }
      });
    }
  });
});

// Listen for messages from content scripts and popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'UPDATE_BADGE') {
    const count = request.count;
    const tabId = sender.tab ? sender.tab.id : undefined;
    
    if (count > 0) {
      chrome.action.setBadgeText({ text: String(count), tabId });
      chrome.action.setBadgeBackgroundColor({ color: '#673AB7', tabId });
    } else {
      chrome.action.setBadgeText({ text: '', tabId });
    }
    sendResponse({ status: 'ok' });
    return true;
  }

  if (request.action === 'DOWNLOAD_FILE') {
    chrome.downloads.download({
      url: request.url,
      filename: request.filename,
      saveAs: true
    }, (downloadId) => {
      sendResponse({ status: 'ok', downloadId });
    });
    return true; // Keep channel open for async response
  }
});
