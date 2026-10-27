// Google Keep Text File Transfer - Popup Logic

document.addEventListener("DOMContentLoaded", async () => {
  // Elements
  const connectionBadge = document.getElementById("connectionBadge");
  const statusDot = connectionBadge.querySelector(".status-dot");
  const statusText = document.getElementById("statusText");
  const keepTabWarning = document.getElementById("keepTabWarning");
  const openKeepBtn = document.getElementById("openKeepBtn");

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

  const uploadProgressBox = document.getElementById("uploadProgressBox");
  const progressStatusLabel = document.getElementById("progressStatusLabel");
  const progressPercentLabel = document.getElementById("progressPercentLabel");
  const progressBarFill = document.getElementById("progressBarFill");
  const currentChunkCount = document.getElementById("currentChunkCount");
  const totalChunkCount = document.getElementById("totalChunkCount");

  const logConsole = document.getElementById("logConsole");
  const logEntries = document.getElementById("logEntries");
  const clearLogBtn = document.getElementById("clearLogBtn");

  const startUploadBtn = document.getElementById("startUploadBtn");
  const cancelUploadBtn = document.getElementById("cancelUploadBtn");

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
  const settingScrollDelay = document.getElementById("settingScrollDelay");
  const saveSettingsBtn = document.getElementById("saveSettingsBtn");

  // Modal Preview
  const previewModal = document.getElementById("previewModal");
  const previewModalTitle = document.getElementById("previewModalTitle");
  const previewModalBody = document.getElementById("previewModalBody");
  const closePreviewBtn = document.getElementById("closePreviewBtn");
  const copyPreviewBtn = document.getElementById("copyPreviewBtn");
  const downloadPreviewBtn = document.getElementById("downloadPreviewBtn");
  const toastContainer = document.getElementById("toastContainer");

  // State
  let activeKeepTab = null;
  let activePort = null;
  let currentFile = null; // { name, size, text, chunks }
  let currentSettings = {
    chunkSize: 10000,
    delayMs: 800,
    prefixTag: "[KeepTransfer]",
    scrollDelay: 1200
  };
  let scannedNotes = [];
  let detectedFileBundles = {};
  let previewCurrentData = null; // { title, filename, content }

  // Load Settings
  async function loadSettings() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["chunkSize", "delayMs", "prefixTag", "scrollDelay"], (res) => {
        if (res.chunkSize) currentSettings.chunkSize = parseInt(res.chunkSize, 10);
        if (res.delayMs) currentSettings.delayMs = parseInt(res.delayMs, 10);
        if (res.prefixTag) currentSettings.prefixTag = res.prefixTag;
        if (res.scrollDelay) currentSettings.scrollDelay = parseInt(res.scrollDelay, 10);

        settingChunkSize.value = currentSettings.chunkSize;
        settingDelayMs.value = currentSettings.delayMs;
        settingPrefix.value = currentSettings.prefixTag;
        settingScrollDelay.value = currentSettings.scrollDelay;
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
    }, 2600);
  }

  // Log to Console UI
  function addLog(text, type = "normal") {
    logConsole.classList.remove("hidden");
    const line = document.createElement("div");
    line.className = `log-line ${type}`;
    const time = new Date().toLocaleTimeString("vi-VN", { hour12: false });
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
      statusText.innerText = "Keep: Kết nối";
      keepTabWarning.classList.add("hidden");
      return true;
    }

    // Check if Keep is open in any other tab
    const keepTabs = await chrome.tabs.query({ url: "*://keep.google.com/*" });
    if (keepTabs.length > 0) {
      activeKeepTab = keepTabs[0];
      statusDot.className = "status-dot connected";
      statusText.innerText = `Keep: Tab #${activeKeepTab.id}`;
      keepTabWarning.classList.remove("hidden");
      return true;
    }

    activeKeepTab = null;
    statusDot.className = "status-dot disconnected";
    statusText.innerText = "Chưa mở Keep";
    keepTabWarning.classList.remove("hidden");
    return false;
  }

  // Open or switch to Google Keep
  openKeepBtn.addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "OPEN_KEEP_TAB" }, (res) => {
      setTimeout(checkKeepConnection, 500);
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
      // Content script not loaded yet, inject it
      try {
        await chrome.scripting.executeScript({
          target: { tabId },
          files: ["content.js"]
        });
        await new Promise((r) => setTimeout(r, 200));
        return true;
      } catch (err) {
        console.error("Không thể inject content script:", err);
        return false;
      }
    }
    return true;
  }

  // Helper: Format bytes
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

  // Generate Unique File ID
  function generateFileId() {
    const rand = Math.random().toString(36).substring(2, 7);
    const ts = Date.now().toString(36);
    return `kpf_${ts}_${rand}`;
  }

  // Prepare File for Upload
  function handleFileLoaded(fileName, fileText, fileSize) {
    const chunkSize = currentSettings.chunkSize || 10000;
    const rawChunks = chunkText(fileText, chunkSize);
    const fileId = generateFileId();
    const total = rawChunks.length;

    const preparedChunks = rawChunks.map((content, idx) => ({
      index: idx + 1,
      total: total,
      title: `${currentSettings.prefixTag} ${fileName} | Part ${idx + 1}/${total} | ID:${fileId}`,
      content: content
    }));

    currentFile = {
      name: fileName,
      size: fileSize,
      length: fileText.length,
      chunks: preparedChunks,
      fileId: fileId
    };

    // Update UI
    fileNameDisplay.innerText = fileName;
    fileMetaDisplay.innerText = `${formatBytes(fileSize)} • ${fileText.length.toLocaleString()} ký tự`;
    chunkCountDisplay.innerText = total;
    fileCard.classList.remove("hidden");
    startUploadBtn.disabled = false;
    startUploadBtn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
      Tách làm ${total} ghi chú & Tải lên Keep
    `;

    addLog(`Đã tải file "${fileName}" (${formatBytes(fileSize)}, ${fileText.length.toLocaleString()} ký tự). Tách thành ${total} phần.`);
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

  // Toggle Paste Direct Text
  togglePasteBox.addEventListener("click", () => {
    pasteContainer.classList.toggle("hidden");
    if (!pasteContainer.classList.contains("hidden")) {
      pasteTextInput.focus();
    }
  });

  pasteTextInput.addEventListener("input", () => {
    const text = pasteTextInput.value;
    if (!text.trim()) return;
    const name = pasteFileName.value.trim() || "pasted_text.txt";
    handleFileLoaded(name, text, new Blob([text]).size);
  });

  // Clear File
  clearFileBtn.addEventListener("click", () => {
    currentFile = null;
    fileInput.value = "";
    pasteTextInput.value = "";
    fileCard.classList.add("hidden");
    startUploadBtn.disabled = true;
    startUploadBtn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
      Tách file & Tải lên Google Keep
    `;
    uploadProgressBox.classList.add("hidden");
    addLog("Đã hủy chọn file.");
  });

  // Clear Logs
  clearLogBtn.addEventListener("click", () => {
    logEntries.innerHTML = "";
    logConsole.classList.add("hidden");
  });

  // Start Upload Button
  startUploadBtn.addEventListener("click", async () => {
    if (!currentFile || !currentFile.chunks.length) {
      showToast("Vui lòng chọn hoặc dán file trước!", "error");
      return;
    }

    const isConnected = await checkKeepConnection();
    if (!isConnected || !activeKeepTab) {
      showToast("Chưa kết nối tab Google Keep. Hãy mở keep.google.com trước!", "error");
      return;
    }

    // Ensure content script is ready
    const ready = await ensureContentScriptInjected(activeKeepTab.id);
    if (!ready) {
      showToast("Không thể kết nối với trang Google Keep!", "error");
      return;
    }

    // Update UI for Uploading state
    startUploadBtn.classList.add("hidden");
    cancelUploadBtn.classList.remove("hidden");
    uploadProgressBox.classList.remove("hidden");
    progressStatusLabel.innerText = "Bắt đầu tải lên...";
    progressBarFill.style.width = "0%";
    progressPercentLabel.innerText = "0%";
    currentChunkCount.innerText = "0";
    totalChunkCount.innerText = currentFile.chunks.length;

    addLog(`🚀 Bắt đầu tải lên file "${currentFile.name}" gồm ${currentFile.chunks.length} ghi chú...`);

    // Connect Port to Content Script
    try {
      activePort = chrome.tabs.connect(activeKeepTab.id, { name: "keep-transfer-port" });
      activePort.onMessage.addListener((msg) => {
        if (msg.type === "UPLOAD_PROGRESS") {
          const pct = Math.round((msg.current / msg.total) * 100);
          progressBarFill.style.width = `${pct}%`;
          progressPercentLabel.innerText = `${pct}%`;
          currentChunkCount.innerText = msg.current;
          progressStatusLabel.innerText = msg.status || `Đang tạo [${msg.current}/${msg.total}]...`;
          addLog(`✅ Đã tạo ghi chú [${msg.current}/${msg.total}]: "${msg.title}"`, "success");
        }

        if (msg.type === "UPLOAD_COMPLETE") {
          progressBarFill.style.width = "100%";
          progressPercentLabel.innerText = "100%";
          progressStatusLabel.innerText = "Hoàn tất!";
          startUploadBtn.classList.remove("hidden");
          cancelUploadBtn.classList.add("hidden");
          addLog(`🎉 HOÀN TẤT! Đã tạo thành công ${msg.total} ghi chú lên Google Keep.`, "success");
          showToast(`Đã tải lên toàn bộ ${msg.total} ghi chú!`, "success");
        }

        if (msg.type === "UPLOAD_ERROR") {
          progressStatusLabel.innerText = "Xảy ra lỗi!";
          addLog(`❌ Lỗi ghi chú [${msg.current}/${msg.total}]: ${msg.error}`, "error");
          showToast(`Lỗi: ${msg.error}`, "error");
          startUploadBtn.classList.remove("hidden");
          cancelUploadBtn.classList.add("hidden");
        }

        if (msg.type === "UPLOAD_CANCELLED") {
          progressStatusLabel.innerText = "Đã dừng.";
          addLog(`⚠️ Đã dừng tải lên tại ghi chú ${msg.index}.`, "error");
          showToast("Đã dừng quá trình tải lên.", "info");
          startUploadBtn.classList.remove("hidden");
          cancelUploadBtn.classList.add("hidden");
        }
      });

      // Send start message
      activePort.postMessage({
        action: "START_UPLOAD",
        chunks: currentFile.chunks,
        delayMs: currentSettings.delayMs
      });
    } catch (err) {
      console.error(err);
      addLog(`❌ Lỗi kết nối: ${err.message}`, "error");
      showToast("Lỗi kết nối tới tab Keep", "error");
      startUploadBtn.classList.remove("hidden");
      cancelUploadBtn.classList.add("hidden");
    }
  });

  // Cancel Upload Button
  cancelUploadBtn.addEventListener("click", () => {
    if (activePort) {
      activePort.postMessage({ action: "CANCEL_OPERATION" });
    }
    if (activeKeepTab) {
      chrome.tabs.sendMessage(activeKeepTab.id, { action: "CANCEL_OPERATION" });
    }
    cancelUploadBtn.classList.add("hidden");
    startUploadBtn.classList.remove("hidden");
  });

  // -------------------------------------------------------------
  // DOWNLOAD & REASSEMBLY LOGIC
  // -------------------------------------------------------------

  // Regex parser for chunk titles
  // Format: [KeepTransfer] filename.txt | Part 1/5 | ID:kpf_xyz
  const chunkTitleRegex = /\[(.*?)\]\s*(.*?)\s*\|\s*Part\s*(\d+)\/(\d+)\s*\|\s*ID:([a-zA-Z0-9_-]+)/i;
  // Fallback regex: filename.txt (Part 1/5)
  const fallbackChunkRegex = /(.*?)\s*(?:\||\-|\[|\()\s*Part\s*(\d+)[\/ ](\d+)(?:[\]\)]|\s*\|\s*ID:([^\s\|\]]+))?/i;

  function parseChunkNote(note) {
    const title = (note.title || "").trim();
    let match = title.match(chunkTitleRegex);
    if (match) {
      return {
        prefix: match[1],
        fileName: match[2].trim(),
        part: parseInt(match[3], 10),
        total: parseInt(match[4], 10),
        fileId: match[5],
        rawNote: note
      };
    }

    match = title.match(fallbackChunkRegex);
    if (match) {
      return {
        prefix: "",
        fileName: match[1].replace(/^\[.*?\]\s*/, "").trim(),
        part: parseInt(match[2], 10),
        total: parseInt(match[3], 10),
        fileId: match[4] || `auto_${match[1].trim()}`,
        rawNote: note
      };
    }

    return null;
  }

  // Group chunks into File Bundles
  function processScannedNotes(notes) {
    scannedNotes = notes;
    detectedFileBundles = {};

    notes.forEach((note) => {
      const parsed = parseChunkNote(note);
      if (!parsed) return;

      const key = parsed.fileId || parsed.fileName;
      if (!detectedFileBundles[key]) {
        detectedFileBundles[key] = {
          fileId: parsed.fileId,
          fileName: parsed.fileName,
          total: parsed.total,
          parts: {},
          scannedCount: 0
        };
      }

      if (!detectedFileBundles[key].parts[parsed.part]) {
        detectedFileBundles[key].parts[parsed.part] = note;
        detectedFileBundles[key].scannedCount++;
      }
    });

    renderDetectedFiles();
    renderManualNotesList();
  }

  // Render Detected Files in Download Tab
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
      const isComplete = foundCount >= totalParts;

      // Calculate total characters
      let totalChars = 0;
      for (let p = 1; p <= totalParts; p++) {
        if (bundle.parts[p]) {
          totalChars += (bundle.parts[p].content || "").length;
        }
      }

      // Check missing parts
      const missingParts = [];
      for (let p = 1; p <= totalParts; p++) {
        if (!bundle.parts[p]) missingParts.push(p);
      }

      const card = document.createElement("div");
      card.className = "file-bundle-card";
      card.innerHTML = `
        <div class="bundle-header">
          <span class="bundle-title" title="${bundle.fileName}">${bundle.fileName}</span>
          <span class="bundle-badge ${isComplete ? "complete" : "partial"}">
            ${isComplete ? `Đủ ${foundCount}/${totalParts} phần ✅` : `Đã thấy ${foundCount}/${totalParts} phần ⚠️`}
          </span>
        </div>
        <div class="bundle-meta">
          ID: <code>${bundle.fileId}</code> • ${totalChars.toLocaleString()} ký tự • ~${formatBytes(totalChars)}
          ${missingParts.length > 0 ? `<br><span style="color:#F59E0B">Thiếu phần: ${missingParts.join(", ")}</span>` : ""}
        </div>
        <div class="bundle-actions">
          <button class="btn btn-sm btn-primary btn-download-file" data-key="${key}" ${!isComplete ? "title='Chưa đủ phần nhưng vẫn có thể tải'" : ""}>
            📥 Tải xuống (.txt)
          </button>
          <button class="btn btn-sm btn-secondary btn-preview-file" data-key="${key}">
            👁️ Xem trước
          </button>
          <button class="btn btn-sm btn-secondary btn-copy-file" data-key="${key}">
            📋 Copy
          </button>
        </div>
      `;

      // Download Button
      card.querySelector(".btn-download-file").addEventListener("click", () => {
        downloadMergedFile(bundle);
      });

      // Preview Button
      card.querySelector(".btn-preview-file").addEventListener("click", () => {
        previewMergedFile(bundle);
      });

      // Copy Button
      card.querySelector(".btn-copy-file").addEventListener("click", () => {
        copyMergedFile(bundle);
      });

      detectedFileList.appendChild(card);
    });
  }

  // Combine and Download
  function getMergedContent(bundle) {
    const partsArray = [];
    for (let p = 1; p <= bundle.total; p++) {
      if (bundle.parts[p]) {
        partsArray.push(bundle.parts[p].content || "");
      }
    }
    return partsArray.join("");
  }

  function downloadMergedFile(bundle) {
    const merged = getMergedContent(bundle);
    chrome.runtime.sendMessage({
      type: "DOWNLOAD_FILE",
      filename: bundle.fileName || "merged_file.txt",
      content: merged
    }, (res) => {
      if (res && res.success) {
        showToast(`Đã bắt đầu tải xuống: ${bundle.fileName}`, "success");
      } else {
        showToast("Lỗi khi tải xuống file", "error");
      }
    });
  }

  function previewMergedFile(bundle) {
    const merged = getMergedContent(bundle);
    previewCurrentData = {
      title: `${bundle.fileName} (${bundle.scannedCount}/${bundle.total} phần)`,
      filename: bundle.fileName,
      content: merged
    };
    previewModalTitle.innerText = previewCurrentData.title;
    previewModalBody.innerText = merged.slice(0, 100000) + (merged.length > 100000 ? "\n\n... (Đã cắt bớt xem trước) ..." : "");
    previewModal.classList.remove("hidden");
  }

  function copyMergedFile(bundle) {
    const merged = getMergedContent(bundle);
    navigator.clipboard.writeText(merged).then(() => {
      showToast(`Đã sao chép ${merged.length.toLocaleString()} ký tự vào clipboard!`, "success");
    }).catch(() => {
      showToast("Không thể sao chép vào clipboard", "error");
    });
  }

  // Search Filter in Download Tab
  scanFilterInput.addEventListener("input", renderDetectedFiles);
  refreshFilesBtn.addEventListener("click", renderDetectedFiles);

  // Trigger Scan Helper
  async function triggerScan(scanAction) {
    const isConnected = await checkKeepConnection();
    if (!isConnected || !activeKeepTab) {
      showToast("Chưa kết nối tab Google Keep!", "error");
      return;
    }

    const ready = await ensureContentScriptInjected(activeKeepTab.id);
    if (!ready) {
      showToast("Không thể kết nối với tab Google Keep!", "error");
      return;
    }

    scanStatusAlert.classList.remove("hidden");
    scanStatusMsg.innerText = "Đang kết nối và quét ghi chú...";

    try {
      activePort = chrome.tabs.connect(activeKeepTab.id, { name: "keep-transfer-port" });
      const receivedNotes = [];

      activePort.onMessage.addListener((msg) => {
        if (msg.type === "SCAN_STATUS") {
          scanStatusMsg.innerText = msg.message;
        }

        if (msg.type === "SCAN_PROGRESS") {
          if (msg.note) receivedNotes.push(msg.note);
          scanStatusMsg.innerText = `Đang đọc ghi chú [${msg.current}/${msg.total}]: "${(msg.note && msg.note.title) || ""}"...`;
        }

        if (msg.type === "SCAN_COMPLETE") {
          scanStatusAlert.classList.add("hidden");
          const finalNotes = msg.results || receivedNotes;
          processScannedNotes(finalNotes);
          showToast(`Quét xong! Đã tìm thấy ${finalNotes.length} ghi chú.`, "success");
        }

        if (msg.type === "SCAN_ERROR") {
          scanStatusAlert.classList.add("hidden");
          showToast(`Lỗi quét: ${msg.error}`, "error");
        }

        if (msg.type === "SCAN_CANCELLED") {
          scanStatusAlert.classList.add("hidden");
          processScannedNotes(msg.results || receivedNotes);
          showToast("Đã dừng quét ghi chú.", "info");
        }
      });

      activePort.postMessage({
        action: scanAction,
        options: {
          prefix: currentSettings.prefixTag,
          scrollDelay: currentSettings.scrollDelay,
          openMatching: true
        }
      });
    } catch (err) {
      scanStatusAlert.classList.add("hidden");
      showToast("Lỗi kết nối khi quét", "error");
    }
  }

  // Quick Scan Button
  quickScanBtn.addEventListener("click", () => triggerScan("START_QUICK_SCAN"));

  // Deep Scan Button
  deepScanBtn.addEventListener("click", () => triggerScan("START_DEEP_SCAN"));

  // Cancel Scan Button
  cancelScanBtn.addEventListener("click", () => {
    if (activePort) activePort.postMessage({ action: "CANCEL_OPERATION" });
    if (activeKeepTab) chrome.tabs.sendMessage(activeKeepTab.id, { action: "CANCEL_OPERATION" });
    scanStatusAlert.classList.add("hidden");
  });

  // -------------------------------------------------------------
  // TAB 3: MANUAL MERGER
  // -------------------------------------------------------------
  function renderManualNotesList() {
    totalScannedNotes.innerText = scannedNotes.length;
    notesManualList.innerHTML = "";

    if (scannedNotes.length === 0) {
      notesManualList.innerHTML = `<div class="empty-manual-msg">Chưa có ghi chú nào. Hãy bấm "Quét nhanh" hoặc "Quét toàn diện" ở tab "Ghép & Tải xuống" trước.</div>`;
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
          <div class="note-item-title">${note.title || "Không có tiêu đề"}</div>
          <div class="note-item-snippet">${(note.content || "").slice(0, 100).replace(/\n/g, " ") || "[Trống]"}</div>
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

  // Merge Selected Notes
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
        showToast("Đã bắt đầu tải file gộp!", "success");
      }
    });
  });

  // Export All as JSON (Matches user script exactly)
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
        showToast("Đã bắt đầu xuất file JSON!", "success");
      }
    });
  });

  // -------------------------------------------------------------
  // TAB 4: SETTINGS LOGIC
  // -------------------------------------------------------------
  saveSettingsBtn.addEventListener("click", () => {
    const newSettings = {
      chunkSize: parseInt(settingChunkSize.value, 10),
      delayMs: parseInt(settingDelayMs.value, 10),
      prefixTag: settingPrefix.value.trim() || "[KeepTransfer]",
      scrollDelay: parseInt(settingScrollDelay.value, 10)
    };

    chrome.storage.local.set(newSettings, () => {
      currentSettings = newSettings;
      chunkSizeDisplay.innerText = Number(currentSettings.chunkSize).toLocaleString();
      showToast("Đã lưu cài đặt thành công!", "success");
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
        showToast("Đã sao chép nội dung vào clipboard!", "success");
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
          showToast("Đã bắt đầu tải xuống!", "success");
          previewModal.classList.add("hidden");
        }
      });
    }
  });

  // Close modal on click outside
  previewModal.addEventListener("click", (e) => {
    if (e.target === previewModal) previewModal.classList.add("hidden");
  });

  // Initial load
  await loadSettings();
  await checkKeepConnection();
});
