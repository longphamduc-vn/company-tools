// Google Keep Text File Transfer - Content Script
// Handles automated note creation, DOM interaction, scrolling, and note extraction.

let isOperationCancelled = false;

// Helper: Sleep
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Helper: Wait for condition
async function waitFor(conditionFn, timeout = 5000, interval = 50) {
  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    if (isOperationCancelled) throw new Error("Thao tác đã bị hủy");
    const res = conditionFn();
    if (res) return res;
    await sleep(interval);
  }
  return null;
}

// Helper: Insert text into contenteditable element reliably for Google Keep
async function insertTextIntoEditable(el, text) {
  if (!el) return false;
  el.focus();
  await sleep(30);

  // Clear existing content
  try {
    document.execCommand("selectAll", false, null);
    document.execCommand("delete", false, null);
  } catch (e) {
    el.innerText = "";
  }

  let success = false;
  try {
    // Primary: execCommand insertText
    success = document.execCommand("insertText", false, text);
  } catch (e) {
    success = false;
  }

  // Fallback if execCommand returned false or innerText is empty
  if (!success || (el.innerText || "").trim() !== text.trim()) {
    try {
      // Fallback 1: Clipboard DataTransfer paste event
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      const pasteEvent = new ClipboardEvent("paste", {
        clipboardData: dt,
        bubbles: true,
        cancelable: true
      });
      el.dispatchEvent(pasteEvent);
      await sleep(20);
    } catch (e) {
      // Fallback 2: Direct text insertion via Selection / Range
      const sel = window.getSelection();
      sel.removeAllRanges();
      const range = document.createRange();
      range.selectNodeContents(el);
      range.deleteContents();
      const textNode = document.createTextNode(text);
      range.insertNode(textNode);
      range.selectNodeContents(el);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    }
  }

  // Dispatch standard events so Google Keep internal model registers changes
  el.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, inputType: "insertText", data: text }));
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  await sleep(30);
  return true;
}

// Locate the "Take a note..." creator container on keep.google.com
function getNoteCreatorElements() {
  const container = document.querySelector(".IZ65Hb-TBnied") ||
                    document.querySelector(".IZ65Hb-s2gQvd") ||
                    document.querySelector(".rymPhb-content") ||
                    document.querySelector("div[data-placeholder='Take a note…']") ||
                    document.querySelector("div[data-placeholder='Tạo ghi chú…']");

  if (!container) return null;

  // Placeholder clickable to expand
  const clickTarget = container.querySelector(".fmcmS-h1U9Be-LS81yb") ||
                      container.querySelector(".IZ65Hb-qJTHM-haAclf") ||
                      container.querySelector(".fmcmS-LwH6nd") ||
                      container;

  // Title element (when expanded)
  const titleEl = container.querySelector(".IZ65Hb-YPqjbf[role='textbox']") ||
                  container.querySelector(".IZ65Hb-YPqjbf[contenteditable='true']") ||
                  container.querySelector(".IZ65Hb-YPqjbf");

  // Content element (when expanded)
  const contentEl = container.querySelector(".IZ65Hb-vIzZGf-L9AdLc-haAclf") ||
                    container.querySelector(".IZ65Hb-qJTHM-haAclf [contenteditable='true']") ||
                    container.querySelector(".fmcmS-h1U9Be-LS81yb [contenteditable='true']");

  // Close button
  const closeBtn = container.querySelector(".IZ65Hb-TvD9Pc") ||
                   Array.from(container.querySelectorAll("div[role='button']")).find(
                     (b) => b.innerText.trim() === "Close" || b.innerText.trim() === "Đóng"
                   );

  return { container, clickTarget, titleEl, contentEl, closeBtn };
}

// Create a single note in Google Keep
async function createSingleNote(title, content) {
  if (isOperationCancelled) throw new Error("Thao tác đã bị dừng bởi người dùng.");

  // 1. Locate creator container
  let elements = getNoteCreatorElements();
  if (!elements || !elements.container) {
    // Try scrolling to top
    window.scrollTo({ top: 0, behavior: "smooth" });
    await sleep(300);
    elements = getNoteCreatorElements();
  }

  if (!elements || !elements.container) {
    throw new Error("Không tìm thấy ô 'Tạo ghi chú' (Take a note) trên trang Google Keep. Hãy chắc chắn bạn đang ở tab Google Keep.");
  }

  // 2. Click to expand creator if not yet editable
  const isTitleEditable = elements.titleEl && elements.titleEl.getAttribute("contenteditable") === "true";
  const isContentEditable = elements.contentEl && elements.contentEl.getAttribute("contenteditable") === "true";

  if (!isTitleEditable && !isContentEditable) {
    elements.clickTarget.click();
    await sleep(200);
  }

  // 3. Wait for Title & Content inputs to be available and editable
  const readyElements = await waitFor(() => {
    const els = getNoteCreatorElements();
    if (els && els.contentEl) return els;
    return null;
  }, 4000, 80);

  if (!readyElements) {
    throw new Error("Không thể mở trình soạn thảo ghi chú Google Keep.");
  }

  // 4. Input Title
  if (title && readyElements.titleEl) {
    await insertTextIntoEditable(readyElements.titleEl, title);
    await sleep(100);
  }

  // 5. Input Content
  if (content && readyElements.contentEl) {
    // If contenteditable is currently false, click on it first
    if (readyElements.contentEl.getAttribute("contenteditable") === "false") {
      readyElements.contentEl.focus();
      readyElements.contentEl.click();
      await sleep(100);
    }
    await insertTextIntoEditable(readyElements.contentEl, content);
    await sleep(150);
  }

  // 6. Close and Save
  const currentEls = getNoteCreatorElements();
  let closed = false;
  if (currentEls && currentEls.closeBtn) {
    currentEls.closeBtn.click();
    closed = true;
  }

  // Fallback: Dispatch Escape key to force close and save
  if (!closed) {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true }));
    document.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true }));
  }

  await sleep(300);
  return true;
}

// Batch Create Notes (Chunk upload)
async function batchCreateNotes(chunks, delayMs = 800, port) {
  isOperationCancelled = false;
  const total = chunks.length;
  console.log(`🚀 Bắt đầu tải lên ${total} ghi chú (Độ trễ: ${delayMs}ms)...`);

  for (let i = 0; i < total; i++) {
    if (isOperationCancelled) {
      if (port) port.postMessage({ type: "UPLOAD_CANCELLED", index: i });
      return { success: false, cancelled: true, completed: i };
    }

    const chunk = chunks[i];
    if (port) {
      port.postMessage({
        type: "UPLOAD_PROGRESS",
        current: i + 1,
        total: total,
        title: chunk.title,
        status: `Đang tạo ghi chú [${i + 1}/${total}]...`
      });
    }

    try {
      await createSingleNote(chunk.title, chunk.content);
      // Wait specified delay to ensure Google Keep syncs and UI settles
      await sleep(delayMs);
    } catch (err) {
      console.error(`Lỗi khi tạo ghi chú [${i + 1}/${total}]:`, err);
      if (port) {
        port.postMessage({
          type: "UPLOAD_ERROR",
          current: i + 1,
          total: total,
          title: chunk.title,
          error: err.message
        });
      }
      throw err;
    }
  }

  if (port) {
    port.postMessage({
      type: "UPLOAD_COMPLETE",
      total: total,
      status: `Đã tạo thành công toàn bộ ${total} ghi chú!`
    });
  }

  return { success: true, count: total };
}

// Deep Scan All Notes (User's extraction algorithm with full scroll and modal extraction)
async function extractAllKeepNotesDeep(options = {}, port) {
  isOperationCancelled = false;
  console.log("🔄 Bắt đầu cuộn trang để tìm tất cả các ghi chú... Vui lòng chờ.");
  if (port) port.postMessage({ type: "SCAN_STATUS", message: "Đang tự động cuộn trang để tải toàn bộ ghi chú..." });

  // 1. Tự động cuộn xuống cuối trang để load toàn bộ DOM ghi chú
  let lastHeight = document.body.scrollHeight;
  let sameHeightCount = 0;
  const maxScrollAttempts = options.maxScrollAttempts || 30;
  let attempts = 0;

  while (sameHeightCount < 3 && attempts < maxScrollAttempts) {
    if (isOperationCancelled) return { cancelled: true, results: [] };
    attempts++;
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(options.scrollDelay || 1200);

    let newHeight = document.body.scrollHeight;
    if (newHeight === lastHeight) {
      sameHeightCount++;
    } else {
      sameHeightCount = 0;
      lastHeight = newHeight;
    }

    if (port) {
      const currentCards = document.querySelectorAll("div.IZ65Hb-n0tgWb").length;
      port.postMessage({
        type: "SCAN_STATUS",
        message: `Đang cuộn nạp ghi chú (Đã thấy ${currentCards} thẻ)...`
      });
    }
  }

  // Cuộn trở lại đầu trang
  window.scrollTo(0, 0);
  await sleep(500);

  // Lấy toàn bộ thẻ ghi chú đã nạp
  const noteCards = Array.from(document.querySelectorAll("div.IZ65Hb-n0tgWb"));
  console.log(`✅ Đã tìm thấy tổng cộng ${noteCards.length} ghi chú! Bắt đầu trích xuất...`);

  if (port) {
    port.postMessage({
      type: "SCAN_STATUS",
      message: `Tìm thấy ${noteCards.length} ghi chú. Đang đọc nội dung chi tiết...`
    });
  }

  const results = [];

  // 2. Lần lượt mở từng ghi chú để trích xuất dữ liệu
  for (let i = 0; i < noteCards.length; i++) {
    if (isOperationCancelled) {
      if (port) port.postMessage({ type: "SCAN_CANCELLED", count: results.length });
      return { cancelled: true, results };
    }

    const card = noteCards[i];

    // Tự động cuộn thẻ hiện tại vào tầm mắt trước khi click
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    await sleep(120);

    // Click mở ghi chú
    const clickableArea = card.querySelector(".IZ65Hb-qJTHM-haAclf") || card;
    clickableArea.click();

    let title = "";
    let content = "";
    let editedAt = "";
    let isLoaded = false;
    let retries = 15;

    // Chờ modal xuất hiện và render dữ liệu đầy đủ
    while (retries > 0) {
      if (isOperationCancelled) break;
      await sleep(120);

      const modal = document.querySelector(".VIpgJd-TUo6Hb") ||
                    document.querySelector("div[role='dialog']") ||
                    document.querySelector(".IZ65Hb-QQhtn");

      if (modal) {
        // Tiêu đề
        const titleEl = modal.querySelector(".IZ65Hb-YPqjbf[aria-label='Title']") ||
                        modal.querySelector(".IZ65Hb-YPqjbf[aria-label='Tiêu đề']") ||
                        modal.querySelector(".IZ65Hb-YPqjbf");
        title = titleEl ? (titleEl.innerText || titleEl.value || "").trim() : "";

        // Nội dung văn bản
        const contentEl = modal.querySelector(".IZ65Hb-vIzZGf-L9AdLc-haAclf") ||
                          modal.querySelector(".fmcmS-h1U9Be-LS81yb") ||
                          modal.querySelector(".IZ65Hb-qJTHM-haAclf");
        content = contentEl ? contentEl.innerText.trim() : "";

        // Danh sách checklist nếu có
        const checkItems = modal.querySelectorAll(".IZ65Ce-wT32fe-LgT2ic, .Cm484d");
        if (checkItems.length > 0) {
          const listItems = Array.from(checkItems).map((item) => `- ${item.innerText.trim()}`).filter(Boolean);
          if (listItems.length > 0) {
            content = content ? `${content}\n${listItems.join("\n")}` : listItems.join("\n");
          }
        }

        // Thời gian
        const timeEl = modal.querySelector(".IZ65Hb-jfdpUb-fmcmS");
        editedAt = timeEl ? (timeEl.getAttribute("aria-label") || timeEl.innerText) : "";

        if (title !== "" || content !== "") {
          isLoaded = true;
          break;
        }
      }
      retries--;
    }

    const noteItem = {
      index: i + 1,
      title: title || "Không có tiêu đề",
      content: content || "",
      editedAt: editedAt
    };
    results.push(noteItem);

    if (port) {
      port.postMessage({
        type: "SCAN_PROGRESS",
        current: i + 1,
        total: noteCards.length,
        note: noteItem
      });
    }

    // Đóng modal
    const closeBtn = document.querySelector(".IZ65Hb-TvD9Pc") ||
                     Array.from(document.querySelectorAll("div[role='button']")).find(
                       (b) => b.innerText.trim() === "Close" || b.innerText.trim() === "Đóng"
                     );

    if (closeBtn) {
      closeBtn.click();
    } else {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true }));
    }

    await sleep(150);
  }

  if (port) {
    port.postMessage({
      type: "SCAN_COMPLETE",
      results: results,
      total: results.length
    });
  }

  return { success: true, results };
}

// Quick Scan: Reads visible cards or opens only cards matching filter
async function scanNotesQuick(options = {}, port) {
  isOperationCancelled = false;
  const cards = Array.from(document.querySelectorAll("div.IZ65Hb-n0tgWb"));
  const filterPrefix = options.prefix || "";
  const results = [];

  if (port) {
    port.postMessage({
      type: "SCAN_STATUS",
      message: `Tìm thấy ${cards.length} thẻ đang hiển thị. Đang phân tích...`
    });
  }

  for (let i = 0; i < cards.length; i++) {
    if (isOperationCancelled) break;
    const card = cards[i];

    // Card title
    const titleEl = card.querySelector(".IZ65Hb-YPqjbf");
    const title = titleEl ? titleEl.innerText.trim() : "";

    // If filter specified and title doesn't match, skip opening
    if (filterPrefix && !title.toLowerCase().includes(filterPrefix.toLowerCase())) {
      continue;
    }

    // Check if card has content preview
    const previewEl = card.querySelector(".IZ65Hb-vIzZGf-L9AdLc-haAclf") ||
                      card.querySelector(".IZ65Hb-qJTHM-haAclf");
    let content = previewEl ? previewEl.innerText.trim() : "";

    // If content looks truncated (e.g. contains '...' or preview is short), or if options.readFull = true,
    // open the card to get 100% full text without omissions
    if (options.openMatching && (!content || content.length < 500)) {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      await sleep(100);
      const clickEl = card.querySelector(".IZ65Hb-qJTHM-haAclf") || card;
      clickEl.click();

      let retries = 10;
      while (retries > 0) {
        await sleep(100);
        const modal = document.querySelector(".VIpgJd-TUo6Hb") ||
                      document.querySelector("div[role='dialog']") ||
                      document.querySelector(".IZ65Hb-QQhtn");
        if (modal) {
          const fullContentEl = modal.querySelector(".IZ65Hb-vIzZGf-L9AdLc-haAclf") ||
                                modal.querySelector(".fmcmS-h1U9Be-LS81yb") ||
                                modal.querySelector(".IZ65Hb-qJTHM-haAclf");
          if (fullContentEl && fullContentEl.innerText.trim()) {
            content = fullContentEl.innerText.trim();
            break;
          }
        }
        retries--;
      }

      // Close modal
      const closeBtn = document.querySelector(".IZ65Hb-TvD9Pc") ||
                       Array.from(document.querySelectorAll("div[role='button']")).find(
                         (b) => b.innerText.trim() === "Close" || b.innerText.trim() === "Đóng"
                       );
      if (closeBtn) closeBtn.click();
      else document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true }));
      await sleep(120);
    }

    results.push({
      index: results.length + 1,
      title: title || "Không có tiêu đề",
      content: content,
      cardIndex: i
    });

    if (port) {
      port.postMessage({
        type: "SCAN_PROGRESS",
        current: results.length,
        total: cards.length,
        note: results[results.length - 1]
      });
    }
  }

  if (port) {
    port.postMessage({
      type: "SCAN_COMPLETE",
      results: results,
      total: results.length
    });
  }

  return { success: true, results };
}

// Search Keep via Keep's native search input
async function filterKeepNotes(query) {
  const searchInput = document.querySelector("input.gb_Qe") ||
                      document.querySelector("input[aria-label='Search']") ||
                      document.querySelector("input[aria-label='Tìm kiếm']");
  if (!searchInput) return false;

  searchInput.focus();
  searchInput.value = query;
  searchInput.dispatchEvent(new Event("input", { bubbles: true }));
  searchInput.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, bubbles: true }));
  await sleep(800);
  return true;
}

// Port listener for long-running operations (Upload & Deep Scan)
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "keep-transfer-port") return;

  port.onMessage.addListener(async (msg) => {
    if (msg.action === "START_UPLOAD") {
      isOperationCancelled = false;
      try {
        await batchCreateNotes(msg.chunks, msg.delayMs || 800, port);
      } catch (err) {
        port.postMessage({ type: "UPLOAD_ERROR", error: err.message });
      }
    }

    if (msg.action === "START_DEEP_SCAN") {
      isOperationCancelled = false;
      try {
        await extractAllKeepNotesDeep(msg.options || {}, port);
      } catch (err) {
        port.postMessage({ type: "SCAN_ERROR", error: err.message });
      }
    }

    if (msg.action === "START_QUICK_SCAN") {
      isOperationCancelled = false;
      try {
        await scanNotesQuick(msg.options || {}, port);
      } catch (err) {
        port.postMessage({ type: "SCAN_ERROR", error: err.message });
      }
    }

    if (msg.action === "CANCEL_OPERATION") {
      isOperationCancelled = true;
      console.log("🛑 Nhận lệnh hủy thao tác từ popup.");
    }
  });
});

// Single message listener for quick checks
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "PING") {
    sendResponse({ status: "OK", url: window.location.href });
    return true;
  }

  if (request.action === "CANCEL_OPERATION") {
    isOperationCancelled = true;
    sendResponse({ status: "CANCELLED" });
    return true;
  }

  if (request.action === "FILTER_SEARCH") {
    filterKeepNotes(request.query).then((success) => sendResponse({ success }));
    return true;
  }
});

console.log("Google Keep Text File Transfer Content Script loaded.");
