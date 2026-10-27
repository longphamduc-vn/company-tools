// Google Keep Text File Transfer - Popup Logic (English Version)

document.addEventListener("DOMContentLoaded", async () => {
  // Elements
  const connectionBadge = document.getElementById("connectionBadge");
  const statusDot = connectionBadge.querySelector(".status-dot");
  const statusText = document.getElementById("statusText");
  const keepTabWarning = document.getElementById("keepTabWarning");
  const openKeepBtn = document.getElementById("openKeepBtn");
  const popoutBtn = document.getElementById("popoutBtn");

  // Tabs
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  // Upload Tab
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const togglePasteBox = document.getElementById("togglePasteBox");
  const pasteContainer = document.getElementById("pasteContainer");
  const pasteFileName = document.getElementById("pasteFileName");
  const pasteTextInput = document.getElementById("pasteTextInput");

  const fileCard = document.getElementById("fileCard");
  const fileNameDisplay = document.getElementById("fileNameDisplay");
  const fileMetaDisplay = document.getElementById("fileMetaDisplay");
  const clearFileBtn = document.getElementById("clearFileBtn");
  const chunkCountDisplay = document.getElementById("chunkCountDisplay");
  const chunkSizeDisplay = document.getElementById("chunkSizeDisplay");
  const createConfigNoteCheckbox = document.getElementById("createConfigNoteCheckbox");

  const uploadProgressBox = document.getElementById("uploadProgressBox");
  const progressStatusLabel = document.getElementById("progressStatusLabel");
  const progressPercentLabel = document.getElementById("progressPercentLabel");
  const progressBarFill = document.getElementById("progressBarFill");
  const currentChunkCount = document.getElementById("currentChunkCount");
  const totalChunkCount = document.getElementById("totalChunkCount");
  const charVerifyStatus = document.getElementById("charVerifyStatus");

  const logConsole = document.getElementById("logConsole");
  const logEntries = document.getElementById("logEntries");
  const clearLogBtn = document.getElementById("clearLogBtn");

  const startUploadBtn = document.getElementById("startUploadBtn");
  const transferControlGroup = document.getElementById("transferControlGroup");
  const pauseUploadBtn = document.getElementById("pauseUploadBtn");
  const resumeUploadBtn = document.getElementById("resumeUploadBtn");
  const focusKeepTabBtn = document.getElementById("focusKeepTabBtn");
  const cancelUploadBtn = document.getElementById("cancelUploadBtn");
  const autoClosePopupCheckbox = document.getElementById("autoClosePopupCheckbox");

  // Download Tab
  const quickScanBtn = document.getElementById("quickScanBtn");
  const deepScanBtn = document.getElementById("deepScanBtn");
  const scanFilterInput = document.getElementById("scanFilterInput");
  const scanStatusAlert = document.getElementById("scanStatusAlert");
  const scanStatusMsg = document.getElementById("scanStatusMsg");
  const cancelScanBtn = document.getElementById("cancelScanBtn");
  const detectedFilesCount = document.getElementById("detectedFilesCount");
  const refreshFilesBtn = document.getElementById("refreshFilesBtn");
  const filesEmptyState = document.getElementById("filesEmptyState");
  const detectedFileList = document.getElementById("detectedFileList");

  // Manual Tab
  const selectAllNotesCheckbox = document.getElementById("selectAllNotesCheckbox");
  const selectedNotesCount = document.getElementById("selectedNotesCount");
  const totalScannedNotes = document.getElementById("totalScannedNotes");
  const mergeSeparatorSelect = document.getElementById("mergeSeparatorSelect");
  const notesManualList = document.getElementById("notesManualList");
  const mergeSelectedBtn = document.getElementById("mergeSelectedBtn");
  const exportAllJsonBtn = document.getElementById("exportAllJsonBtn");

  // Settings Tab
  const settingChunkSize = document.getElementById("settingChunkSize");
  const settingDelayMs = document.getElementById("settingDelayMs");
  const settingPrefix = document.getElementById("settingPrefix");
  const settingConfigPrefix = document.getElementById("settingConfigPrefix");
  const settingScrollDelay = document.getElementById("settingScrollDelay");
  const settingAutoClose = document.getElementById("settingAutoClose");
  const saveSettingsBtn = document.getElementById("saveSettingsBtn");

  // Modal Preview
  const previewModal = document.getElementById("previewModal");
  const previewModalTitle = document.getElementById("previewModalTitle");
  const previewModalBody = document.getElementById("previewModalBody");
  const closePreviewBtn = document.getElementById("closePreviewBtn");
  const copyPreviewBtn = document.getElementById("copyPreviewBtn");
  const downloadPreviewBtn = document.getElementById("downloadPreviewBtn");
  const toastContainer = document.getElementById("toastContainer");

  // Pop Out Window Handling
  const isWindowMode = window.location.search.includes("mode=window");
  if (isWindowMode && popoutBtn) {
    popoutBtn.style.display = "none";
  }

  popoutBtn.addEventListener("click", () => {
    chrome.windows.create({
      url: "popup.html?mode=window",
      type: "popup",
      width: 490,
      height: 650
    });
    window.close();
  });

  // Focus Keep Tab Button
  if (focusKeepTabBtn) {
    focusKeepTabBtn.addEventListener("click", () => {
      if (activeKeepTab) {
        chrome.tabs.update(activeKeepTab.id, { active: true });
        if (activeKeepTab.windowId) {
          chrome.windows.update(activeKeepTab.windowId, { focused: true });
        }
      }
      window.close();
    });
  }

  // Toggle Auto Close Checkbox
  if (autoClosePopupCheckbox) {
    autoClosePopupCheckbox.addEventListener("change", () => {
      const isChecked = autoClosePopupCheckbox.checked;
      if (settingAutoClose) settingAutoClose.checked = isChecked;
      chrome.storage.local.set({ autoClose: isChecked });
    });
  }

  // State
  let activeKeepTab = null;
  let activeScanPort = null;
  let currentFile = null; // { name, size, text, chunks, configNote, fileId }
  let currentSettings = {
    chunkSize: 10000,
    delayMs: 800,
    prefixTag: "[KT]",
    configPrefix: "[KT-CONFIG]",
    scrollDelay: 1200,
    autoClose: true
  };
  let scannedNotes = [];
  let detectedFileBundles = {};
  let previewCurrentData = null; // { title, filename, content }

  // Load Settings
  async function loadSettings() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["chunkSize", "delayMs", "prefixTag", "configPrefix", "scrollDelay", "autoClose"], (res) => {
        if (res.chunkSize) currentSettings.chunkSize = parseInt(res.chunkSize, 10);
        if (res.delayMs) currentSettings.delayMs = parseInt(res.delayMs, 10);
        if (res.prefixTag) currentSettings.prefixTag = res.prefixTag;
        if (res.configPrefix) currentSettings.configPrefix = res.configPrefix;
        if (res.scrollDelay) currentSettings.scrollDelay = parseInt(res.scrollDelay, 10);
        if (typeof res.autoClose !== "undefined") currentSettings.autoClose = Boolean(res.autoClose);
        else currentSettings.autoClose = true;

        settingChunkSize.value = currentSettings.chunkSize;
        settingDelayMs.value = currentSettings.delayMs;
        settingPrefix.value = currentSettings.prefixTag;
        settingConfigPrefix.value = currentSettings.configPrefix;
        settingScrollDelay.value = currentSettings.scrollDelay;
        if (settingAutoClose) settingAutoClose.checked = currentSettings.autoClose;
        if (autoClosePopupCheckbox) autoClosePopupCheckbox.checked = currentSettings.autoClose;
        chunkSizeDisplay.innerText = Number(currentSettings.chunkSize).toLocaleString();
        resolve();
      });
    });
  }

  // Toast Helper
  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerText = message;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 2800);
  }

  // Add Log Entry
  function addLog(text, type = "normal") {
    logConsole.classList.remove("hidden");
    const line = document.createElement("div");
    line.className = `log-line ${type}`;
    const time = new Date().toLocaleTimeString("en-US", { hour12: false });
    line.innerText = `[${time}] ${text}`;
    logEntries.appendChild(line);
    logEntries.scrollTop = logEntries.scrollHeight;
  }

  // Check Google Keep Connection
  async function checkKeepConnection() {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const currentTab = tabs[0];

    if (currentTab && currentTab.url && currentTab.url.includes("keep.google.com")) {
      activeKeepTab = currentTab;
      statusDot.className = "status-dot connected";
      statusText.innerText = "Keep: Connected";
      keepTabWarning.classList.add("hidden");
      return true;
    }

    const keepTabs = await chrome.tabs.query({ url: "*://keep.google.com/*" });
    if (keepTabs.length > 0) {
      activeKeepTab = keepTabs[0];
      statusDot.className = "status-dot connected";
      statusText.innerText = `Keep: Tab #${activeKeepTab.id}`;
      keepTabWarning.classList.add("hidden");
      return true;
    }

    activeKeepTab = null;
    statusDot.className = "status-dot disconnected";
    statusText.innerText = "Keep Not Found";
    keepTabWarning.classList.remove("hidden");
    return false;
  }

  // Switch to or open Google Keep
  openKeepBtn.addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "OPEN_KEEP_TAB" }, (res) => {
      setTimeout(checkKeepConnection, 600);
    });
  });

  // Tab switching
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      tabBtns.forEach((b) => b.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const targetPane = document.getElementById(targetTab);
      if (targetPane) targetPane.classList.add("active");
    });
  });

  // Ensure content script injected into Keep Tab
  async function ensureContentScriptInjected(tabId) {
    try {
      const response = await chrome.tabs.sendMessage(tabId, { action: "PING" });
      if (response && response.status === "OK") return true;
    } catch (e) {
      try {
        await chrome.scripting.executeScript({
          target: { tabId },
          files: ["content.js"]
        });
        await new Promise((r) => setTimeout(r, 250));
        return true;
      } catch (err) {
        console.error("Failed to inject content script:", err);
        return false;
      }
    }
    return true;
  }

  // Format bytes
  function formatBytes(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  // Split text into chunks
  function chunkText(text, size = 10000) {
    const chunks = [];
    let i = 0;
    while (i < text.length) {
      chunks.push(text.slice(i, i + size));
      i += size;
    }
    return chunks;
  }

  // Generate Short 6-char Unique File ID (e.g. "a9f2b1")
  function generateFileId() {
    const rand = Math.random().toString(36).substring(2, 6);
    const ts = (Date.now() % 1000000).toString(36);
    return `${ts}${rand}`.slice(0, 6);
  }

  // Prepare File for Upload
  function handleFileLoaded(fileName, fileText, fileSize) {
    const chunkSize = currentSettings.chunkSize || 10000;
    const rawChunks = chunkText(fileText, chunkSize);
    const fileId = generateFileId();
    const total = rawChunks.length;
    const padLength = String(total).length > 1 ? String(total).length : 2;
    const totalNum = String(total).padStart(padLength, "0");

    // Clean prefix: e.g. "KT"
    const prefix = (currentSettings.prefixTag || "KT").replace(/[\[\]]/g, "").trim() || "KT";

    const preparedChunks = rawChunks.map((content, idx) => {
      const partNum = String(idx + 1).padStart(padLength, "0");
      return {
        index: idx + 1,
        total: total,
        partString: partNum,
        totalString: totalNum,
        // Compact front-loaded title: [KT 01/05 #abc12] filename.ext
        // Part & ID are at the beginning so Keep card truncation never hides them
        title: `[${prefix} ${partNum}/${totalNum} #${fileId}] ${fileName}`,
        content: content,
        length: content.length
      };
    });

    // Compact config note format: [KT CFG #abc12] (5 parts) filename.ext
    const configNote = {
      title: `[${prefix} CFG #${fileId}] (${total} parts) ${fileName}`,
      content: JSON.stringify({
        transferVersion: "1.3",
        fileId: fileId,
        fileName: fileName,
        fileSize: fileSize,
        totalChunks: total,
        chunkSize: chunkSize,
        createdAt: new Date().toISOString(),
        chunks: preparedChunks.map((c) => ({
          part: c.index,
          title: c.title,
          length: c.length
        }))
      }, null, 2)
    };

    currentFile = {
      name: fileName,
      size: fileSize,
      length: fileText.length,
      chunks: preparedChunks,
      configNote: configNote,
      fileId: fileId
    };

    // Update UI
    fileNameDisplay.innerText = fileName;
    fileMetaDisplay.innerText = `${formatBytes(fileSize)} • ${fileText.length.toLocaleString()} characters`;
    chunkCountDisplay.innerText = total;
    fileCard.classList.remove("hidden");
    startUploadBtn.disabled = false;
    startUploadBtn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
      Split into ${total} Notes & Upload to Keep
    `;

    addLog(`Loaded file "${fileName}" (${formatBytes(fileSize)}, ${fileText.length.toLocaleString()} chars). Split into ${total} parts.`);
  }

  // File Input Change
  fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      handleFileLoaded(file.name, event.target.result, file.size);
    };
    reader.readAsText(file);
  });

  // Drag and Drop
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });
  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      const reader = new FileReader();
      reader.onload = (event) => {
        handleFileLoaded(file.name, event.target.result, file.size);
      };
      reader.readAsText(file);
    }
  });

  // Toggle Direct Text Paste
  togglePasteBox.addEventListener("click", () => {
    pasteContainer.classList.toggle("hidden");
    if (!pasteContainer.classList.contains("hidden")) {
      pasteTextInput.focus();
    }
  });

  pasteTextInput.addEventListener("input", () => {
    const text = pasteTextInput.value;
    if (!text.trim()) return;
    const name = pasteFileName.value.trim() || "snippet.txt";
    handleFileLoaded(name, text, new Blob([text]).size);
  });

  // Clear File Selection
  clearFileBtn.addEventListener("click", () => {
    currentFile = null;
    fileInput.value = "";
    pasteTextInput.value = "";
    fileCard.classList.add("hidden");
    startUploadBtn.disabled = true;
    startUploadBtn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
      Split File & Upload to Google Keep
    `;
    uploadProgressBox.classList.add("hidden");
    transferControlGroup.classList.add("hidden");
    startUploadBtn.classList.remove("hidden");
    addLog("Selection cleared.");
  });

  // Clear Logs
  clearLogBtn.addEventListener("click", () => {
    logEntries.innerHTML = "";
    logConsole.classList.add("hidden");
  });

  // -------------------------------------------------------------
  // AUTONOMOUS BACKGROUND TRANSFER SYNC & CONTROLS
  // -------------------------------------------------------------
  function updateTransferUI(transfer) {
    if (!transfer || transfer.state === "IDLE") {
      uploadProgressBox.classList.add("hidden");
      transferControlGroup.classList.add("hidden");
      startUploadBtn.classList.remove("hidden");
      return;
    }

    const total = (transfer.notes && transfer.notes.length) || 0;
    const current = transfer.currentIndex || 0;
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;

    uploadProgressBox.classList.remove("hidden");
    startUploadBtn.classList.add("hidden");
    transferControlGroup.classList.remove("hidden");

    progressBarFill.style.width = `${pct}%`;
    progressPercentLabel.innerText = `${pct}%`;
    currentChunkCount.innerText = current;
    totalChunkCount.innerText = total;

    if (transfer.state === "RUNNING") {
      progressStatusLabel.innerText = transfer.statusText || `Creating note [${current + 1}/${total}]...`;
      pauseUploadBtn.classList.remove("hidden");
      resumeUploadBtn.classList.add("hidden");
      charVerifyStatus.innerText = "✓ Verifying Integrity";
    } else if (transfer.state === "PAUSED") {
      progressStatusLabel.innerText = transfer.statusText || `Paused at note [${current + 1}/${total}].`;
      pauseUploadBtn.classList.add("hidden");
      resumeUploadBtn.classList.remove("hidden");
      charVerifyStatus.innerText = "⏸ Paused";
    } else if (transfer.state === "COMPLETED") {
      progressStatusLabel.innerText = "Upload Complete!";
      progressBarFill.style.width = "100%";
      progressPercentLabel.innerText = "100%";
      currentChunkCount.innerText = total;
      transferControlGroup.classList.add("hidden");
      startUploadBtn.classList.remove("hidden");
      charVerifyStatus.innerText = "✓ 100% Verified";
      showToast("Transfer completed successfully!", "success");
    }

    // Restore logs if available
    if (transfer.logs && transfer.logs.length > 0) {
      logConsole.classList.remove("hidden");
      logEntries.innerHTML = "";
      transfer.logs.forEach((item) => {
        const line = document.createElement("div");
        line.className = "log-line success";
        line.innerText = `[${item.time}] ${item.text}`;
        logEntries.appendChild(line);
      });
      logEntries.scrollTop = logEntries.scrollHeight;
    }
  }

  // Check ongoing transfer on Keep tab
  async function syncActiveTransfer() {
    if (!activeKeepTab) return;
    try {
      const response = await chrome.tabs.sendMessage(activeKeepTab.id, { action: "GET_TRANSFER_STATUS" });
      if (response && response.transfer) {
        updateTransferUI(response.transfer);
      }
    } catch (e) {
      chrome.storage.local.get("activeTransferState", (res) => {
        if (res.activeTransferState) {
          updateTransferUI(res.activeTransferState);
        }
      });
    }
  }

  // Listen to runtime progress updates from content script
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "TRANSFER_UPDATE" && msg.transfer) {
      updateTransferUI(msg.transfer);
    }
  });

  // Start Upload
  startUploadBtn.addEventListener("click", async () => {
    if (!currentFile || !currentFile.chunks.length) {
      showToast("Please choose or paste a text file first!", "error");
      return;
    }

    const isConnected = await checkKeepConnection();
    if (!isConnected || !activeKeepTab) {
      showToast("Google Keep tab not found. Please open keep.google.com first!", "error");
      return;
    }

    const ready = await ensureContentScriptInjected(activeKeepTab.id);
    if (!ready) {
      showToast("Could not connect to Google Keep tab!", "error");
      return;
    }

    const shouldCreateConfig = createConfigNoteCheckbox.checked;
    const configNote = shouldCreateConfig ? currentFile.configNote : null;
    const totalNotes = currentFile.chunks.length + (shouldCreateConfig ? 1 : 0);

    // Update UI immediately
    startUploadBtn.classList.add("hidden");
    transferControlGroup.classList.remove("hidden");
    pauseUploadBtn.classList.remove("hidden");
    resumeUploadBtn.classList.add("hidden");

    uploadProgressBox.classList.remove("hidden");
    progressStatusLabel.innerText = "Starting autonomous upload...";
    progressBarFill.style.width = "0%";
    progressPercentLabel.innerText = "0%";
    currentChunkCount.innerText = "0";
    totalChunkCount.innerText = totalNotes;

    addLog(`🚀 Upload launched: "${currentFile.name}" (${totalNotes} total notes: ${currentFile.chunks.length} chunks${shouldCreateConfig ? " + 1 Config Note" : ""})...`);

    // Dispatch task to content script
    chrome.tabs.sendMessage(activeKeepTab.id, {
      action: "START_UPLOAD",
      chunks: currentFile.chunks,
      configNote: configNote,
      delayMs: currentSettings.delayMs,
      fileId: currentFile.fileId,
      fileName: currentFile.name
    }, (res) => {
      if (res && res.success) {
        showToast("Autonomous upload running in Google Keep tab!", "info");
      }
    });

    // Bring Google Keep tab and its window to front
    chrome.tabs.update(activeKeepTab.id, { active: true });
    if (activeKeepTab.windowId) {
      chrome.windows.update(activeKeepTab.windowId, { focused: true });
    }

    // Auto-close popup if enabled and not in detached window mode
    const shouldAutoClose = autoClosePopupCheckbox && autoClosePopupCheckbox.checked && !isWindowMode;
    if (shouldAutoClose) {
      showToast("Transfer running! Closing popup to monitor on Keep...", "info");
      setTimeout(() => {
        window.close();
      }, 350);
    }
  });

  // Pause Upload
  pauseUploadBtn.addEventListener("click", () => {
    if (activeKeepTab) {
      chrome.tabs.sendMessage(activeKeepTab.id, { action: "PAUSE_UPLOAD" }, (res) => {
        pauseUploadBtn.classList.add("hidden");
        resumeUploadBtn.classList.remove("hidden");
        showToast("Transfer paused. You can click Resume anytime.", "info");
      });
    }
  });

  // Resume Upload
  resumeUploadBtn.addEventListener("click", () => {
    if (activeKeepTab) {
      chrome.tabs.sendMessage(activeKeepTab.id, { action: "RESUME_UPLOAD" }, (res) => {
        if (res && res.success) {
          resumeUploadBtn.classList.add("hidden");
          pauseUploadBtn.classList.remove("hidden");
          showToast("Transfer resumed!", "success");
        } else {
          showToast(res ? res.message : "Failed to resume", "error");
        }
      });
    }
  });

  // Cancel Upload
  cancelUploadBtn.addEventListener("click", () => {
    if (activeKeepTab) {
      chrome.tabs.sendMessage(activeKeepTab.id, { action: "CANCEL_UPLOAD" }, () => {
        showToast("Transfer cancelled.", "info");
        uploadProgressBox.classList.add("hidden");
        transferControlGroup.classList.add("hidden");
        startUploadBtn.classList.remove("hidden");
      });
    }
  });

  // -------------------------------------------------------------
  // DOWNLOAD & REASSEMBLY LOGIC
  // -------------------------------------------------------------
  function parseNoteTitle(note) {
    const rawTitle = (note.title || "").trim();
    if (!rawTitle) return null;

    // 1. New Compact Config Note: [KT CFG #id] (5 parts) filename or [KT-CFG #id] filename
    const compactConfigMatch = rawTitle.match(/^\[(?:KT|KeepTransfer|.*?)?\s*(?:CFG|CONFIG)(?:\s*#([a-zA-Z0-9_-]+))?\](?:\s*\(\s*(\d+)\s*(?:parts|notes|p)?\s*\))?\s*(.*)$/i);
    if (compactConfigMatch) {
      let parsedConfig = null;
      try {
        parsedConfig = JSON.parse(note.content);
      } catch (e) {
        parsedConfig = null;
      }
      const fileId = compactConfigMatch[1] || (parsedConfig && parsedConfig.fileId) || "cfg_unknown";
      const totalParts = compactConfigMatch[2] ? parseInt(compactConfigMatch[2], 10) : (parsedConfig && parsedConfig.totalChunks) || 0;
      const fileName = (compactConfigMatch[3] || (parsedConfig && parsedConfig.fileName) || "file.txt")
        .replace(/[…\.\s\|]+$/, "")
        .trim();

      return {
        isConfig: true,
        fileId: fileId,
        fileName: fileName,
        total: totalParts,
        configData: parsedConfig,
        rawNote: note
      };
    }

    // 2. Old Config Note: [KT-CONFIG] filename | ID:xxx
    const oldConfigMatch = rawTitle.match(/\[(.*?-CONFIG)\]\s*(.*?)\s*\|\s*ID:([a-zA-Z0-9_-]+)/i);
    if (oldConfigMatch) {
      let parsedConfig = null;
      try {
        parsedConfig = JSON.parse(note.content);
      } catch (e) {
        parsedConfig = null;
      }
      return {
        isConfig: true,
        fileId: oldConfigMatch[3].trim(),
        fileName: oldConfigMatch[2].replace(/[…\.\s\|]+$/, "").trim(),
        total: (parsedConfig && parsedConfig.totalChunks) || 0,
        configData: parsedConfig,
        rawNote: note
      };
    }

    // 3. New Compact Chunk Note: [KT 01/05 #abc12] filename or [01/05 #abc12] filename
    const compactChunkMatch = rawTitle.match(/^\[(?:KT|KeepTransfer|.*?)?\s*(\d+)[\/ ](\d+)(?:\s*#([a-zA-Z0-9_-]+))?\]\s*(?:#([a-zA-Z0-9_-]+)\s*\|?\s*)?(.*)$/i);
    if (compactChunkMatch) {
      const part = parseInt(compactChunkMatch[1], 10);
      const total = parseInt(compactChunkMatch[2], 10);
      const fileId = compactChunkMatch[3] || compactChunkMatch[4] || "default_id";
      const rawFileName = (compactChunkMatch[5] || "").replace(/[…\.\s\|]+$/, "").trim() || "transfer_file.txt";

      return {
        isConfig: false,
        part: part,
        total: total,
        fileId: fileId,
        fileName: rawFileName,
        rawNote: note
      };
    }

    // 4. Old Chunk Note: [KT] filename | Part 01/05 | ID:xxx
    const oldChunkMatch = rawTitle.match(/\[(.*?)\]\s*(.*?)\s*\|\s*Part\s*(\d+)[\/ ](\d+)\s*\|\s*ID:([a-zA-Z0-9_-]+)/i);
    if (oldChunkMatch) {
      return {
        isConfig: false,
        prefix: oldChunkMatch[1],
        fileName: oldChunkMatch[2].replace(/[…\.\s\|]+$/, "").trim(),
        part: parseInt(oldChunkMatch[3], 10),
        total: parseInt(oldChunkMatch[4], 10),
        fileId: oldChunkMatch[5].trim(),
        rawNote: note
      };
    }

    // 5. Fallback Part matcher: Part 01/05
    const fallbackMatch = rawTitle.match(/(.*?)\s*(?:\||\-|\[|\()\s*Part\s*(\d+)[\/ ](\d+)(?:[\]\)]|\s*\|\s*ID:([^\s\|\]]+))?/i);
    if (fallbackMatch) {
      return {
        isConfig: false,
        fileName: fallbackMatch[1].replace(/^\[.*?\]\s*/, "").replace(/[…\.\s\|]+$/, "").trim(),
        part: parseInt(fallbackMatch[2], 10),
        total: parseInt(fallbackMatch[3], 10),
        fileId: fallbackMatch[4] || `auto_${fallbackMatch[1].trim()}`,
        rawNote: note
      };
    }

    return null;
  }

  function processScannedNotes(notes) {
    scannedNotes = notes;
    detectedFileBundles = {};

    notes.forEach((note) => {
      const parsed = parseNoteTitle(note);
      if (!parsed) return;

      const key = (parsed.fileId && parsed.fileId !== "default_id") ? parsed.fileId : parsed.fileName;
      if (!detectedFileBundles[key]) {
        detectedFileBundles[key] = {
          fileId: parsed.fileId,
          fileName: parsed.fileName,
          total: parsed.total || 0,
          parts: {},
          scannedCount: 0,
          configNote: null
        };
      }

      // Preserve the longest un-truncated filename across notes in the bundle
      if (parsed.fileName && parsed.fileName.length > detectedFileBundles[key].fileName.length && !parsed.fileName.endsWith("…")) {
        detectedFileBundles[key].fileName = parsed.fileName;
      }

      if (parsed.isConfig) {
        detectedFileBundles[key].configNote = parsed;
        if (parsed.total && parsed.total > 0) {
          detectedFileBundles[key].total = parsed.total;
        }
        if (parsed.configData && parsed.configData.totalChunks) {
          detectedFileBundles[key].total = parsed.configData.totalChunks;
        }
        if (parsed.configData && parsed.configData.fileName) {
          detectedFileBundles[key].fileName = parsed.configData.fileName;
        }
      } else {
        if (!detectedFileBundles[key].parts[parsed.part]) {
          detectedFileBundles[key].parts[parsed.part] = note;
          detectedFileBundles[key].scannedCount++;
        }
        if (parsed.total && parsed.total > detectedFileBundles[key].total) {
          detectedFileBundles[key].total = parsed.total;
        }
      }
    });

    renderDetectedFiles();
    renderManualNotesList();
  }

  function renderDetectedFiles() {
    const filter = (scanFilterInput.value || "").toLowerCase().trim();
    const bundleKeys = Object.keys(detectedFileBundles);
    detectedFilesCount.innerText = bundleKeys.length;

    detectedFileList.innerHTML = "";

    if (bundleKeys.length === 0) {
      filesEmptyState.classList.remove("hidden");
      return;
    }

    filesEmptyState.classList.add("hidden");

    bundleKeys.forEach((key) => {
      const bundle = detectedFileBundles[key];
      if (filter && !bundle.fileName.toLowerCase().includes(filter) && !bundle.fileId.toLowerCase().includes(filter)) {
        return;
      }

      const totalParts = bundle.total;
      const foundCount = bundle.scannedCount;
      const hasConfig = bundle.configNote !== null;

      // Calculate missing parts
      const missingParts = [];
      if (totalParts > 0) {
        for (let p = 1; p <= totalParts; p++) {
          if (!bundle.parts[p]) missingParts.push(p);
        }
      }

      // ACCURATE EVALUATION:
      // A file is ONLY complete when totalParts > 0 AND missingParts is empty AND foundCount === totalParts
      const isComplete = totalParts > 0 && missingParts.length === 0 && foundCount === totalParts;

      let totalChars = 0;
      const limit = totalParts > 0 ? totalParts : foundCount;
      for (let p = 1; p <= limit; p++) {
        if (bundle.parts[p]) {
          totalChars += (bundle.parts[p].content || "").length;
        }
      }

      let statusBadgeHtml = "";
      if (isComplete) {
        statusBadgeHtml = `<span class="bundle-badge complete">Complete (${foundCount}/${totalParts}) ✅</span>`;
      } else if (totalParts > 0) {
        statusBadgeHtml = `<span class="bundle-badge partial">Incomplete (${foundCount}/${totalParts}) ⚠️</span>`;
      } else {
        statusBadgeHtml = `<span class="bundle-badge partial">Found ${foundCount} parts (Total unknown) ⚠️</span>`;
      }

      const card = document.createElement("div");
      card.className = "file-bundle-card";
      card.innerHTML = `
        <div class="bundle-header">
          <span class="bundle-title" title="${bundle.fileName}">${bundle.fileName}</span>
          <div class="bundle-badges">
            ${hasConfig ? `<span class="bundle-badge config" title="Master Config Note was detected">Config ✅</span>` : ""}
            ${statusBadgeHtml}
          </div>
        </div>
        <div class="bundle-meta">
          ID: <code>${bundle.fileId}</code> • ${totalChars.toLocaleString()} chars • ~${formatBytes(totalChars)}
          ${missingParts.length > 0 ? `<br><span style="color:#F59E0B; font-weight:600;">⚠️ Missing parts: ${missingParts.map(p => `Part ${p}`).join(", ")}</span>` : ""}
          ${totalParts === 0 ? `<br><span style="color:#F59E0B;">⚠️ Total parts unverified (Deep Scan to find all parts)</span>` : ""}
        </div>
        <div class="bundle-actions">
          ${isComplete ? `
            <button class="btn btn-sm btn-primary btn-download-file" data-key="${key}">
              📥 Download (.txt)
            </button>
          ` : `
            <button class="btn btn-sm btn-secondary btn-download-file" data-key="${key}" title="Warning: File has missing parts" style="border-color:#F59E0B; color:#FCD34D;">
              ⚠️ Download Partial (${foundCount}/${totalParts || "?"})
            </button>
          `}
          <button class="btn btn-sm btn-secondary btn-preview-file" data-key="${key}">
            👁️ Preview
          </button>
          <button class="btn btn-sm btn-secondary btn-copy-file" data-key="${key}">
            📋 Copy
          </button>
        </div>
      `;

      card.querySelector(".btn-download-file").addEventListener("click", () => {
        downloadMergedFile(bundle);
      });

      card.querySelector(".btn-preview-file").addEventListener("click", () => {
        previewMergedFile(bundle);
      });

      card.querySelector(".btn-copy-file").addEventListener("click", () => {
        copyMergedFile(bundle);
      });

      detectedFileList.appendChild(card);
    });
  }

  function getMergedContent(bundle) {
    const partsArray = [];
    const totalParts = bundle.total || bundle.scannedCount;
    for (let p = 1; p <= totalParts; p++) {
      if (bundle.parts[p]) {
        partsArray.push(bundle.parts[p].content || "");
      }
    }
    return partsArray.join("");
  }

  function downloadMergedFile(bundle) {
    const totalParts = bundle.total;
    const missingParts = [];
    if (totalParts > 0) {
      for (let p = 1; p <= totalParts; p++) {
        if (!bundle.parts[p]) missingParts.push(p);
      }
    }

    if (missingParts.length > 0) {
      const confirmDownload = confirm(`⚠️ Warning: This file is missing ${missingParts.length} parts (${missingParts.map(p => `Part ${p}`).join(", ")}).\n\nIf downloaded, the file will be incomplete.\n\nDo you want to download partial content anyway?`);
      if (!confirmDownload) return;
    }

    const merged = getMergedContent(bundle);
    chrome.runtime.sendMessage({
      type: "DOWNLOAD_FILE",
      filename: bundle.fileName || "merged_file.txt",
      content: merged
    }, (res) => {
      if (res && res.success) {
        showToast(`Download started: ${bundle.fileName}`, "success");
      } else {
        showToast("Error starting download", "error");
      }
    });
  }

  function previewMergedFile(bundle) {
    const merged = getMergedContent(bundle);
    previewCurrentData = {
      title: `${bundle.fileName} (${bundle.scannedCount}/${bundle.total || bundle.scannedCount} parts)`,
      filename: bundle.fileName,
      content: merged
    };
    previewModalTitle.innerText = previewCurrentData.title;
    previewModalBody.innerText = merged.slice(0, 80000) + (merged.length > 80000 ? "\n\n... (Preview truncated for display) ..." : "");
    previewModal.classList.remove("hidden");
  }

  function copyMergedFile(bundle) {
    const merged = getMergedContent(bundle);
    navigator.clipboard.writeText(merged).then(() => {
      showToast(`Copied ${merged.length.toLocaleString()} characters to clipboard!`, "success");
    }).catch(() => {
      showToast("Failed to copy to clipboard", "error");
    });
  }

  scanFilterInput.addEventListener("input", renderDetectedFiles);
  refreshFilesBtn.addEventListener("click", renderDetectedFiles);

  async function triggerScan(scanAction) {
    const isConnected = await checkKeepConnection();
    if (!isConnected || !activeKeepTab) {
      showToast("Google Keep tab not found!", "error");
      return;
    }

    const ready = await ensureContentScriptInjected(activeKeepTab.id);
    if (!ready) {
      showToast("Could not connect to Google Keep tab!", "error");
      return;
    }

    scanStatusAlert.classList.remove("hidden");
    scanStatusMsg.innerText = "Connecting and scanning notes...";

    try {
      activeScanPort = chrome.tabs.connect(activeKeepTab.id, { name: "keep-transfer-port" });
      const receivedNotes = [];

      activeScanPort.onMessage.addListener((msg) => {
        if (msg.type === "SCAN_STATUS") {
          scanStatusMsg.innerText = msg.message;
        }

        if (msg.type === "SCAN_PROGRESS") {
          if (msg.note) receivedNotes.push(msg.note);
          scanStatusMsg.innerText = `Scanning [${msg.current}/${msg.total}]: "${(msg.note && msg.note.title) || ""}"...`;
        }

        if (msg.type === "SCAN_COMPLETE") {
          scanStatusAlert.classList.add("hidden");
          const finalNotes = msg.results || receivedNotes;
          processScannedNotes(finalNotes);
          showToast(`Scan complete! Found ${finalNotes.length} notes.`, "success");
        }

        if (msg.type === "SCAN_ERROR") {
          scanStatusAlert.classList.add("hidden");
          showToast(`Scan error: ${msg.error}`, "error");
        }
      });

      activeScanPort.postMessage({
        action: scanAction,
        options: {
          prefix: currentSettings.prefixTag,
          scrollDelay: currentSettings.scrollDelay,
          openMatching: true
        }
      });
    } catch (err) {
      scanStatusAlert.classList.add("hidden");
      showToast("Connection error during scan", "error");
    }
  }

  quickScanBtn.addEventListener("click", () => triggerScan("START_QUICK_SCAN"));
  deepScanBtn.addEventListener("click", () => triggerScan("START_DEEP_SCAN"));

  cancelScanBtn.addEventListener("click", () => {
    if (activeScanPort) {
      activeScanPort.disconnect();
      activeScanPort = null;
    }
    scanStatusAlert.classList.add("hidden");
    showToast("Scan stopped.", "info");
  });

  // -------------------------------------------------------------
  // TAB 3: MANUAL MERGER
  // -------------------------------------------------------------
  function renderManualNotesList() {
    totalScannedNotes.innerText = scannedNotes.length;
    notesManualList.innerHTML = "";

    if (scannedNotes.length === 0) {
      notesManualList.innerHTML = `<div class="empty-manual-msg">No notes available. Click "Quick Scan" or "Deep Scan" in the "Reassemble & Download" tab first.</div>`;
      mergeSelectedBtn.disabled = true;
      exportAllJsonBtn.disabled = true;
      return;
    }

    exportAllJsonBtn.disabled = false;

    scannedNotes.forEach((note, index) => {
      const card = document.createElement("div");
      card.className = "note-item-card";
      card.innerHTML = `
        <input type="checkbox" class="note-select-check" data-index="${index}">
        <div class="note-item-info">
          <div class="note-item-title">${note.title || "Untitled Note"}</div>
          <div class="note-item-snippet">${(note.content || "").slice(0, 100).replace(/\n/g, " ") || "[Empty content]"}</div>
        </div>
      `;

      card.querySelector(".note-select-check").addEventListener("change", updateManualSelectionStats);
      notesManualList.appendChild(card);
    });

    updateManualSelectionStats();
  }

  function updateManualSelectionStats() {
    const checks = notesManualList.querySelectorAll(".note-select-check:checked");
    selectedNotesCount.innerText = checks.length;
    mergeSelectedBtn.disabled = checks.length === 0;
  }

  selectAllNotesCheckbox.addEventListener("change", () => {
    const isChecked = selectAllNotesCheckbox.checked;
    const checks = notesManualList.querySelectorAll(".note-select-check");
    checks.forEach((chk) => (chk.checked = isChecked));
    updateManualSelectionStats();
  });

  mergeSelectedBtn.addEventListener("click", () => {
    const checks = Array.from(notesManualList.querySelectorAll(".note-select-check:checked"));
    if (checks.length === 0) return;

    let sep = "\n";
    if (mergeSeparatorSelect.value === "none") sep = "";
    if (mergeSeparatorSelect.value === "double_newline") sep = "\n\n";
    if (mergeSeparatorSelect.value === "divider") sep = "\n\n---\n\n";

    const selectedContents = checks.map((chk) => {
      const idx = parseInt(chk.getAttribute("data-index"), 10);
      return (scannedNotes[idx] && scannedNotes[idx].content) || "";
    });

    const mergedText = selectedContents.join(sep);
    chrome.runtime.sendMessage({
      type: "DOWNLOAD_FILE",
      filename: `keep_manual_merged_${new Date().toISOString().slice(0, 10)}.txt`,
      content: mergedText
    }, (res) => {
      if (res && res.success) {
        showToast("Merged download started!", "success");
      }
    });
  });

  exportAllJsonBtn.addEventListener("click", () => {
    if (scannedNotes.length === 0) return;
    const jsonString = JSON.stringify(scannedNotes, null, 2);
    chrome.runtime.sendMessage({
      type: "DOWNLOAD_FILE",
      filename: `google_keep_full_export_${new Date().toISOString().slice(0, 10)}.json`,
      content: jsonString,
      mimeType: "application/json;charset=utf-8"
    }, (res) => {
      if (res && res.success) {
        showToast("Exported JSON successfully!", "success");
      }
    });
  });

  // -------------------------------------------------------------
  // TAB 4: SETTINGS
  // -------------------------------------------------------------
  saveSettingsBtn.addEventListener("click", () => {
    const newSettings = {
      chunkSize: parseInt(settingChunkSize.value, 10),
      delayMs: parseInt(settingDelayMs.value, 10),
      prefixTag: settingPrefix.value.trim() || "[KT]",
      configPrefix: settingConfigPrefix.value.trim() || "[KT-CONFIG]",
      scrollDelay: parseInt(settingScrollDelay.value, 10),
      autoClose: settingAutoClose ? settingAutoClose.checked : true
    };

    chrome.storage.local.set(newSettings, () => {
      currentSettings = newSettings;
      if (autoClosePopupCheckbox) autoClosePopupCheckbox.checked = currentSettings.autoClose;
      chunkSizeDisplay.innerText = Number(currentSettings.chunkSize).toLocaleString();
      showToast("Settings saved successfully!", "success");
    });
  });

  // -------------------------------------------------------------
  // PREVIEW MODAL
  // -------------------------------------------------------------
  closePreviewBtn.addEventListener("click", () => {
    previewModal.classList.add("hidden");
  });

  copyPreviewBtn.addEventListener("click", () => {
    if (previewCurrentData) {
      navigator.clipboard.writeText(previewCurrentData.content).then(() => {
        showToast("Copied content to clipboard!", "success");
      });
    }
  });

  downloadPreviewBtn.addEventListener("click", () => {
    if (previewCurrentData) {
      chrome.runtime.sendMessage({
        type: "DOWNLOAD_FILE",
        filename: previewCurrentData.filename || "preview_download.txt",
        content: previewCurrentData.content
      }, (res) => {
        if (res && res.success) {
          showToast("Download started!", "success");
          previewModal.classList.add("hidden");
        }
      });
    }
  });

  previewModal.addEventListener("click", (e) => {
    if (e.target === previewModal) previewModal.classList.add("hidden");
  });

  // Initial Load & State Sync
  await loadSettings();
  await checkKeepConnection();
  await syncActiveTransfer();
});
