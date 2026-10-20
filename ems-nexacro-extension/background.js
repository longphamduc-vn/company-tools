/**
 * background.js - Manifest V3 Background Service Worker
 * Manages runtime states, badge updates, and lifecycle events.
 */

chrome.runtime.onInstalled.addListener(() => {
  chrome.action.setBadgeText({ text: '' });
  chrome.action.setBadgeBackgroundColor({ color: '#2563EB' });
  console.info('[NexacroServiceWorker] Extension installed.');
});

// Update badge count dynamically
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === 'TRAFFIC_COUNT_UPDATED') {
    const count = message.count || 0;
    const text = count > 0 ? (count > 99 ? '99+' : String(count)) : '';
    chrome.action.setBadgeText({ text: text });
    sendResponse({ success: true });
  }
  return true;
});