// Google Forms Question Collector - Content Script

(function () {
  'use strict';

  // Prevent multiple injections
  if (window.__GFC_INJECTED__) return;
  window.__GFC_INJECTED__ = true;

  let isCrawling = false;
  let crawlAbortController = false;

  // Helper to check if extension context is still active (prevents "Extension context invalidated" errors)
  function isExtensionValid() {
    try {
      return !!(typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.id);
    } catch (e) {
      return false;
    }
  }

  function safeStorageGet(keys, callback) {
    if (!isExtensionValid()) return;
    try {
      chrome.storage.local.get(keys, (res) => {
        if (!isExtensionValid() || (chrome.runtime && chrome.runtime.lastError)) return;
        if (callback) callback(res || {});
      });
    } catch (e) {}
  }

  function safeStorageSet(data, callback) {
    if (!isExtensionValid()) return;
    try {
      chrome.storage.local.set(data, () => {
        if (!isExtensionValid() || (chrome.runtime && chrome.runtime.lastError)) return;
        if (callback) callback();
      });
    } catch (e) {}
  }

  function safeSendMessage(msg, callback) {
    if (!isExtensionValid()) return;
    try {
      chrome.runtime.sendMessage(msg, (resp) => {
        if (!isExtensionValid() || (chrome.runtime && chrome.runtime.lastError)) return;
        if (callback) callback(resp);
      });
    } catch (e) {}
  }

  // Generate unique form key from URL (works with /u/0/, /viewform, /formResponse, etc.)
  function getFormKey() {
    try {
      const match = (window.location.href || window.location.pathname).match(/\/d\/(?:e\/)?([a-zA-Z0-9_-]+)/);
      if (match && match[1]) {
        return 'form_' + match[1];
      }
    } catch (e) {}
    const cleanPath = window.location.pathname.replace(/\/(viewform|formResponse|edit|closedform).*$/, '');
    return 'form_' + cleanPath;
  }

  // Safe string cleaner
  function cleanText(str) {
    if (!str) return '';
    return str
      .replace(/[\u200B-\u200D\uFEFF]/g, '') // remove zero-width chars
      .replace(/\s+/g, ' ')
      .trim();
  }

  // Strip option prefix (e.g. "A. ", "B) ", "1. ")
  // Do NOT strip if the entire option is just a single character like "A", "B", "1"
  function stripOptionPrefix(text) {
    if (!text) return '';
    let cleaned = cleanText(text);
    if (cleaned.length > 2) {
      cleaned = cleaned.replace(/^\(?[A-Za-z0-9]\)?[\.\)\:\-]\s+/, '').trim();
    }
    return cleaned;
  }

  // Convert an HTML Image element to Base64 Data URL (no external links)
  async function getBase64Image(imgElem) {
    if (!imgElem) return null;
    const src = imgElem.src;
    if (!src || src.includes('cleardot.gif')) return null;
    if (src.startsWith('data:image/')) return src;

    // 1. Try Canvas directly from rendered DOM image (zero latency)
    try {
      if (imgElem.complete && imgElem.naturalWidth > 0) {
        const canvas = document.createElement('canvas');
        canvas.width = imgElem.naturalWidth;
        canvas.height = imgElem.naturalHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(imgElem, 0, 0);
        const dataUrl = canvas.toDataURL('image/png');
        if (dataUrl && dataUrl.length > 100) {
          return dataUrl;
        }
      }
    } catch (e) {
      // Canvas tainted or not ready
    }

    // 2. Fetch image blob with 2s timeout and convert to Base64 Data URL
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);
      const res = await fetch(src, { credentials: 'include', signal: controller.signal });
      clearTimeout(timeoutId);
      const blob = await res.blob();
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.onerror = () => resolve(src);
        reader.readAsDataURL(blob);
      });
    } catch (e) {
      return src; // fallback if network fetch fails
    }
  }

  // Get unique page signature to detect transitions accurately
  function getPageSignature() {
    const pageText = cleanText(document.querySelector('#lpd4pf, .HZh16d')?.innerText || '');
    const pBar = document.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow') || '';
    const sectionHeader = cleanText(document.querySelector('.F9yp7e, .ahS2Le, .m7w29c [role="heading"]')?.innerText || '');
    const visibleElements = Array.from(document.querySelectorAll('.Qr7Oae, .geS5n, div[role="listitem"]'))
      .filter(el => isElementVisible(el))
      .slice(0, 5)
      .map(el => {
        const h = el.querySelector('[role="heading"], .M7eMe');
        const img = el.querySelector('img');
        return h ? cleanText(h.innerText).slice(0, 20) : (img ? img.src.slice(-20) : el.id || '');
      })
      .filter(Boolean)
      .join('__');

    if (!pageText && !pBar && !visibleElements) {
      return ''; // Blank or transitioning DOM state
    }

    return `${pageText}__${pBar}__${sectionHeader}__${visibleElements}`;
  }

  // Wait for questions to be present and visible in DOM after a page transition
  async function waitForPageReady(timeoutMs = 5000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const visibleItems = Array.from(document.querySelectorAll('.Qr7Oae, div[role="listitem"], .geS5n'))
        .filter(el => isElementVisible(el));
      if (visibleItems.length > 0) {
        await new Promise(r => setTimeout(r, 400));
        return true;
      }
      await new Promise(r => setTimeout(r, 150));
    }
    return false;
  }

  // Extract page metadata & questions from current DOM (with Base64 images)
  async function extractCurrentPageData() {
    // 1. Form Title
    let formTitle = '';
    const titleElem = document.querySelector('div[role="heading"][aria-level="1"], .F9yp7e, .ahS2Le, .freebirdFormviewerViewHeaderTitle');
    if (titleElem) {
      formTitle = cleanText(titleElem.innerText);
    }
    if (!formTitle) {
      formTitle = cleanText(document.title.replace(/- Google Biểu mẫu|- Google Forms/i, ''));
    }
    if (!formTitle) {
      formTitle = 'Biểu mẫu không có tiêu đề';
    }

    // 2. Form Description
    let formDescription = '';
    const descElem = document.querySelector('.liS6Hc, .freebirdFormviewerViewHeaderDescription');
    if (descElem) {
      formDescription = cleanText(descElem.innerText);
    }

    // 3. Page Progress Info (e.g. "Trang 2 trong tổng số 7")
    let pageInfo = '';
    const pageElem = document.querySelector('#lpd4pf, .HZh16d');
    if (pageElem) {
      pageInfo = cleanText(pageElem.innerText);
    } else {
      const pBar = document.querySelector('[role="progressbar"]');
      if (pBar) {
        const val = pBar.getAttribute('aria-valuenow');
        if (val) pageInfo = `Tiến độ: ${val}%`;
      }
    }

    // 4. Scan Items (Sections and Questions)
    const items = document.querySelectorAll('.Qr7Oae, div[role="listitem"]');
    let currentSection = '';
    const questions = [];

    for (let index = 0; index < items.length; index++) {
      const item = items[index];

      // Check if item is a Section Header
      const sectionElem = item.querySelector('div[role="heading"][aria-level="2"], .KkG9vf, .aG9Vid');
      if (sectionElem && !item.querySelector('[role="heading"][aria-level="3"]') && !item.querySelector('[role="radiogroup"]') && !item.querySelector('input, textarea')) {
        currentSection = cleanText(sectionElem.innerText);
        continue;
      }

      // Check for attached Image in Question (convert to Base64)
      let questionImage = null;
      const imgElem = item.querySelector('.gCouxf img, .HxhGpf, .y6GzNb img, .Hvn9fb img, .tP9Zud img, img.Hvn9fb');
      if (imgElem) {
        questionImage = await getBase64Image(imgElem);
      }

      // Extract Question Title
      let qTitleElem = item.querySelector('div[role="heading"][aria-level="3"], .M7eMe, .HoXoMd');
      let qTitle = qTitleElem ? cleanText(qTitleElem.innerText) : '';

      // Handle questions with no text title (Image-based questions)
      if (!qTitle) {
        if (questionImage) {
          qTitle = '[Câu hỏi hình ảnh]';
        } else if (item.querySelector('[role="radiogroup"], [role="checkbox"], input, textarea')) {
          qTitle = '[Câu hỏi không tiêu đề]';
        } else {
          continue; // not a question item
        }
      }

      // Extract Description / Subtext
      let qDesc = '';
      const descBox = item.querySelector('.gubaDc, .OIC90c');
      if (descBox) {
        const txt = cleanText(descBox.innerText);
        if (txt && txt !== qTitle) {
          qDesc = txt;
        }
      }

      // Points (e.g. "1 điểm", "1 point")
      let points = '';
      const noteElem = item.querySelector('[role="note"], .FUQCPb, .nUvMO');
      if (noteElem) {
        points = cleanText(noteElem.innerText);
      }

      // Required indicator
      const isRequired = !!item.querySelector('.vVVJbe, .vnumgf, [aria-label*="bắt buộc"], [aria-label*="required"], [aria-required="true"]') || qTitle.includes('*');
      if (isRequired) {
        qTitle = qTitle.replace(/\s*\*\s*$/, '').trim();
      }

      // Check if this is an administrative personal information field
      const isPersonalInfo = /^(STT|Họ và tên|Họ tên|Tên|Khoa|Lớp|Email|Mã số|MSSV|SBD|Số báo danh|Lớp học phần|Học kỳ|Phòng thi)/i.test(qTitle);

      // Determine Question Type and Options
      let type = 'unknown';
      let options = [];
      let userAnswer = [];
      let correctAnswer = null;
      let feedback = null;

      // Check for Multiple Choice (Radio)
      const radios = item.querySelectorAll('[role="radio"]');
      if (radios.length > 0) {
        type = 'multiple_choice';
        for (let r of radios) {
          let val = r.getAttribute('data-value') || r.getAttribute('aria-label');
          if (!val) {
            const labelSpan = r.closest('label')?.querySelector('.snByac, .aDTYNe');
            if (labelSpan) val = labelSpan.innerText;
          }
          if (!val) {
            val = r.innerText;
          }
          // Strip prefix A., B., C.
          val = stripOptionPrefix(val);

          // Option image converted to Base64
          const optImgElem = r.closest('.nWQGrd, label, .docssharedWizToggleLabeledContainer')?.querySelector('.LAANW img, .QU5LQc, img:not(.Hvn9fb)');
          let optImgBase64 = null;
          if (optImgElem) {
            optImgBase64 = await getBase64Image(optImgElem);
          }

          if (val && !options.some(o => o.text === val)) {
            options.push({ text: val, image: optImgBase64 });
          }

          if (r.getAttribute('aria-checked') === 'true') {
            userAnswer.push(val);
          }
        }
      }

      // Check for Checkboxes (Multiple Choice)
      const checkboxes = item.querySelectorAll('[role="checkbox"]');
      if (checkboxes.length > 0) {
        type = 'checkbox';
        for (let cb of checkboxes) {
          let val = cb.getAttribute('data-value') || cb.getAttribute('aria-label');
          if (!val) {
            const labelSpan = cb.closest('label')?.querySelector('.snByac, .aDTYNe');
            if (labelSpan) val = labelSpan.innerText;
          }
          if (!val) {
            val = cb.innerText;
          }
          val = stripOptionPrefix(val);

          const optImgElem = cb.closest('.nWQGrd, label, .docssharedWizToggleLabeledContainer')?.querySelector('.LAANW img, .QU5LQc, img:not(.Hvn9fb)');
          let optImgBase64 = null;
          if (optImgElem) {
            optImgBase64 = await getBase64Image(optImgElem);
          }

          if (val && !options.some(o => o.text === val)) {
            options.push({ text: val, image: optImgBase64 });
          }

          if (cb.getAttribute('aria-checked') === 'true') {
            userAnswer.push(val);
          }
        }
      }

      // Check for Short Text Answer
      const textInput = item.querySelector('input[type="text"]:not([type="hidden"])');
      if (textInput && type === 'unknown') {
        type = 'short_text';
        if (textInput.value) {
          userAnswer.push(cleanText(textInput.value));
        }
      }

      // Check for Paragraph Answer
      const textarea = item.querySelector('textarea');
      if (textarea && type === 'unknown') {
        type = 'paragraph';
        if (textarea.value) {
          userAnswer.push(cleanText(textarea.value));
        }
      }

      // Check for Dropdown
      const listbox = item.querySelector('[role="listbox"]');
      if (listbox && type === 'unknown') {
        type = 'dropdown';
        const optElements = listbox.querySelectorAll('[role="option"]');
        optElements.forEach(o => {
          let val = cleanText(o.innerText);
          val = stripOptionPrefix(val);
          if (val && val !== 'Chọn' && val !== 'Choose' && !options.some(opt => opt.text === val)) {
            options.push({ text: val, image: null });
          }
        });
      }

      // Check for Linear Scale
      const scaleRadios = item.querySelectorAll('[role="radiogroup"] [role="radio"]');
      if (scaleRadios.length > 0 && type === 'unknown') {
        type = 'linear_scale';
      }

      // Check data-params attribute for questions if options were missed
      const dataParamsAttr = item.getAttribute('data-params') || item.querySelector('[data-params]')?.getAttribute('data-params');
      let entryId = null;
      if (dataParamsAttr) {
        try {
          let raw = dataParamsAttr.trim();
          if (raw.startsWith('%.@.')) {
            raw = '[' + raw.substring(4);
          }
          raw = raw.replace(/\\(?!["\\/bfnrtu]|u[0-9a-fA-F]{4})/g, '\\\\');
          const parsed = JSON.parse(raw);
          const qdata = parsed[0];
          if (Array.isArray(qdata)) {
            entryId = qdata[0];
            if (options.length === 0 && qdata[4] && qdata[4][0] && Array.isArray(qdata[4][0][1])) {
              qdata[4][0][1].forEach(opt => {
                if (opt && opt[0]) {
                  const optText = stripOptionPrefix(opt[0]);
                  if (!options.some(o => o.text === optText)) {
                    options.push({ text: optText, image: null });
                  }
                }
              });
              if (type === 'unknown' && options.length > 0) {
                type = 'multiple_choice';
              }
            }
          }
        } catch (e) {}
      }

      // Check for Correct Answer & Feedback (Quiz Review / viewscore mode)
      const correctBox = item.querySelector('.GDUsPd, .c2yFc, .s3v03d, [aria-label*="Câu trả lời đúng"], [aria-label*="Correct"]');
      if (correctBox) {
        correctAnswer = cleanText(correctBox.innerText.replace(/^(Câu trả lời đúng|Correct answer):\s*/i, ''));
        correctAnswer = stripOptionPrefix(correctAnswer);
      }
      const feedbackBox = item.querySelector('.N3Oo6b, .G95uG');
      if (feedbackBox) {
        feedback = cleanText(feedbackBox.innerText);
      }

      // Permanent Question Identifier (stable across page refresh and shuffle!)
      const stableId = entryId ? String(entryId) : ('q_' + (questions.length + 1) + '_' + Math.random().toString(36).substr(2, 6));

      questions.push({
        id: stableId,
        section: currentSection,
        title: qTitle,
        description: qDesc,
        points: points,
        isRequired: isRequired,
        isPersonalInfo: isPersonalInfo,
        type: type,
        image: questionImage, // Base64 Data URL!
        options: options,
        userAnswer: userAnswer,
        correctAnswer: correctAnswer,
        explanation: feedback || '',
        page: pageInfo
      });
    }

    return {
      title: formTitle,
      description: formDescription,
      pageInfo: pageInfo,
      url: window.location.href,
      questions: questions
    };
  }

  // Get question canonical key for deduplication across refreshes & shuffles
  function getQuestionCanonicalKey(q) {
    // 1. Stable Question ID from Google Form if present
    if (q.id && !String(q.id).startsWith('q_')) {
      return 'id:' + q.id;
    }
    // 2. Normalized Title
    const normTitle = (q.title || '')
      .toLowerCase()
      .replace(/^câu\s*\d+\s*[\:\.\-]\s*/i, '')
      .replace(/\s+/g, ' ')
      .trim();

    if ((normTitle === '[câu hỏi hình ảnh]' || !normTitle) && q.image) {
      return 'img:' + q.image.substring(0, 100);
    }
    return 'title:' + (q.section ? q.section.toLowerCase() + '::' : '') + normTitle;
  }

  // Merge questions into existing storage with smart deduplication against shuffle & refresh
  function mergeQuestions(existingQuestions, newQuestions) {
    const map = new Map();

    // Index existing questions
    existingQuestions.forEach(q => {
      const key = getQuestionCanonicalKey(q);
      map.set(key, q);
    });

    // Merge or add new questions
    newQuestions.forEach(nq => {
      const key = getQuestionCanonicalKey(nq);

      if (map.has(key)) {
        const existing = map.get(key);

        // Preserve non-empty metadata
        if (!existing.points && nq.points) existing.points = nq.points;
        if (!existing.section && nq.section) existing.section = nq.section;
        if (!existing.correctAnswer && nq.correctAnswer) existing.correctAnswer = nq.correctAnswer;
        if (!existing.explanation && nq.explanation) existing.explanation = nq.explanation;

        // Upgrade image if new scan has Base64
        if ((!existing.image || !existing.image.startsWith('data:image/')) && nq.image) {
          existing.image = nq.image;
        }

        // Merge options without duplicates even if Google shuffled option order on refresh!
        if (nq.options && nq.options.length > 0) {
          if (!existing.options || existing.options.length === 0) {
            existing.options = nq.options;
          } else {
            // Check each option
            nq.options.forEach(nOpt => {
              const matchOpt = existing.options.find(eOpt => eOpt.text.toLowerCase() === nOpt.text.toLowerCase());
              if (matchOpt) {
                // If existing option image is missing and new has Base64, update it
                if (!matchOpt.image && nOpt.image) {
                  matchOpt.image = nOpt.image;
                }
              } else {
                existing.options.push(nOpt);
              }
            });
          }
        }

        if (nq.userAnswer && nq.userAnswer.length > 0) {
          existing.userAnswer = nq.userAnswer;
        }
      } else {
        map.set(key, nq);
      }
    });

    return Array.from(map.values());
  }

  // Save collected data to chrome.storage.local safely
  function saveCollectedData(pageData, callback) {
    if (!isExtensionValid()) {
      if (callback) callback({ total: 0, newAdded: 0, pageQuestions: pageData?.questions?.length || 0 });
      return;
    }
    const formKey = getFormKey();
    safeStorageGet(['forms', 'activeFormKey', 'settings'], (res) => {
      const forms = res.forms || {};
      const currentForm = forms[formKey] || {
        key: formKey,
        title: pageData.title,
        description: pageData.description,
        url: pageData.url,
        createdAt: new Date().toISOString(),
        questions: [],
        visitedPages: []
      };

      currentForm.title = pageData.title || currentForm.title;
      currentForm.description = pageData.description || currentForm.description;
      currentForm.url = pageData.url;
      currentForm.lastUpdated = new Date().toISOString();

      if (pageData.pageInfo && !currentForm.visitedPages.includes(pageData.pageInfo)) {
        currentForm.visitedPages.push(pageData.pageInfo);
      }

      // Merge & deduplicate
      const prevCount = currentForm.questions.length;
      currentForm.questions = mergeQuestions(currentForm.questions, pageData.questions);
      const newAdded = currentForm.questions.length - prevCount;

      forms[formKey] = currentForm;

      safeStorageSet({
        forms: forms,
        activeFormKey: formKey
      }, () => {
        // Update badge
        safeSendMessage({
          action: 'UPDATE_BADGE',
          count: currentForm.questions.length
        });

        // Update floating widget
        updateFloatingWidget(currentForm.questions.length, pageData.pageInfo);

        if (callback) {
          callback({
            total: currentForm.questions.length,
            newAdded: newAdded,
            pageQuestions: pageData.questions.length
          });
        }
      });
    });
  }

  // Floating Toast in Google Form page
  function showToast(message, type = 'info', duration = 3000) {
    let toast = document.querySelector('.gfc-toast-notice');
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'gfc-toast-notice';
      document.body.appendChild(toast);
    }
    toast.className = `gfc-toast-notice gfc-toast-${type}`;
    toast.innerHTML = `<span>${message}</span>`;
    toast.style.display = 'flex';

    if (window.__gfcToastTimer) clearTimeout(window.__gfcToastTimer);
    window.__gfcToastTimer = setTimeout(() => {
      if (toast && toast.parentNode) {
        toast.style.display = 'none';
      }
    }, duration);
  }

  // Create or Update Floating Widget on Google Forms
  function createFloatingWidget() {
    if (document.getElementById('gfc-floating-widget-container')) return;

    const container = document.createElement('div');
    container.id = 'gfc-floating-widget-container';
    container.innerHTML = `
      <!-- Minimized Pill -->
      <button class="gfc-pill-btn" id="gfc-pill" title="Mở bảng thu thập câu hỏi Google Form">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm6 12H6v-1.4c0-2 4-3.1 6-3.1s6 1.1 6 3.1V18z"/>
        </svg>
        <span>Thu thập câu hỏi</span>
        <span class="gfc-pill-badge" id="gfc-badge-count">0</span>
      </button>

      <!-- Expanded Panel -->
      <div class="gfc-panel gfc-hidden" id="gfc-panel">
        <div class="gfc-header">
          <div class="gfc-header-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/>
            </svg>
            <span>Form Question Collector</span>
          </div>
          <div class="gfc-header-actions">
            <button class="gfc-icon-btn" id="gfc-btn-minimize" title="Thu nhỏ">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 13H5v-2h14v2z"/></svg>
            </button>
            <button class="gfc-icon-btn" id="gfc-btn-close" title="Ẩn nút">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
            </button>
          </div>
        </div>
        <div class="gfc-body">
          <div class="gfc-stat-row">
            <span class="gfc-stat-label">Tổng câu đã thu thập:</span>
            <span class="gfc-stat-val" id="gfc-stat-total">0 câu</span>
          </div>
          <div class="gfc-stat-row" id="gfc-stat-page-row">
            <span class="gfc-stat-label">Trang hiện tại:</span>
            <span class="gfc-stat-val" id="gfc-stat-page">-</span>
          </div>
          
          <button class="gfc-action-btn gfc-btn-crawl" id="gfc-btn-autocrawl" style="padding: 10px 12px; font-weight: 700; font-size: 13px;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
            <span id="gfc-crawl-text">⚡ Tự động thu thập tất cả các trang</span>
          </button>

          <button class="gfc-action-btn gfc-btn-outline" id="gfc-btn-open-web">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
            <span>Mở Web Ôn Tập (Quiz App)</span>
          </button>

          <button class="gfc-action-btn gfc-btn-secondary" id="gfc-btn-copy">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
            <span>Sao chép nhanh đề thi</span>
          </button>
          
          <div class="gfc-footer-hint">Tự động gom & chuyển đổi ảnh Base64</div>
        </div>
      </div>
    `;

    document.body.appendChild(container);

    const pill = container.querySelector('#gfc-pill');
    const panel = container.querySelector('#gfc-panel');
    const btnMin = container.querySelector('#gfc-btn-minimize');
    const btnClose = container.querySelector('#gfc-btn-close');
    const btnAutoCrawl = container.querySelector('#gfc-btn-autocrawl');
    const btnCopy = container.querySelector('#gfc-btn-copy');
    const btnOpenWeb = container.querySelector('#gfc-btn-open-web');

    pill.addEventListener('click', () => {
      pill.classList.add('gfc-hidden');
      panel.classList.remove('gfc-hidden');
    });

    btnMin.addEventListener('click', () => {
      panel.classList.add('gfc-hidden');
      pill.classList.remove('gfc-hidden');
    });

    btnClose.addEventListener('click', () => {
      container.style.display = 'none';
      showToast('Đã ẩn nút nổi. Bạn có thể mở lại từ Extension Popup!', 'info');
    });

    btnAutoCrawl.addEventListener('click', () => {
      if (isCrawling) {
        stopAutoCrawl();
      } else {
        startAutoCrawl();
      }
    });

    btnCopy.addEventListener('click', () => {
      copyCollectedQuestionsQuickly();
    });

    btnOpenWeb.addEventListener('click', () => {
      if (!isExtensionValid()) {
        showToast('Tiện ích vừa được cập nhật, vui lòng F5 lại trang!', 'warning');
        return;
      }
      try {
        const quizAppUrl = chrome.runtime.getURL('quiz_app.html');
        window.open(quizAppUrl, '_blank');
      } catch (e) {}
    });

    syncCurrentCount();
  }

  function updateFloatingWidget(totalCount, pageInfo) {
    const badge = document.getElementById('gfc-badge-count');
    const statTotal = document.getElementById('gfc-stat-total');
    const statPage = document.getElementById('gfc-stat-page');

    if (badge) badge.innerText = String(totalCount);
    if (statTotal) statTotal.innerText = `${totalCount} câu`;
    if (statPage && pageInfo) statPage.innerText = pageInfo;
  }

  function syncCurrentCount() {
    if (!isExtensionValid()) return;
    const formKey = getFormKey();
    safeStorageGet(['forms', 'settings'], (res) => {
      const forms = res.forms || {};
      const form = forms[formKey];
      const count = form ? form.questions.length : 0;
      const pageInfo = document.querySelector('#lpd4pf, .HZh16d')?.innerText || '';
      updateFloatingWidget(count, cleanText(pageInfo));

      if (res.settings && res.settings.showFloatingWidget === false) {
        const container = document.getElementById('gfc-floating-widget-container');
        if (container) container.style.display = 'none';
      }
    });
  }

  // Quick copy in plain text
  function copyCollectedQuestionsQuickly() {
    if (!isExtensionValid()) {
      showToast('Tiện ích vừa được cập nhật, vui lòng F5 lại trang!', 'warning');
      return;
    }
    const formKey = getFormKey();
    safeStorageGet(['forms', 'settings'], (res) => {
      const forms = res.forms || {};
      const form = forms[formKey];
      if (!form || form.questions.length === 0) {
        showToast('Chưa có câu hỏi nào được thu thập. Hãy bấm "Thu thập trang này" trước!', 'warning');
        return;
      }

      let text = `${form.title}\n`;
      text += `Tổng số câu hỏi: ${form.questions.length}\n`;
      text += '--------------------------------------------------\n\n';

      let curSection = '';
      form.questions.forEach((q, idx) => {
        if (q.section && q.section !== curSection) {
          curSection = q.section;
          text += `=== ${curSection} ===\n\n`;
        }

        const pointStr = q.points ? ` [${q.points}]` : '';
        text += `Câu ${idx + 1}: ${q.title}${pointStr}\n`;

        if (q.description) {
          text += `(Mô tả: ${q.description})\n`;
        }

        if (q.image) {
          text += `[Đã nhúng hình ảnh Base64]\n`;
        }

        if (q.options && q.options.length > 0) {
          q.options.forEach((opt, optIdx) => {
            const letter = String.fromCharCode(65 + optIdx);
            const imgNotice = opt.image ? ' [Có ảnh]' : '';
            text += `  ${letter}. ${opt.text}${imgNotice}\n`;
          });
        }

        if (q.correctAnswer) {
          text += `  => Đáp án đúng: ${q.correctAnswer}\n`;
        }
        if (q.explanation) {
          text += `  => Giải thích: ${q.explanation}\n`;
        }
        text += '\n';
      });

      navigator.clipboard.writeText(text).then(() => {
        showToast(`Đã sao chép ${form.questions.length} câu hỏi vào Clipboard!`, 'success');
      }).catch(err => {
        showToast('Lỗi khi sao chép vào bộ nhớ tạm: ' + err.message, 'warning');
      });
    });
  }

  // Click an element with clean mouse and pointer events for Google Forms (mimics human click)
  async function clickButton(btn) {
    if (!btn) return false;

    // Scroll into view
    try {
      btn.scrollIntoView({ behavior: 'instant', block: 'center' });
    } catch (e) {}
    try {
      if (typeof btn.focus === 'function') btn.focus();
    } catch (e) {}

    await new Promise(r => setTimeout(r, 80));

    // Target the inner text span if present, else the button itself
    const target = btn.querySelector('.NPEfkd, .snByac, .l4V7wb') || btn;
    const rect = target.getBoundingClientRect();
    const cx = Math.round(rect.left + Math.max(5, rect.width / 2));
    const cy = Math.round(rect.top + Math.max(5, rect.height / 2));

    const commonOpts = {
      bubbles: true,
      cancelable: true,
      composed: true,
      view: window,
      clientX: cx,
      clientY: cy,
      screenX: cx,
      screenY: cy,
      detail: 1
    };

    // 1. Pointerdown & Mousedown (press)
    try { target.dispatchEvent(new PointerEvent('pointerdown', Object.assign({ button: 0, buttons: 1 }, commonOpts))); } catch (e) {}
    target.dispatchEvent(new MouseEvent('mousedown', Object.assign({ button: 0, buttons: 1 }, commonOpts)));

    // Short natural delay between mouse down and up
    await new Promise(r => setTimeout(r, 60));

    // 2. Pointerup & Mouseup (release)
    try { target.dispatchEvent(new PointerEvent('pointerup', Object.assign({ button: 0, buttons: 0 }, commonOpts))); } catch (e) {}
    target.dispatchEvent(new MouseEvent('mouseup', Object.assign({ button: 0, buttons: 0 }, commonOpts)));

    // 3. Click event
    target.dispatchEvent(new MouseEvent('click', Object.assign({ button: 0, buttons: 0 }, commonOpts)));

    // 4. Native click fallback on the button element if not triggered
    setTimeout(() => {
      try {
        if (typeof btn.click === 'function') {
          btn.click();
        }
      } catch (e) {}
    }, 40);

    return true;
  }

  // Backward compatibility alias
  function dispatchReliableClick(element) {
    clickButton(element);
  }

  // Select a radio button or checkbox in Google Forms reliably
  function selectRadio(radio) {
    if (!radio) return;
    try { radio.scrollIntoView({ behavior: 'instant', block: 'nearest' }); } catch (e) {}
    try { if (typeof radio.focus === 'function') radio.focus(); } catch (e) {}

    if (radio.getAttribute('aria-checked') === 'true') return;

    const rect = radio.getBoundingClientRect();
    const cx = Math.round(rect.left + Math.max(5, rect.width / 2));
    const cy = Math.round(rect.top + Math.max(5, rect.height / 2));

    const opts = { bubbles: true, cancelable: true, composed: true, view: window, clientX: cx, clientY: cy, button: 0, buttons: 0, detail: 1 };
    radio.dispatchEvent(new MouseEvent('mousedown', Object.assign({}, opts, { buttons: 1 })));
    radio.dispatchEvent(new MouseEvent('mouseup', opts));
    radio.dispatchEvent(new MouseEvent('click', opts));
    if (typeof radio.click === 'function') {
      try { radio.click(); } catch (e) {}
    }

    const parentLabel = radio.closest('.docssharedWizToggleLabeledContainer, .nWQGrd, label');
    if (parentLabel && radio.getAttribute('aria-checked') !== 'true') {
      try { parentLabel.click(); } catch (e) {}
    }
  }

  // Set value and trigger all input events for Google Forms controlled text inputs
  function setInputValue(inp, val) {
    if (!inp) return;
    try { inp.focus(); } catch (e) {}

    const proto = inp instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (nativeSetter) {
      nativeSetter.call(inp, val);
    } else {
      inp.value = val;
    }

    try { inp.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true, data: val })); } catch (e) {}
    inp.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
    try { inp.blur(); } catch (e) {}
  }

  // Check if a question item has a mandatory required indicator (*)
  function isItemRequired(item) {
    if (!item) return false;
    // 1. Google Forms red asterisk element (* icon / text)
    const asterisks = item.querySelectorAll('.vVVJbe, .vnumgf');
    for (const ast of asterisks) {
      if (cleanText(ast.innerText) === '*' || ast.getAttribute('aria-hidden') === 'true') {
        return true;
      }
    }
    // 2. aria-required attribute
    if (item.querySelector('[aria-required="true"]') || item.getAttribute('aria-required') === 'true') {
      return true;
    }
    // 3. aria-label with "bắt buộc" or "required"
    if (item.querySelector('[aria-label*="bắt buộc" i], [aria-label*="required" i]')) {
      return true;
    }
    // 4. Heading text containing asterisk
    const h = item.querySelector('[role="heading"], .M7eMe');
    if (h) {
      const hText = cleanText(h.innerText);
      if (/\*\s*$/.test(hText) || /\*\s*\(bắt buộc\)/i.test(hText)) {
        return true;
      }
    }
    // 5. Active validation error alert (Google Forms shows "Đây là một câu hỏi bắt buộc")
    if (item.querySelector('[role="alert"], .RDPZE, .m2Dzb')) {
      return true;
    }
    return false;
  }

  // Check if a question item currently has an answer
  function isItemAnswered(item) {
    if (!item) return false;
    // Radio button checked?
    if (item.querySelector('[role="radio"][aria-checked="true"]')) return true;
    // Checkbox checked?
    if (item.querySelector('[role="checkbox"][aria-checked="true"]')) return true;
    // Text input / textarea non-empty?
    const textInputs = item.querySelectorAll('input[type="text"]:not([type="hidden"]), textarea, input[type="email"], input[type="number"]');
    for (const inp of textInputs) {
      if (inp.value && inp.value.trim().length > 0) return true;
    }
    // Dropdown selected?
    const listbox = item.querySelector('[role="listbox"]');
    if (listbox) {
      const txt = cleanText(listbox.innerText);
      if (txt && txt !== 'Chọn' && txt !== 'Choose') return true;
    }
    return false;
  }

  // Fill temporary dummy value ONLY for questions strictly marked with * (Required)
  // All normal non-required questions will NEVER be touched!
  async function bypassRequiredFieldsOnly() {
    const allowBypass = await new Promise(resolve => {
      safeStorageGet(['settings'], res => resolve(res.settings?.bypassRequiredForAutoCrawl !== false));
    });
    if (!allowBypass) return 0;

    const items = Array.from(document.querySelectorAll('.Qr7Oae, div[role="listitem"], .geS5n'));
    let modifiedCount = 0;

    for (const item of items) {
      // STRICT FILTER: Must be a required question AND currently unanswered!
      if (!isItemRequired(item) || isItemAnswered(item)) {
        continue;
      }

      // 1. Radio group: select only the first option
      const firstRadio = item.querySelector('[role="radio"]');
      if (firstRadio) {
        selectRadio(firstRadio);
        modifiedCount++;
        await new Promise(r => setTimeout(r, 80));
        continue;
      }

      // 2. Checkbox group: select only the first option
      const firstCheckbox = item.querySelector('[role="checkbox"]');
      if (firstCheckbox) {
        selectRadio(firstCheckbox);
        modifiedCount++;
        await new Promise(r => setTimeout(r, 80));
        continue;
      }

      // 3. Text inputs / textareas
      const textInp = item.querySelector('input[type="text"]:not([type="hidden"]), textarea, input[type="email"], input[type="number"]');
      if (textInp && (!textInp.value || textInp.value.trim() === '')) {
        const qTitle = item.querySelector('[role="heading"], .M7eMe')?.innerText || '';
        let dummyVal = '1';
        if (/họ và tên|họ tên|tên/i.test(qTitle)) dummyVal = 'Nguyễn Văn A';
        else if (/email/i.test(qTitle)) dummyVal = 'student@example.com';
        else if (/mã|mssv|sbd|stt/i.test(qTitle)) dummyVal = '12345';
        else if (/lớp|khoa/i.test(qTitle)) dummyVal = 'Lớp 01';

        setInputValue(textInp, dummyVal);
        modifiedCount++;
        await new Promise(r => setTimeout(r, 80));
        continue;
      }

      // 4. Dropdowns
      const listbox = item.querySelector('[role="listbox"]');
      if (listbox) {
        clickButton(listbox);
        await new Promise(r => setTimeout(r, 120));
        const opt = document.querySelector('[role="option"]:not([data-value=""]):not([aria-disabled="true"])');
        if (opt) {
          clickButton(opt);
          modifiedCount++;
          await new Promise(r => setTimeout(r, 100));
        }
      }
    }

    if (modifiedCount > 0) {
      showToast(`⚠️ Đã tự chọn tạm ${modifiedCount} câu hỏi bắt buộc (*) để chuyển trang`, 'info', 2000);
      await new Promise(r => setTimeout(r, 300));
    }

    return modifiedCount;
  }

  // Get current page number from progress text (e.g. "Trang 2 trong tổng số 7")
  function getCurrentPageNumber() {
    const pageText = cleanText(document.querySelector('#lpd4pf, .HZh16d')?.innerText || '');
    if (pageText) {
      const m = pageText.match(/trang\s*(\d+)/i) || pageText.match(/page\s*(\d+)/i) || pageText.match(/(\d+)\s*(?:trong|of|\/)\s*\d+/i);
      if (m) {
        const n = parseInt(m[1], 10);
        if (!isNaN(n) && n > 0) return n;
      }
    }
    return 1;
  }

  // Find the visible "Tiếp" (Next) button strictly without accidentally matching Back/Clear buttons
  function findNextButton() {
    // 1. Look for text span with strictly "Tiếp", "Tiếp tục", or "Next"
    const spans = Array.from(document.querySelectorAll('.NPEfkd, .snByac, .RveJvd, .l4V7wb span, [role="button"] span, button span'));
    for (const s of spans) {
      if (!isElementVisible(s)) continue;
      const txt = cleanText(s.innerText);
      if (/^(tiếp|tiếp tục|next)$/i.test(txt)) {
        const btn = s.closest('[role="button"], button');
        if (btn && isElementVisible(btn)) {
          const btnTxt = cleanText(btn.innerText);
          if (!/quay lại|back|xóa|clear|gửi|submit/i.test(btnTxt)) {
            return btn;
          }
        }
      }
    }

    // 2. Button elements with text "Tiếp" or "Next"
    const allButtons = Array.from(document.querySelectorAll('[role="button"], button'));
    for (const b of allButtons) {
      if (!isElementVisible(b)) continue;
      const txt = cleanText(b.innerText);
      if (/quay lại|back|xóa|clear|gửi|submit/i.test(txt)) continue;
      if (/^(tiếp|tiếp tục|next)$/i.test(txt) || /(^|\s)(tiếp|next)($|\s)/i.test(txt)) {
        return b;
      }
    }

    // 3. Footer area specifically looking for button containing "Tiếp" or "Next"
    const footerBtns = Array.from(document.querySelectorAll('.DE3NNc [role="button"], .lRwqcd [role="button"], .ThHDze [role="button"]'));
    for (const b of footerBtns) {
      if (!isElementVisible(b)) continue;
      const txt = cleanText(b.innerText);
      if (/quay lại|back|xóa|clear|gửi|submit/i.test(txt)) continue;
      if (/tiếp|next/i.test(txt)) {
        return b;
      }
    }

    return null;
  }

  // Find the "Gửi" / "Submit" button
  function findSubmitButton() {
    const candidateSpans = Array.from(document.querySelectorAll('.NPEfkd, .snByac, .RveJvd, .l4V7wb span, [role="button"] span, button span'));
    for (const s of candidateSpans) {
      if (!isElementVisible(s)) continue;
      const txt = cleanText(s.innerText);
      if (/^(gửi|submit|nộp bài)$/i.test(txt)) {
        const btn = s.closest('[role="button"], button');
        if (btn && isElementVisible(btn)) return btn;
      }
    }

    const allButtons = Array.from(document.querySelectorAll('[role="button"][jsname="M2UYVd"], button[jsname="M2UYVd"], [role="button"], button'));
    for (const b of allButtons) {
      if (!isElementVisible(b)) continue;
      const txt = cleanText(b.innerText);
      if (/quay lại|back|xóa|clear|tiếp|next/i.test(txt)) continue;
      if (/^(gửi|submit|nộp bài)$/i.test(txt) || b.getAttribute('jsname') === 'M2UYVd') {
        return b;
      }
    }

    return null;
  }

  // Check if element is visible on page
  function isElementVisible(elem) {
    if (!elem) return false;
    return !!(elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length);
  }

  // Broadcast crawling status to popup and floating widget
  function broadcastCrawlStatus(active) {
    isCrawling = active;
    safeStorageSet({ isCrawling: active });

    const btnAutoCrawl = document.getElementById('gfc-btn-autocrawl');
    const crawlText = document.getElementById('gfc-crawl-text');
    if (btnAutoCrawl) {
      if (active) btnAutoCrawl.classList.add('gfc-crawling');
      else btnAutoCrawl.classList.remove('gfc-crawling');
    }
    if (crawlText) {
      crawlText.innerText = active ? '⏹ Đang thu thập... Bấm dừng' : '⚡ Tự động thu thập tất cả các trang';
    }

    safeSendMessage({
      action: 'CRAWL_STATUS_CHANGED',
      isCrawling: active
    });
  }

  // Trigger Next page transition reliably in Google Forms
  async function triggerNextPage() {
    const nextBtn = findNextButton();
    if (!nextBtn) {
      const submitBtn = findSubmitButton();
      if (submitBtn) {
        showToast('🎉 Đang ở trang cuối cùng của biểu mẫu!', 'success');
      } else {
        showToast('Không tìm thấy nút "Tiếp" trên trang này.', 'warning');
      }
      return false;
    }

    const prevSignature = getPageSignature();
    const prevPageNum = getCurrentPageNumber();
    showToast('Đang chuyển sang trang tiếp theo...', 'info', 1200);

    // 1. Click Next button without touching anything
    await clickButton(nextBtn);

    // 2. Wait and check if page transitioned (up to 3.5 seconds)
    const startTime = Date.now();
    let transitioned = false;
    while (Date.now() - startTime < 3500) {
      await new Promise(r => setTimeout(r, 200));
      const curSig = getPageSignature();
      const curPageNum = getCurrentPageNumber();
      if ((curSig && curSig !== prevSignature) || (curPageNum > prevPageNum)) {
        transitioned = true;
        break;
      }
    }

    // 3. If not transitioned, check if blocked by unanswered required questions (*)
    if (!transitioned) {
      const items = Array.from(document.querySelectorAll('.Qr7Oae, div[role="listitem"], .geS5n'));
      const hasUnansweredReq = items.some(item => isItemRequired(item) && !isItemAnswered(item));

      if (hasUnansweredReq) {
        await bypassRequiredFieldsOnly();
      }

      const retryBtn = findNextButton();
      if (retryBtn) {
        await clickButton(retryBtn);
        const retryStart = Date.now();
        while (Date.now() - retryStart < 4000) {
          await new Promise(r => setTimeout(r, 200));
          const curSig = getPageSignature();
          const curPageNum = getCurrentPageNumber();
          if ((curSig && curSig !== prevSignature) || (curPageNum > prevPageNum)) {
            transitioned = true;
            break;
          }
        }
      }
    }

    if (transitioned) {
      showToast('Đã chuyển sang trang tiếp theo thành công!', 'success');
      return true;
    } else {
      return false;
    }
  }

  // Collect current page, and optionally trigger Next page
  async function collectCurrentPageAndNext(autoNext = true) {
    const pageData = await extractCurrentPageData();
    return new Promise(resolve => {
      saveCollectedData(pageData, async (res) => {
        showToast(`Đã thu thập ${pageData.questions.length} câu hỏi trang này!`, 'success');

        if (autoNext) {
          await new Promise(r => setTimeout(r, 300));
          const transitioned = await triggerNextPage();
          resolve({ status: 'ok', data: pageData, result: res, transitioned });
        } else {
          resolve({ status: 'ok', data: pageData, result: res, transitioned: false });
        }
      });
    });
  }

  // Persistent Auto-Crawl Step (survives full page navigations and reloads)
  async function runCrawlStep(pageNum = 1) {
    if (!isExtensionValid()) return;

    isCrawling = true;
    crawlAbortController = false;
    broadcastCrawlStatus(true);

    const formKey = getFormKey();
    safeStorageSet({
      crawlState: {
        active: true,
        formKey: formKey,
        pageNum: pageNum,
        timestamp: Date.now()
      },
      isCrawling: true
    });

    // 1. Wait for questions on the page to mount and be visible
    await waitForPageReady(3000);

    // 2. Capture current page with Base64 conversion
    // (Notice: questions are collected cleanly in original state before any bypass!)
    const pageData = await extractCurrentPageData();
    await new Promise(resolve => {
      saveCollectedData(pageData, resolve);
    });

    const curPageStr = pageData.pageInfo || `Trang ${pageNum}`;
    showToast(`📄 Đã thu thập ${curPageStr} (${pageData.questions.length} câu)`, 'info', 2000);
    safeSendMessage({ action: 'PAGE_COLLECTED' });

    // Check if crawl was aborted by user
    if (!isCrawling || crawlAbortController || !isExtensionValid()) {
      return;
    }

    // 3. Check for Next button or Submit button
    const nextBtn = findNextButton();

    if (!nextBtn) {
      const submitBtn = findSubmitButton();
      if (submitBtn) {
        showToast('🎉 Đã tới trang cuối cùng! Hoàn tất thu thập toàn bộ biểu mẫu.', 'success', 5000);
      } else {
        showToast('🎉 Đã thu thập xong biểu mẫu (không thấy nút Tiếp).', 'success', 4000);
      }
      safeStorageSet({
        crawlState: { active: false },
        isCrawling: false
      });
      broadcastCrawlStatus(false);
      return;
    }

    const prevSignature = getPageSignature();
    const prevPageNum = getCurrentPageNumber() || pageNum;

    // Update crawlState to expect the NEXT page before clicking Next
    safeStorageSet({
      crawlState: {
        active: true,
        formKey: formKey,
        pageNum: prevPageNum + 1,
        timestamp: Date.now()
      }
    });

    showToast(`Đang chuyển sang Trang tiếp theo...`, 'info', 1500);

    // 4. Click Next button without modifying any normal questions!
    await clickButton(nextBtn);

    // If Google Forms transitions via in-place SPA DOM update:
    const waitStart = Date.now();
    let spaTransitioned = false;
    while (Date.now() - waitStart < 3500) {
      if (!isCrawling || crawlAbortController || !isExtensionValid()) return;
      await new Promise(r => setTimeout(r, 250));
      const curSig = getPageSignature();
      const curPageNum = getCurrentPageNumber();
      if ((curSig && curSig !== prevSignature) || (curPageNum > prevPageNum)) {
        spaTransitioned = true;
        break;
      }
    }

    if (spaTransitioned) {
      await new Promise(r => setTimeout(r, 700));
      const nextPage = getCurrentPageNumber() || (prevPageNum + 1);
      runCrawlStep(nextPage);
      return;
    }

    // 5. If NOT transitioned: check if blocked by unanswered required questions (*)
    const items = Array.from(document.querySelectorAll('.Qr7Oae, div[role="listitem"], .geS5n'));
    const unansweredRequired = items.filter(item => isItemRequired(item) && !isItemAnswered(item));

    if (unansweredRequired.length > 0) {
      showToast(`⚠️ Phát hiện ${unansweredRequired.length} câu hỏi bắt buộc (*), đang chọn tạm để qua trang...`, 'info', 2000);
      await bypassRequiredFieldsOnly();
    }

    // Retry clicking Next button
    const retryBtn = findNextButton();
    if (retryBtn) {
      await new Promise(r => setTimeout(r, 300));
      await clickButton(retryBtn);

      const retryStart = Date.now();
      while (Date.now() - retryStart < 5000) {
        if (!isCrawling || crawlAbortController || !isExtensionValid()) return;
        await new Promise(r => setTimeout(r, 250));
        const curSig = getPageSignature();
        const curPageNum = getCurrentPageNumber();
        if ((curSig && curSig !== prevSignature) || (curPageNum > prevPageNum)) {
          spaTransitioned = true;
          break;
        }
      }
      if (spaTransitioned) {
        await new Promise(r => setTimeout(r, 700));
        const nextPage = getCurrentPageNumber() || (prevPageNum + 1);
        runCrawlStep(nextPage);
        return;
      }
    }

    // If still blocked, scroll to the first unanswered required question if any and prompt user
    const remainingReq = items.find(item => isItemRequired(item) && !isItemAnswered(item));
    if (remainingReq) {
      try { remainingReq.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) {}
    }
    showToast('⚠️ Vui lòng hoàn thành câu hỏi bắt buộc (*) trên form — tiện ích sẽ TỰ ĐỘNG thu thập tiếp ngay khi sang trang!', 'warning', 10000);

    const userWaitStart = Date.now();
    while (Date.now() - userWaitStart < 30000) {
      if (!isCrawling || crawlAbortController || !isExtensionValid()) return;
      await new Promise(r => setTimeout(r, 400));
      const curSig = getPageSignature();
      const curPageNum = getCurrentPageNumber();
      if ((curSig && curSig !== prevSignature) || (curPageNum > prevPageNum)) {
        await new Promise(r => setTimeout(r, 700));
        const nextPage = getCurrentPageNumber() || (prevPageNum + 1);
        runCrawlStep(nextPage);
        return;
      }
    }

    // If timed out after 30s, stop crawl
    stopAutoCrawl();
  }

  // Start Auto-Crawl across multiple pages seamlessly
  function startAutoCrawl() {
    const curPage = getCurrentPageNumber();
    runCrawlStep(curPage);
  }

  // Stop Auto-Crawl
  function stopAutoCrawl() {
    isCrawling = false;
    crawlAbortController = true;
    safeStorageSet({
      crawlState: { active: false },
      isCrawling: false
    });
    broadcastCrawlStatus(false);

    // Final sync
    if (isExtensionValid()) {
      extractCurrentPageData().then(data => saveCollectedData(data));
    }
  }

  // Setup DOM Mutation Observer for automatic accumulation when user navigates manually
  let debounceTimer = null;
  const observer = new MutationObserver(() => {
    if (!isExtensionValid()) {
      try { observer.disconnect(); } catch (e) {}
      return;
    }
    safeStorageGet(['settings'], (res) => {
      const settings = res.settings || {};
      if (settings.autoAccumulate === false) return;

      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(async () => {
        if (!isExtensionValid()) return;
        const pageData = await extractCurrentPageData();
        if (pageData.questions.length > 0) {
          saveCollectedData(pageData);
        }
      }, 800);
    });
  });

  // Start observing question list container
  function startObserver() {
    if (!isExtensionValid()) return;
    const target = document.querySelector('form, .RH5hzf, .o3Dpx') || document.body;
    try {
      observer.observe(target, {
        childList: true,
        subtree: true
      });
    } catch (e) {}
  }

  // Listen for messages from popup or background
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'PING') {
      sendResponse({ status: 'ok', url: window.location.href });
      return true;
    }

    if (request.action === 'COLLECT_CURRENT_PAGE') {
      const autoNext = !!request.autoNext;
      collectCurrentPageAndNext(autoNext).then(resp => {
        sendResponse(resp);
      });
      return true;
    }

    if (request.action === 'COLLECT_AND_NEXT') {
      collectCurrentPageAndNext(true).then(resp => {
        sendResponse(resp);
      });
      return true;
    }

    if (request.action === 'GO_NEXT_PAGE') {
      triggerNextPage(true).then(transitioned => {
        sendResponse({ status: 'ok', transitioned });
      });
      return true;
    }

    if (request.action === 'GET_CURRENT_PAGE_DATA') {
      extractCurrentPageData().then(data => {
        sendResponse({ status: 'ok', data: data });
      });
      return true;
    }

    if (request.action === 'GET_CRAWL_STATUS') {
      sendResponse({ status: 'ok', isCrawling: isCrawling });
      return true;
    }

    if (request.action === 'START_AUTO_CRAWL') {
      startAutoCrawl();
      sendResponse({ status: 'crawling' });
      return true;
    }

    if (request.action === 'STOP_AUTO_CRAWL') {
      stopAutoCrawl();
      sendResponse({ status: 'stopped' });
      return true;
    }

    if (request.action === 'TOGGLE_FLOATING_WIDGET') {
      const container = document.getElementById('gfc-floating-widget-container');
      if (container) {
        container.style.display = request.show ? 'block' : 'none';
      }
      sendResponse({ status: 'ok' });
      return true;
    }
  });

  // Initialize
  function init() {
    if (!isExtensionValid()) return;
    createFloatingWidget();
    startObserver();

    // Check if we are in an active crawl across page navigation!
    safeStorageGet(['crawlState', 'settings'], (res) => {
      const cs = res.crawlState;
      const formKey = getFormKey();

      if (cs && cs.active && cs.formKey === formKey && (Date.now() - cs.timestamp < 15 * 60 * 1000)) {
        // Active multi-page crawl detected across navigation!
        broadcastCrawlStatus(true);
        const curPage = getCurrentPageNumber() || cs.pageNum || 2;
        showToast(`📄 Đang tiếp tục tự động thu thập (Trang ${curPage})...`, 'info', 2000);
        setTimeout(() => {
          runCrawlStep(curPage);
        }, 1200);
      } else {
        // Normal page visit
        broadcastCrawlStatus(false);
        const settings = res.settings || {};
        if (settings.autoAccumulate !== false) {
          setTimeout(async () => {
            if (!isExtensionValid()) return;
            const data = await extractCurrentPageData();
            if (data.questions.length > 0) {
              saveCollectedData(data);
            }
          }, 1000);
        }
      }
    });
  }

  // Wait for DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
