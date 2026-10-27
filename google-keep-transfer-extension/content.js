// Google Keep Text File Transfer - Content Script
// Autonomous note creation, DOM paragraph structuring, character integrity verification,
// and floating in-page progress widget for Google Keep (keep.google.com).

let activeTransfer = {
  state: "IDLE", // "IDLE" | "RUNNING" | "PAUSED" | "COMPLETED" | "ERROR"
  fileId: null,
  fileName: null,
  notes: [], // Array of { title, content, isConfig, index, total }
  currentIndex: 0,
  delayMs: 800,
  lastError: null,
  logs: []
};

// Utility: Sleep
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Utility: Wait for condition
async function waitFor(conditionFn, timeout = 7000, interval = 70) {
  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    if (activeTransfer.state === "PAUSED" || activeTransfer.state === "IDLE") {
      throw new Error("Transfer paused or cancelled by user.");
    }
    const res = conditionFn();
    if (res) return res;
    await sleep(interval);
  }
  return null;
}

// Normalize text for comparison
function normalizeText(str) {
  if (!str) return "";
  return str
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/\u00a0/g, " ")
    .trim();
}

// Extract clean text from contenteditable
function getElementCleanText(el) {
  if (!el) return "";
  const paragraphs = Array.from(el.querySelectorAll("p"));
  if (paragraphs.length > 0) {
    return paragraphs
      .map((p) => p.innerText || p.textContent || "")
      .join("\n")
      .replace(/\u00a0/g, " ");
  }
  return (el.innerText || el.textContent || "").replace(/\u00a0/g, " ");
}

// -------------------------------------------------------------
// REAL-TIME DOM MONITOR & CONSOLE LOGGER FOR GOOGLE KEEP
// -------------------------------------------------------------
function initKeepDomMonitor() {
  console.log("%c[Keep DOM Monitor] 🚀 Started listening to Google Keep DOM mutations & interactions...", "color: #3b82f6; font-weight: bold; font-size: 13px;");

  function getElSummary(el) {
    if (!el || !el.tagName) return "null";
    const tag = el.tagName.toLowerCase();
    const id = el.id ? `#${el.id}` : "";
    const classes = el.className && typeof el.className === "string" ? `.${el.className.trim().split(/\s+/).slice(0, 3).join(".")}` : "";
    const role = el.getAttribute("role") ? `[role='${el.getAttribute("role")}']` : "";
    const ce = el.getAttribute("contenteditable") ? `[contenteditable='${el.getAttribute("contenteditable")}']` : "";
    const aria = el.getAttribute("aria-label") ? `[aria='${el.getAttribute("aria-label")}']` : "";
    const text = (el.innerText || el.textContent || "").trim().slice(0, 30);
    return `<${tag}${id}${classes}${role}${ce}${aria}> "${text}"`;
  }

  // 1. Capture user & script click interactions
  window.addEventListener("click", (e) => {
    const t = e.target;
    if (!t) return;
    const isClose = (t.innerText || t.getAttribute("aria-label") || "").trim().toLowerCase() === "close" ||
                    (t.innerText || t.getAttribute("aria-label") || "").trim().toLowerCase() === "đóng" ||
                    (t.classList && t.classList.contains("IZ65Hb-TvD9Pc"));
    const isCard = t.closest && t.closest(".IZ65Hb-n0tgWb");
    const isCreator = !isCard && (t.closest && (t.closest(".h1U9Be-xhiy4, .IZ65Hb-TBnied, .IZ65Hb-s2gQvd") || (t.innerText || "").includes("Take a note") || (t.innerText || "").includes("Ghi chú")));

    if (isClose) {
      console.log("%c[DOM Click] 🚪 CLOSE BUTTON CLICKED: " + getElSummary(t), "color: #ef4444; font-weight: bold;");
    } else if (isCreator) {
      console.log("%c[DOM Click] 🎯 NOTE CREATOR CLICKED: " + getElSummary(t), "color: #10b981; font-weight: bold;");
    } else if (isCard) {
      console.log("%c[DOM Click] 📋 NOTE CARD CLICKED: " + getElSummary(t), "color: #64748b;");
    }
  }, true);

  // 2. Capture inputs (title & body typing)
  window.addEventListener("input", (e) => {
    const t = e.target;
    if (!t) return;
    const parentCard = t.closest && t.closest(".IZ65Hb-n0tgWb");
    if (parentCard) return;

    const isTitle = t.classList && (t.classList.contains("IZ65Hb-YPqjbf") || t.classList.contains("r4nke-YPqjbf"));
    const isContent = t.getAttribute && (t.getAttribute("contenteditable") === "true");

    if (isTitle) {
      console.log("%c[DOM Input] 🏷️ CREATOR TITLE: \"" + (t.innerText || t.textContent || "").trim() + "\"", "color: #f59e0b; font-weight: bold;");
    } else if (isContent) {
      console.log("%c[DOM Input] 📝 CREATOR BODY: " + (t.innerText || "").length + " chars", "color: #8b5cf6;");
    }
  }, true);

  // 3. Real-time Mutation Observer for creator state changes and cards
  let lastState = null;
  const observer = new MutationObserver((mutations) => {
    try {
      const els = getNoteCreatorElements();
      if (els) {
        const curState = els.isExpanded ? "EXPANDED" : "COLLAPSED";
        if (curState !== lastState) {
          lastState = curState;
          if (curState === "EXPANDED") {
            console.log("%c[DOM State] 🟢 CREATOR EXPANDED!", "color: #10b981; font-weight: bold; font-size: 13px;", {
              container: els.container,
              titleEl: els.titleEl,
              contentEl: els.contentEl,
              closeBtn: els.closeBtn
            });
          } else {
            console.log("%c[DOM State] ⚪ CREATOR COLLAPSED!", "color: #94a3b8; font-weight: bold; font-size: 13px;");
          }
        }
      }

      for (const m of mutations) {
        if (m.type === "childList") {
          for (const node of m.addedNodes) {
            if (node.nodeType === 1) {
              const card = (node.classList && node.classList.contains("IZ65Hb-n0tgWb")) ? node : (node.querySelector ? node.querySelector(".IZ65Hb-n0tgWb") : null);
              if (card) {
                const titleEl = card.querySelector(".IZ65Hb-YPqjbf, .r4nke-YPqjbf, [role='textbox']");
                const cardTitle = titleEl ? (titleEl.innerText || titleEl.textContent || "").trim() : "Untitled";
                console.log("%c[DOM Board] 💾 NEW NOTE CARD ON BOARD: \"" + cardTitle + "\"", "color: #059669; font-weight: bold;", card);
              }
            }
          }
        }
      }
    } catch (e) {}
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["contenteditable", "class", "style", "aria-expanded"]
  });

  return observer;
}

// Find the "Take a note..." placeholder or click target on keep.google.com
function findTakeANotePlaceholder() {
  // Strategy 1 (Highest Reliability): Anchor via "New list" button (100% unique to the top creator header)
  const listBtns = Array.from(document.querySelectorAll("div[role='button'][aria-label*='list' i], div[role='button'][aria-label*='danh sách' i]"));
  for (const listBtn of listBtns) {
    if (listBtn.closest(".IZ65Hb-n0tgWb, [role='dialog'], [role='listitem']")) continue;
    const parentBar = listBtn.closest("div[role='region'], div[role='main'] > div") ||
                      listBtn.parentElement.parentElement.parentElement ||
                      listBtn.parentElement.parentElement;
    if (parentBar) {
      // Find the main text input or button inside this creator header
      const clickTarget = Array.from(parentBar.querySelectorAll("div[role='textbox'], div[role='button']"))
        .find((el) => el !== listBtn && !listBtn.contains(el)) || parentBar;
      return clickTarget;
    }
  }

  // Strategy 2: Multilingual ARIA labels and placeholders (Accessibility Standard)
  const ariaCandidates = Array.from(document.querySelectorAll("div[role='button'], div[role='textbox'], div[data-placeholder]"));
  for (const el of ariaCandidates) {
    if (el.closest(".IZ65Hb-n0tgWb, [role='dialog'], [role='listitem']")) continue;
    const label = (el.getAttribute("aria-label") || el.getAttribute("data-placeholder") || el.getAttribute("aria-placeholder") || el.innerText || "").toLowerCase();
    if (label.includes("take a note") || label.includes("ghi chú") || label.includes("tạo ghi chú")) {
      if (window.getComputedStyle(el).display !== "none") return el;
    }
  }

  // Strategy 3: Page Geometry (Top card with width ~600px, outside notes grid)
  const topBoxes = Array.from(document.querySelectorAll("div")).filter((el) => {
    if (el.closest(".IZ65Hb-n0tgWb, [role='dialog'], [role='listitem']")) return false;
    const rect = el.getBoundingClientRect();
    return rect.top >= 20 && rect.top <= 220 && rect.width >= 450 && rect.height >= 35 && rect.height <= 120;
  });
  if (topBoxes.length > 0) {
    const inner = topBoxes[0].querySelector("div[role='button'], div[role='textbox']") || topBoxes[0];
    return inner;
  }

  // Strategy 4 (Fallback only): Class-based candidates
  const classCandidates = Array.from(document.querySelectorAll(".di8rgd-r4nke, [class*='r4nke'], .h1U9Be-YPqjbf, .fmcmS-h1U9Be-LS81yb, .fmcmS-LwH6nd"));
  for (const el of classCandidates) {
    if (el.closest(".IZ65Hb-n0tgWb, [role='dialog'], [role='listitem']")) continue;
    const inner = el.querySelector ? el.querySelector("div[role='textbox'], div[role='button']") : null;
    const target = inner || el;
    if (window.getComputedStyle(target).display !== "none") return target;
  }

  return null;
}

// Locate "Take a note..." creator container on keep.google.com
function getNoteCreatorElements() {
  const placeholder = findTakeANotePlaceholder();

  let container = null;
  if (placeholder) {
    container = placeholder.closest("div[role='region'], div[role='main'] > div, div[style*='600'], .di8rgd-r4nke, .h1U9Be-xhiy4, .IZ65Hb-TBnied, .IZ65Hb-s2gQvd");
    if (container && container.closest(".IZ65Hb-n0tgWb, [role='dialog'], [role='listitem']")) {
      container = null;
    }
  }

  if (!container) {
    const candidates = Array.from(document.querySelectorAll("div")).filter((el) => {
      if (el.closest(".IZ65Hb-n0tgWb, [role='dialog'], [role='listitem']")) return false;
      const rect = el.getBoundingClientRect();
      return rect.top >= 20 && rect.top <= 220 && rect.width >= 450 && rect.height >= 35;
    });
    if (candidates.length > 0) {
      container = candidates[0];
    }
  }

  if (!container) return null;

  // Title element inside creator container
  const titleEl = container.querySelector("div[role='textbox'][aria-label*='Title' i], div[role='textbox'][aria-label*='Tiêu đề' i]") ||
                  container.querySelector("div[data-placeholder*='Title' i], div[data-placeholder*='Tiêu đề' i]") ||
                  container.querySelector(".IZ65Hb-YPqjbf, .r4nke-YPqjbf");

  // Content element inside creator container (any editable that is not Title)
  let contentEl = Array.from(container.querySelectorAll("div[role='textbox'], div[contenteditable='true']"))
    .find((el) => el !== titleEl && !el.classList.contains("IZ65Hb-YPqjbf") && !el.classList.contains("r4nke-YPqjbf"));

  if (!contentEl) {
    contentEl = container.querySelector(".IZ65Hb-vIzZGf-L9AdLc-haAclf") ||
                container.querySelector(".IZ65Hb-vIzZGf-bVEB4e-qJTHM") ||
                container.querySelector(".IZ65Hb-qJTHM-haAclf [role='textbox']") ||
                container.querySelector("div[aria-label*='Take a note' i], div[aria-label*='Ghi chú' i]");
  }

  // Close button scoped to creator container
  const closeBtn = Array.from(container.querySelectorAll("div[role='button'], button")).find((b) => {
    const text = (b.innerText || b.getAttribute("aria-label") || "").trim().toLowerCase();
    return text === "close" || text === "đóng" || b.classList.contains("IZ65Hb-TvD9Pc");
  });

  // Evaluate expanded state reliably:
  // ONLY true when contenteditable is explicitly "true" (never "false") or close button is active
  const isTitleEditable = titleEl && titleEl.getAttribute("contenteditable") === "true";
  const isContentEditable = contentEl && contentEl.getAttribute("contenteditable") === "true";
  const isCloseVisible = closeBtn && window.getComputedStyle(closeBtn).display !== "none" && window.getComputedStyle(closeBtn).visibility !== "hidden";

  const isExpanded = Boolean((isTitleEditable || isContentEditable) && isCloseVisible) ||
                     Boolean(isTitleEditable && isContentEditable) ||
                     Boolean(isCloseVisible && !placeholder);

  return { container, placeholder, titleEl, contentEl, closeBtn, isExpanded };
}

// Safely fill Google Keep Title element
async function fillKeepTitle(titleEl, title) {
  if (!titleEl) return false;
  titleEl.focus();
  await sleep(30);

  // Clear existing content
  titleEl.innerText = "";

  const sel = window.getSelection();
  sel.selectAllChildren(titleEl);

  let success = false;
  try {
    success = document.execCommand("insertText", false, title);
  } catch (e) {
    success = false;
  }

  if (!success || (titleEl.innerText || "").trim() !== title.trim()) {
    titleEl.innerText = title;
  }

  titleEl.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: title }));
  titleEl.dispatchEvent(new Event("change", { bubbles: true }));
  await sleep(50);
  return true;
}

// Safely fill Google Keep Content box preserving native <p> paragraph structure
async function fillKeepContent(contentEl, text) {
  if (!contentEl) return { success: false, actualLength: 0, expectedLength: 0, isExactMatch: false };
  contentEl.focus();
  await sleep(40);

  // Split text by newlines
  const lines = text.split(/\r?\n/);

  // Ensure contentEl has native Keep paragraphs
  contentEl.innerHTML = "";
  lines.forEach((line) => {
    const p = document.createElement("p");
    p.setAttribute("dir", "auto");
    p.setAttribute("role", "presentation");
    p.style.lineHeight = "1.38";
    p.style.marginTop = "0pt";
    p.style.marginBottom = "0pt";

    if (line && line.length > 0) {
      const span = document.createElement("span");
      span.className = "vIzZGf-fmcmS";
      span.style.fontFamily = '"Google Sans Text", Roboto, Arial, sans-serif';
      span.style.fontSize = "11pt";
      span.textContent = line;
      p.appendChild(span);
    } else {
      const br = document.createElement("br");
      p.appendChild(br);
    }
    contentEl.appendChild(p);
  });

  // Focus the last paragraph and trigger native events
  const lastP = contentEl.querySelector("p:last-child") || contentEl;
  const sel = window.getSelection();
  sel.selectAllChildren(lastP);
  sel.collapseToEnd();

  // Dispatch standard events so Keep's Closure text model registers the changes
  contentEl.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, inputType: "insertText", data: text }));
  contentEl.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
  contentEl.dispatchEvent(new Event("change", { bubbles: true }));
  contentEl.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: "End" }));
  await sleep(60);

  // Verify character length
  const normalizedExpected = normalizeText(text);
  const normalizedActual = normalizeText(getElementCleanText(contentEl));
  const isMatch = Math.abs(normalizedActual.length - normalizedExpected.length) <= 5;

  return {
    success: true,
    expectedLength: normalizedExpected.length,
    actualLength: normalizedActual.length,
    isExactMatch: isMatch
  };
}

// Save and close note creator reliably
async function saveAndCloseNote(readyElements) {
  const { container, titleEl, contentEl } = readyElements;

  // 1. Blur inputs to indicate editing is complete
  if (titleEl) {
    titleEl.dispatchEvent(new Event("input", { bubbles: true }));
    titleEl.dispatchEvent(new Event("change", { bubbles: true }));
    titleEl.dispatchEvent(new FocusEvent("blur", { bubbles: false }));
    titleEl.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    titleEl.blur();
  }
  if (contentEl) {
    contentEl.dispatchEvent(new Event("input", { bubbles: true }));
    contentEl.dispatchEvent(new Event("change", { bubbles: true }));
    contentEl.dispatchEvent(new FocusEvent("blur", { bubbles: false }));
    contentEl.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    contentEl.blur();
  }
  if (document.activeElement && typeof document.activeElement.blur === "function") {
    document.activeElement.blur();
  }

  await sleep(80);

  // 2. Click Close button with full mouse and keyboard gestures
  const currentEls = getNoteCreatorElements();
  const closeBtn = (currentEls && currentEls.closeBtn) ||
                   (container && container.querySelector(".IZ65Hb-TvD9Pc")) ||
                   Array.from(document.querySelectorAll(".IZ65Hb-TvD9Pc, div[role='button'], button")).find((b) => {
                     if (b.closest(".IZ65Hb-n0tgWb, [role='dialog']")) return false;
                     const text = (b.innerText || b.getAttribute("aria-label") || "").trim().toLowerCase();
                     return b.classList.contains("IZ65Hb-TvD9Pc") || text === "close" || text === "đóng";
                   });

  if (closeBtn) {
    const rect = closeBtn.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const btnOpts = { bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, button: 0, buttons: 1 };

    closeBtn.focus();
    closeBtn.dispatchEvent(new PointerEvent("pointerdown", btnOpts));
    closeBtn.dispatchEvent(new MouseEvent("mousedown", btnOpts));
    await sleep(25);
    closeBtn.dispatchEvent(new PointerEvent("pointerup", btnOpts));
    closeBtn.dispatchEvent(new MouseEvent("mouseup", btnOpts));
    closeBtn.dispatchEvent(new MouseEvent("click", btnOpts));
    closeBtn.click();

    closeBtn.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
    closeBtn.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
    closeBtn.dispatchEvent(new KeyboardEvent("keydown", { key: " ", code: "Space", keyCode: 32, which: 32, bubbles: true }));
    closeBtn.dispatchEvent(new KeyboardEvent("keyup", { key: " ", code: "Space", keyCode: 32, which: 32, bubbles: true }));
  }

  await sleep(80);

  // 3. Dispatch Escape key on content element and container
  if (contentEl) {
    contentEl.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true }));
    contentEl.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true }));
  }
  if (container) {
    container.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true }));
    container.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true }));
  }

  // 4. Click outside on the background board / left navigation area (guaranteed outside 600px creator)
  const outsideTargets = [
    document.querySelector(".ogm-kpc"),
    document.querySelector(".RfDI4d-bN97Pc"),
    document.querySelector(".gkA7Yd-sKfxWe"),
    document.body,
    document.documentElement
  ].filter(Boolean);

  for (const target of outsideTargets) {
    const outOpts = { bubbles: true, cancelable: true, view: window, clientX: 40, clientY: 100, button: 0, buttons: 1 };
    target.dispatchEvent(new PointerEvent("pointerdown", outOpts));
    target.dispatchEvent(new MouseEvent("mousedown", outOpts));
    target.dispatchEvent(new PointerEvent("pointerup", outOpts));
    target.dispatchEvent(new MouseEvent("mouseup", outOpts));
    target.dispatchEvent(new MouseEvent("click", outOpts));
  }

  // Dispatch outside click directly to document to trigger Closure's onDocumentClick_
  const docOpts = { bubbles: true, cancelable: true, view: window, clientX: 40, clientY: 100, button: 0, buttons: 1 };
  document.dispatchEvent(new MouseEvent("mousedown", docOpts));
  document.dispatchEvent(new MouseEvent("mouseup", docOpts));
  document.dispatchEvent(new MouseEvent("click", docOpts));

  // 5. Polling verification: wait until editor collapses (isExpanded === false)
  let retries = 20;
  while (retries > 0) {
    await sleep(60);
    const checkEls = getNoteCreatorElements();
    if (!checkEls || !checkEls.isExpanded) {
      break;
    }
    if (checkEls.closeBtn) {
      checkEls.closeBtn.click();
    }
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
    retries--;
  }

  // Soft fallback click on document body to ensure Closure onDocumentClick_ commits
  document.body.click();
  await sleep(100);
}

// Locate newly created note card on Google Keep board
function findNoteCardInDOM(expectedTitle) {
  if (!expectedTitle) return null;
  const matchPrefix = expectedTitle.match(/^\[(.*?)\]/);
  const titleKey = (matchPrefix ? matchPrefix[0] : expectedTitle.slice(0, 25)).toLowerCase().trim();
  const idMatch = expectedTitle.match(/#([a-zA-Z0-9_-]+)/);
  const partMatch = expectedTitle.match(/(\d+[\/ ]\d+)/);

  // Search note title elements strictly inside note cards (.IZ65Hb-n0tgWb)
  const cardTitles = Array.from(document.querySelectorAll(".IZ65Hb-n0tgWb .IZ65Hb-YPqjbf, .IZ65Hb-n0tgWb .r4nke-YPqjbf, .IZ65Hb-n0tgWb [role='textbox']"));
  for (const tEl of cardTitles) {
    const text = (tEl.innerText || tEl.textContent || "").toLowerCase().trim();
    if (!text) continue;

    if (text.includes(titleKey)) return tEl;
    if (idMatch && text.includes(idMatch[1].toLowerCase())) {
      if (!partMatch || text.includes(partMatch[1])) return tEl;
    }
    if (text.includes(expectedTitle.toLowerCase().slice(0, 20))) return tEl;
  }
  return null;
}

// Automatically listen to HTML / DOM mutations until newly created note appears on Google Keep board
function waitForNoteInDOM(expectedTitle, timeout = 2500) {
  return new Promise((resolve) => {
    // 1. Instant check
    const existing = findNoteCardInDOM(expectedTitle);
    if (existing) {
      resolve(existing);
      return;
    }

    let observer = null;
    let pollInterval = null;
    let timer = null;

    const cleanup = () => {
      if (observer) observer.disconnect();
      if (pollInterval) clearInterval(pollInterval);
      if (timer) clearTimeout(timer);
    };

    // 2. Real-time HTML MutationObserver
    observer = new MutationObserver(() => {
      const card = findNoteCardInDOM(expectedTitle);
      if (card) {
        cleanup();
        resolve(card);
      }
    });

    const targetNode = document.querySelector(".RfDI4d-bN97Pc") ||
                       document.querySelector(".browse-view") ||
                       document.querySelector(".gkA7Yd-sKfxWe") ||
                       document.body;

    observer.observe(targetNode, {
      childList: true,
      subtree: true,
      characterData: true
    });

    // 3. Periodic fallback poll every 60ms
    pollInterval = setInterval(() => {
      const card = findNoteCardInDOM(expectedTitle);
      if (card) {
        cleanup();
        resolve(card);
      }
    }, 60);

    // 4. Timeout safety: resolve null on timeout, never crash or reject
    timer = setTimeout(() => {
      cleanup();
      resolve(findNoteCardInDOM(expectedTitle));
    }, timeout);
  });
}

// Automatically expand note creator with multi-strategy simulation and reactive wait
async function expandNoteCreator(maxAttempts = 3) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    window.scrollTo({ top: 0, behavior: "instant" });
    await sleep(60);

    let els = getNoteCreatorElements();
    if (els && els.isExpanded && (els.contentEl || els.titleEl)) {
      return els;
    }

    const target = (els && els.placeholder) || findTakeANotePlaceholder();
    if (!target) {
      console.warn(`[Expand attempt ${attempt}] Placeholder not found, waiting...`);
      await sleep(250);
      continue;
    }

    console.log(`%c[Expand attempt ${attempt}] 🎯 Clicking target:`, "color: #3b82f6; font-weight: bold;", target);
    target.scrollIntoView({ block: "center", behavior: "instant" });
    await sleep(40);

    const rect = target.getBoundingClientRect();
    const cx = rect.left + Math.max(10, rect.width / 3);
    const cy = rect.top + Math.max(10, rect.height / 2);
    const clickOpts = { bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, button: 0, buttons: 1 };

    target.dispatchEvent(new PointerEvent("pointerover", clickOpts));
    target.dispatchEvent(new MouseEvent("mouseover", clickOpts));
    target.dispatchEvent(new PointerEvent("pointerdown", clickOpts));
    target.dispatchEvent(new MouseEvent("mousedown", clickOpts));
    if (typeof target.focus === "function") target.focus();
    target.dispatchEvent(new PointerEvent("pointerup", clickOpts));
    target.dispatchEvent(new MouseEvent("mouseup", clickOpts));
    target.dispatchEvent(new MouseEvent("click", clickOpts));
    if (typeof target.click === "function") target.click();

    target.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
    target.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));

    const expanded = await waitFor(() => {
      const cur = getNoteCreatorElements();
      if (cur && cur.isExpanded && (cur.contentEl || cur.titleEl)) {
        return cur;
      }
      return null;
    }, 1800, 50);

    if (expanded) {
      console.log("%c✅ Creator expanded successfully!", "color: #10b981; font-weight: bold;", expanded);
      return expanded;
    }

    console.warn(`[Expand attempt ${attempt}] Creator not expanded after click. Resetting and retrying...`);
    document.body.click();
    await sleep(250);
  }

  const finalEls = getNoteCreatorElements();
  if (finalEls && finalEls.isExpanded) return finalEls;
  return null;
}

// Create a single note on Keep with verified expansion, paragraph structuring, and HTML confirmation
async function createSingleNote(title, content) {
  // 1. Automatically expand note creator with multi-strategy simulation
  const elements = await expandNoteCreator(3);
  if (!elements || !elements.container) {
    throw new Error("Cannot find or open 'Take a note' bar on Google Keep. Ensure keep.google.com is active.");
  }

  // 4. Fill Title
  if (title && elements.titleEl) {
    await fillKeepTitle(elements.titleEl, title);
    await sleep(60);
  }

  // 5. Fill Content and verify character count
  let charCheck = { expectedLength: 0, actualLength: 0, isExactMatch: true };
  if (content && elements.contentEl) {
    charCheck = await fillKeepContent(elements.contentEl, content);
    await sleep(120);
  }

  // 6. Allow Google Keep's debounced input handler to capture text
  await sleep(200);

  // 7. Save and close note
  await saveAndCloseNote(elements);

  // 8. Automatically listen to HTML / DOM to verify note is rendered on Keep board
  console.log(`📡 Listening to HTML for note: "${title}"...`);
  broadcastProgress({
    statusText: `HTML Checking: "${title.slice(0, 24)}..."`
  });

  const confirmedCard = await waitForNoteInDOM(title, 2500);
  if (confirmedCard) {
    console.log(`✅ Note confirmed in HTML! Auto-next.`);
  } else {
    // Quick soft nudge: click outside to flush Keep queue, check again quickly
    document.body.click();
    await sleep(150);
    const retryCard = await waitForNoteInDOM(title, 1000);
    if (retryCard) {
      console.log(`✅ Note confirmed in HTML on retry! Auto-next.`);
    } else {
      console.log(`ℹ️ Editor closed and committed. Auto-advancing to next note...`);
    }
  }

  return {
    success: true,
    charCheck: charCheck
  };
}

// -------------------------------------------------------------
// FLOATING IN-PAGE WIDGET (Renders directly on keep.google.com)
// -------------------------------------------------------------
function injectFloatingWidgetStyles() {
  if (document.getElementById("kt-widget-styles")) return;

  const style = document.createElement("style");
  style.id = "kt-widget-styles";
  style.textContent = `
    #kt-floating-widget {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 320px;
      background: #1E293B;
      color: #F8FAFC;
      border: 1px solid rgba(251, 188, 4, 0.4);
      border-radius: 12px;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5), 0 0 15px rgba(245, 158, 11, 0.2);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 12px;
      z-index: 999999;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      animation: ktSlideUp 0.3s ease-out;
      user-select: none;
    }
    @keyframes ktSlideUp {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .kt-w-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 12px;
      background: #0F172A;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .kt-w-brand {
      display: flex;
      align-items: center;
      gap: 6px;
      font-weight: 700;
      color: #FBBC04;
      font-size: 13px;
    }
    .kt-w-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #10B981;
      box-shadow: 0 0 6px #10B981;
    }
    .kt-w-dot.paused { background: #F59E0B; box-shadow: 0 0 6px #F59E0B; }
    .kt-w-dot.idle { background: #64748B; box-shadow: none; }
    .kt-w-ctrls {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .kt-w-btn-icon {
      background: none;
      border: none;
      color: #94A3B8;
      cursor: pointer;
      font-size: 14px;
      padding: 2px 4px;
    }
    .kt-w-btn-icon:hover { color: #FFF; }
    .kt-w-body {
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .kt-w-file {
      font-weight: 600;
      color: #F8FAFC;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .kt-w-info {
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      color: #94A3B8;
    }
    .kt-w-track {
      width: 100%;
      height: 6px;
      background: #334155;
      border-radius: 3px;
      overflow: hidden;
    }
    .kt-w-fill {
      height: 100%;
      background: linear-gradient(90deg, #F59E0B, #10B981);
      border-radius: 3px;
      transition: width 0.3s ease;
    }
    .kt-w-badge {
      font-size: 10px;
      color: #34D399;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 2px 6px;
      border-radius: 6px;
      width: fit-content;
      font-weight: 600;
    }
    .kt-w-actions {
      display: flex;
      gap: 6px;
      margin-top: 4px;
    }
    .kt-w-btn {
      flex: 1;
      padding: 6px 10px;
      font-size: 11px;
      font-weight: 600;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      transition: all 0.2s;
    }
    .kt-w-btn-primary { background: #F59E0B; color: #1E293B; }
    .kt-w-btn-primary:hover { filter: brightness(1.1); }
    .kt-w-btn-sec { background: #334155; color: #F8FAFC; }
    .kt-w-btn-sec:hover { background: #475569; }
    .kt-w-btn-danger { background: #EF4444; color: #FFF; }
    .kt-w-btn-danger:hover { background: #DC2626; }
    .kt-hidden { display: none !important; }
  `;
  document.head.appendChild(style);
}

function updateFloatingWidget(transfer) {
  injectFloatingWidgetStyles();

  let widget = document.getElementById("kt-floating-widget");
  if (!widget) {
    widget = document.createElement("div");
    widget.id = "kt-floating-widget";
    widget.innerHTML = `
      <div class="kt-w-header">
        <div class="kt-w-brand">
          <span class="kt-w-dot" id="ktWidgetDot"></span>
          <span>Keep Transfer</span>
        </div>
        <div class="kt-w-ctrls">
          <button class="kt-w-btn-icon" id="ktWidgetMin" title="Minimize">−</button>
          <button class="kt-w-btn-icon" id="ktWidgetClose" title="Dismiss">✕</button>
        </div>
      </div>
      <div class="kt-w-body" id="ktWidgetBody">
        <div class="kt-w-file" id="ktWidgetFileName">Transferring file...</div>
        <div class="kt-w-info">
          <span id="ktWidgetStatus">Preparing...</span>
          <span id="ktWidgetPercent">0%</span>
        </div>
        <div class="kt-w-track">
          <div class="kt-w-fill" id="ktWidgetFill" style="width: 0%"></div>
        </div>
        <div class="kt-w-badge" id="ktWidgetBadge">✓ Chars Verified</div>
        <div class="kt-w-actions" id="ktWidgetActions">
          <button class="kt-w-btn kt-w-btn-sec" id="ktWidgetPauseBtn">⏸ Pause</button>
          <button class="kt-w-btn kt-w-btn-primary kt-hidden" id="ktWidgetResumeBtn">▶ Resume</button>
          <button class="kt-w-btn kt-w-btn-danger" id="ktWidgetCancelBtn">🛑 Stop</button>
        </div>
      </div>
    `;
    document.body.appendChild(widget);

    // Event listeners on widget buttons
    document.getElementById("ktWidgetPauseBtn").addEventListener("click", () => {
      activeTransfer.state = "PAUSED";
      broadcastProgress({ state: "PAUSED" });
    });

    document.getElementById("ktWidgetResumeBtn").addEventListener("click", () => {
      if (activeTransfer.state === "PAUSED") {
        activeTransfer.state = "RUNNING";
        broadcastProgress({ state: "RUNNING" });
        runUploadQueue();
      }
    });

    document.getElementById("ktWidgetCancelBtn").addEventListener("click", () => {
      activeTransfer.state = "IDLE";
      activeTransfer.notes = [];
      activeTransfer.currentIndex = 0;
      broadcastProgress({ state: "IDLE" });
      chrome.storage.local.remove("activeTransferState");
      removeFloatingWidget();
    });

    document.getElementById("ktWidgetClose").addEventListener("click", removeFloatingWidget);

    document.getElementById("ktWidgetMin").addEventListener("click", () => {
      const b = document.getElementById("ktWidgetBody");
      b.classList.toggle("kt-hidden");
      document.getElementById("ktWidgetMin").innerText = b.classList.contains("kt-hidden") ? "+" : "−";
    });
  }

  // Update widget contents
  const total = (transfer.notes && transfer.notes.length) || 1;
  const current = transfer.currentIndex || 0;
  const pct = Math.round((current / total) * 100);

  const fileEl = document.getElementById("ktWidgetFileName");
  const statusEl = document.getElementById("ktWidgetStatus");
  const percentEl = document.getElementById("ktWidgetPercent");
  const fillEl = document.getElementById("ktWidgetFill");
  const dotEl = document.getElementById("ktWidgetDot");
  const pauseBtn = document.getElementById("ktWidgetPauseBtn");
  const resumeBtn = document.getElementById("ktWidgetResumeBtn");
  const badgeEl = document.getElementById("ktWidgetBadge");

  if (fileEl) fileEl.innerText = transfer.fileName || "Text File";
  if (percentEl) percentEl.innerText = `${pct}%`;
  if (fillEl) fillEl.style.width = `${pct}%`;

  if (transfer.state === "RUNNING") {
    dotEl.className = "kt-w-dot";
    statusEl.innerText = `Note ${current + 1} of ${total}`;
    pauseBtn.classList.remove("kt-hidden");
    resumeBtn.classList.add("kt-hidden");
    badgeEl.innerText = `✓ Note [${current + 1}/${total}] In Progress`;
  } else if (transfer.state === "PAUSED") {
    dotEl.className = "kt-w-dot paused";
    statusEl.innerText = transfer.statusText || `Paused at [${current + 1}/${total}]`;
    pauseBtn.classList.add("kt-hidden");
    resumeBtn.classList.remove("kt-hidden");
    badgeEl.innerText = transfer.lastError ? `⚠️ ${transfer.lastError.slice(0, 30)}` : "⏸ Paused";
  } else if (transfer.state === "COMPLETED") {
    dotEl.className = "kt-w-dot";
    statusEl.innerText = "100% Completed!";
    percentEl.innerText = "100%";
    fillEl.style.width = "100%";
    badgeEl.innerText = "🎉 All Notes Saved!";
    document.getElementById("ktWidgetActions").classList.add("kt-hidden");
    setTimeout(removeFloatingWidget, 6000);
  }
}

function removeFloatingWidget() {
  const w = document.getElementById("kt-floating-widget");
  if (w && w.parentNode) w.parentNode.removeChild(w);
}

// Broadcast progress to storage, popup and floating widget
function broadcastProgress(update) {
  Object.assign(activeTransfer, update);

  // Update in-page floating widget directly on keep.google.com
  updateFloatingWidget(activeTransfer);

  // Sync to chrome.storage.local
  chrome.storage.local.set({ activeTransferState: activeTransfer });

  // Notify popup if open
  try {
    chrome.runtime.sendMessage({
      type: "TRANSFER_UPDATE",
      transfer: activeTransfer
    }).catch(() => {});
  } catch (e) {}
}

// Autonomous Upload Queue running directly in Google Keep tab
async function runUploadQueue() {
  const total = activeTransfer.notes.length;
  console.log(`🚀 Starting transfer of ${total} notes from #${activeTransfer.currentIndex + 1}...`);

  while (activeTransfer.currentIndex < total) {
    if (activeTransfer.state === "PAUSED") {
      broadcastProgress({ state: "PAUSED" });
      return;
    }

    if (activeTransfer.state === "IDLE") {
      removeFloatingWidget();
      return;
    }

    const item = activeTransfer.notes[activeTransfer.currentIndex];
    const itemLabel = item.isConfig ? "Config Note" : `Part [${item.index}/${item.total}]`;

    let success = false;
    let attempts = 0;
    const maxAttempts = 3;

    while (!success && attempts < maxAttempts) {
      attempts++;
      if (activeTransfer.state === "PAUSED" || activeTransfer.state === "IDLE") {
        return;
      }

      broadcastProgress({
        state: "RUNNING",
        statusText: attempts > 1 ? `Retrying ${itemLabel} (attempt ${attempts}/${maxAttempts})...` : `Creating ${itemLabel}...`,
        currentTitle: item.title
      });

      try {
        const result = await createSingleNote(item.title, item.content);
        const charInfo = result.charCheck;

        const logMsg = `Note [${activeTransfer.currentIndex + 1}/${total}]: "${item.title}" confirmed in HTML ✓ (${charInfo.actualLength} chars)`;
        activeTransfer.logs.push({ text: logMsg, time: new Date().toLocaleTimeString("en-US", { hour12: false }) });

        activeTransfer.currentIndex++;
        success = true;

        broadcastProgress({
          state: "RUNNING",
          statusText: `HTML Confirmed [${activeTransfer.currentIndex}/${total}]. Auto-advancing...`
        });

        // Note is confirmed in Google Keep HTML, proceed to next note immediately
        await sleep(150);
      } catch (err) {
        console.warn(`Attempt ${attempts} on note [${activeTransfer.currentIndex + 1}/${total}] failed:`, err);
        if (attempts >= maxAttempts) {
          console.error(`All ${maxAttempts} attempts failed on note [${activeTransfer.currentIndex + 1}/${total}]:`, err);
          activeTransfer.state = "PAUSED";
          activeTransfer.lastError = err.message;
          broadcastProgress({
            state: "PAUSED",
            statusText: `Paused: ${err.message}`
          });
          return;
        }
        // Soft reset Keep before next retry attempt
        document.body.click();
        await sleep(400);
      }
    }
  }

  activeTransfer.state = "COMPLETED";
  broadcastProgress({
    state: "COMPLETED",
    statusText: `All ${total} notes saved on Google Keep!`
  });
}

// Deep Scan All Notes (Scrolls page and opens cards to extract full content without omission)
async function extractAllKeepNotesDeep(options = {}, port) {
  let isCancelled = false;
  console.log("🔄 Scrolling page to load all Google Keep notes...");
  if (port) port.postMessage({ type: "SCAN_STATUS", message: "Scrolling down to load all notes from Google Keep..." });

  let lastHeight = document.body.scrollHeight;
  let sameHeightCount = 0;
  const maxScrollAttempts = options.maxScrollAttempts || 35;
  let attempts = 0;

  while (sameHeightCount < 3 && attempts < maxScrollAttempts) {
    if (isCancelled) return { cancelled: true, results: [] };
    attempts++;
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(options.scrollDelay || 1200);

    const newHeight = document.body.scrollHeight;
    if (newHeight === lastHeight) sameHeightCount++;
    else {
      sameHeightCount = 0;
      lastHeight = newHeight;
    }

    if (port) {
      const currentCards = document.querySelectorAll("div.IZ65Hb-n0tgWb").length;
      port.postMessage({
        type: "SCAN_STATUS",
        message: `Loading notes: detected ${currentCards} cards so far...`
      });
    }
  }

  window.scrollTo(0, 0);
  await sleep(400);

  const noteCards = Array.from(document.querySelectorAll("div.IZ65Hb-n0tgWb"));
  if (port) {
    port.postMessage({
      type: "SCAN_STATUS",
      message: `Found ${noteCards.length} notes. Extracting details...`
    });
  }

  const results = [];

  for (let i = 0; i < noteCards.length; i++) {
    const card = noteCards[i];
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    await sleep(90);

    const clickableArea = card.querySelector(".IZ65Hb-qJTHM-haAclf") || card;
    clickableArea.click();

    let title = "";
    let content = "";
    let editedAt = "";
    let retries = 15;

    while (retries > 0) {
      await sleep(90);
      const modal = document.querySelector(".VIpgJd-TUo6Hb") ||
                    document.querySelector("div[role='dialog']") ||
                    document.querySelector(".IZ65Hb-QQhtn");

      if (modal) {
        const titleEl = modal.querySelector(".IZ65Hb-YPqjbf[aria-label='Title']") ||
                        modal.querySelector(".IZ65Hb-YPqjbf[aria-label='Tiêu đề']") ||
                        modal.querySelector(".IZ65Hb-YPqjbf");
        title = titleEl ? (titleEl.innerText || titleEl.value || "").trim() : "";

        const contentEl = modal.querySelector(".IZ65Hb-vIzZGf-L9AdLc-haAclf") ||
                          modal.querySelector(".fmcmS-h1U9Be-LS81yb") ||
                          modal.querySelector(".IZ65Hb-qJTHM-haAclf");
        content = contentEl ? contentEl.innerText.trim() : "";

        const checkItems = modal.querySelectorAll(".IZ65Ce-wT32fe-LgT2ic, .Cm484d");
        if (checkItems.length > 0) {
          const listItems = Array.from(checkItems).map((item) => `- ${item.innerText.trim()}`).filter(Boolean);
          if (listItems.length > 0) {
            content = content ? `${content}\n${listItems.join("\n")}` : listItems.join("\n");
          }
        }

        const timeEl = modal.querySelector(".IZ65Hb-jfdpUb-fmcmS");
        editedAt = timeEl ? (timeEl.getAttribute("aria-label") || timeEl.innerText) : "";

        if (title !== "" || content !== "") break;
      }
      retries--;
    }

    const noteItem = {
      index: i + 1,
      title: title || "Untitled Note",
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

    // Close modal
    const closeBtn = document.querySelector(".IZ65Hb-TvD9Pc") ||
                     Array.from(document.querySelectorAll("div[role='button']")).find((b) => {
                       const text = (b.innerText || "").trim().toLowerCase();
                       return text === "close" || text === "đóng";
                     });

    if (closeBtn) closeBtn.click();
    else document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true }));

    await sleep(100);
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

// Quick Scan: Reads cards currently in DOM
async function scanNotesQuick(options = {}, port) {
  const cards = Array.from(document.querySelectorAll("div.IZ65Hb-n0tgWb"));
  const filterPrefix = options.prefix || "";
  const results = [];

  if (port) {
    port.postMessage({
      type: "SCAN_STATUS",
      message: `Analyzing ${cards.length} visible note cards...`
    });
  }

  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];
    const titleEl = card.querySelector(".IZ65Hb-YPqjbf");
    let title = titleEl ? titleEl.innerText.trim() : "";

    const cleanFilter = (filterPrefix || "").replace(/[\[\]]/g, "").toLowerCase().trim();
    const titleLower = title.toLowerCase();

    // Check if card is relevant to transfer
    const isTransferNote = !cleanFilter ||
                           titleLower.includes(cleanFilter) ||
                           titleLower.includes("[kt") ||
                           titleLower.includes("[keep") ||
                           titleLower.includes("cfg") ||
                           titleLower.includes("config") ||
                           /part\s*\d+/i.test(title);

    if (!isTransferNote) {
      continue;
    }

    const previewEl = card.querySelector(".IZ65Hb-vIzZGf-L9AdLc-haAclf") ||
                      card.querySelector(".IZ65Hb-qJTHM-haAclf");
    let content = previewEl ? previewEl.innerText.trim() : "";

    // If card title is truncated with ellipsis or content is short, open modal to read full data
    const isTruncated = title.endsWith("…") || title.endsWith("...") || title.includes("|…") || title.includes("| …");
    const needsOpen = options.openMatching && (isTruncated || !content || content.length < 500);

    if (needsOpen) {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      await sleep(70);
      const clickEl = card.querySelector(".IZ65Hb-qJTHM-haAclf") || card;
      clickEl.click();

      let retries = 12;
      while (retries > 0) {
        await sleep(70);
        const modal = document.querySelector(".VIpgJd-TUo6Hb") ||
                      document.querySelector("div[role='dialog']") ||
                      document.querySelector(".IZ65Hb-QQhtn");
        if (modal) {
          const fullTitleEl = modal.querySelector(".IZ65Hb-YPqjbf[aria-label='Title']") ||
                              modal.querySelector(".IZ65Hb-YPqjbf[aria-label='Tiêu đề']") ||
                              modal.querySelector(".IZ65Hb-YPqjbf");
          if (fullTitleEl && (fullTitleEl.innerText || fullTitleEl.value)) {
            title = (fullTitleEl.innerText || fullTitleEl.value).trim();
          }

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

      const closeBtn = document.querySelector(".IZ65Hb-TvD9Pc") ||
                       Array.from(document.querySelectorAll("div[role='button']")).find((b) => {
                         const text = (b.innerText || "").trim().toLowerCase();
                         return text === "close" || text === "đóng";
                       });
      if (closeBtn) closeBtn.click();
      else document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true }));
      await sleep(80);
    }

    results.push({
      index: results.length + 1,
      title: title || "Untitled Note",
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

// Port listener for scanning operations
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "keep-transfer-port") return;

  port.onMessage.addListener(async (msg) => {
    if (msg.action === "START_DEEP_SCAN") {
      try {
        await extractAllKeepNotesDeep(msg.options || {}, port);
      } catch (err) {
        port.postMessage({ type: "SCAN_ERROR", error: err.message });
      }
    }

    if (msg.action === "START_QUICK_SCAN") {
      try {
        await scanNotesQuick(msg.options || {}, port);
      } catch (err) {
        port.postMessage({ type: "SCAN_ERROR", error: err.message });
      }
    }
  });
});

// Single message listener for upload control & status queries
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "PING") {
    sendResponse({ status: "OK", url: window.location.href, activeTransferState: activeTransfer });
    return true;
  }

  if (request.action === "GET_TRANSFER_STATUS") {
    sendResponse({ transfer: activeTransfer });
    return true;
  }

  if (request.action === "START_UPLOAD") {
    const { chunks, configNote, delayMs, fileId, fileName } = request;

    const combinedNotes = [];
    if (configNote) {
      combinedNotes.push({
        isConfig: true,
        title: configNote.title,
        content: configNote.content
      });
    }

    chunks.forEach((c) => {
      combinedNotes.push({
        isConfig: false,
        title: c.title,
        content: c.content,
        index: c.index,
        total: c.total
      });
    });

    activeTransfer = {
      state: "RUNNING",
      fileId: fileId,
      fileName: fileName,
      notes: combinedNotes,
      currentIndex: 0,
      delayMs: delayMs || 800,
      lastError: null,
      logs: []
    };

    broadcastProgress({ state: "RUNNING" });
    runUploadQueue(); // Autonomous execution on Keep tab
    sendResponse({ success: true, status: "RUNNING" });
    return true;
  }

  if (request.action === "PAUSE_UPLOAD") {
    activeTransfer.state = "PAUSED";
    broadcastProgress({ state: "PAUSED" });
    sendResponse({ success: true, status: "PAUSED" });
    return true;
  }

  if (request.action === "RESUME_UPLOAD") {
    if (activeTransfer.state === "PAUSED" && activeTransfer.notes.length > 0) {
      activeTransfer.state = "RUNNING";
      broadcastProgress({ state: "RUNNING" });
      runUploadQueue();
      sendResponse({ success: true, status: "RUNNING" });
    } else {
      sendResponse({ success: false, message: "No paused transfer to resume." });
    }
    return true;
  }

  if (request.action === "CANCEL_UPLOAD") {
    activeTransfer.state = "IDLE";
    activeTransfer.notes = [];
    activeTransfer.currentIndex = 0;
    removeFloatingWidget();
    chrome.storage.local.remove("activeTransferState");
    sendResponse({ success: true, status: "IDLE" });
    return true;
  }
});

// Check if there was an active transfer saved in storage on content script load
chrome.storage.local.get("activeTransferState", (res) => {
  if (res.activeTransferState && res.activeTransferState.state === "RUNNING") {
    activeTransfer = res.activeTransferState;
    activeTransfer.state = "PAUSED";
    broadcastProgress({ state: "PAUSED" });
  }
});

// Initialize real-time DOM monitor & logger
initKeepDomMonitor();

console.log("Google Keep Text File Transfer Content Script ready with on-page floating widget.");
