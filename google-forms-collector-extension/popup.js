// Google Forms Question Collector - Popup Script

document.addEventListener('DOMContentLoaded', () => {
  'use strict';

  // State
  let currentFormKey = null;
  let currentFormData = null;
  let activeTabId = null;
  let isGoogleFormTab = false;
  let isCrawling = false;
  let settings = {
    autoAccumulate: true,
    showFloatingWidget: true,
    bypassRequiredForAutoCrawl: true,
    autoNextPage: false,
    exportFormat: 'text',
    optionPrefix: 'letter'
  };

  // DOM Elements
  const formTitleEl = document.getElementById('form-title');
  const statCountEl = document.getElementById('stat-count');
  const statPageEl = document.getElementById('stat-page');
  const tabCountBadge = document.getElementById('tab-count-badge');
  const btnCollect = document.getElementById('btn-collect');
  const btnCollectAndNext = document.getElementById('btn-collect-and-next');
  const btnAutoCrawl = document.getElementById('btn-autocrawl');
  const crawlBtnText = document.getElementById('crawl-btn-text');
  const btnOpenQuizApp = document.getElementById('btn-open-quiz-app');
  const btnGeminiPrompt = document.getElementById('btn-gemini-prompt');
  const btnQuickCopy = document.getElementById('btn-quick-copy');
  const btnClear = document.getElementById('btn-clear');
  const inputSearch = document.getElementById('input-search');
  const selectFilterSection = document.getElementById('select-filter-section');
  const questionsContainer = document.getElementById('questions-container');
  const emptyState = document.getElementById('empty-state');
  const exportPreview = document.getElementById('export-preview');
  const previewInfo = document.getElementById('preview-info');
  const btnCopyExport = document.getElementById('btn-copy-export');
  const btnDownloadExport = document.getElementById('btn-download-export');
  const chkExpPoints = document.getElementById('chk-exp-points');
  const chkExpSections = document.getElementById('chk-exp-sections');
  const chkExpAnswers = document.getElementById('chk-exp-answers');
  const chkExpExcludePersonal = document.getElementById('chk-exp-exclude-personal');
  const setAutoAccumulate = document.getElementById('set-auto-accumulate');
  const setFloatingWidget = document.getElementById('set-floating-widget');
  const setBypassRequired = document.getElementById('set-bypass-required');
  const setAutoNextPage = document.getElementById('set-auto-next-page');
  const setOptionPrefix = document.getElementById('set-option-prefix');
  const savedFormsList = document.getElementById('saved-forms-list');
  const popupToast = document.getElementById('popup-toast');

  // Initialize
  init();

  async function init() {
    setupTabNavigation();
    setupEventListeners();
    setupMessageListeners();
    await loadSettings();
    await checkActiveTab();
    loadCurrentFormData();
    syncCrawlStatus();
  }

  // Update crawl button UI
  function updateCrawlButtonState(crawling) {
    isCrawling = !!crawling;
    if (btnAutoCrawl && crawlBtnText) {
      if (isCrawling) {
        btnAutoCrawl.classList.add('crawling');
        crawlBtnText.innerText = '⏹ Đang thu thập... Bấm dừng';
      } else {
        btnAutoCrawl.classList.remove('crawling');
        crawlBtnText.innerText = '⚡ Tự động thu thập tất cả các trang';
      }
    }
  }

  // Sync crawl status with content script and storage
  function syncCrawlStatus() {
    chrome.storage.local.get(['isCrawling', 'crawlState'], (res) => {
      if (res && (res.isCrawling || res.crawlState?.active)) {
        updateCrawlButtonState(true);
      } else {
        updateCrawlButtonState(false);
      }
    });

    if (activeTabId && isGoogleFormTab) {
      chrome.tabs.sendMessage(activeTabId, { action: 'GET_CRAWL_STATUS' }, (resp) => {
        if (!chrome.runtime.lastError && resp && typeof resp.isCrawling === 'boolean') {
          updateCrawlButtonState(resp.isCrawling);
        }
      });
    }
  }

  // Listen for real-time messages from content script
  function setupMessageListeners() {
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (request.action === 'CRAWL_STATUS_CHANGED') {
        updateCrawlButtonState(request.isCrawling);
        loadCurrentFormData();
      } else if (request.action === 'PAGE_COLLECTED') {
        loadCurrentFormData();
      }
    });
  }

  // Toast notification
  function showToast(msg, duration = 2500) {
    if (!popupToast) return;
    popupToast.innerText = msg;
    popupToast.classList.add('show');
    setTimeout(() => {
      popupToast.classList.remove('show');
    }, duration);
  }

  // Tab navigation
  function setupTabNavigation() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    tabBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        tabBtns.forEach(b => b.classList.remove('active'));
        tabPanes.forEach(p => p.classList.remove('active'));

        btn.classList.add('active');
        document.getElementById(targetTab)?.classList.add('active');

        if (targetTab === 'tab-export') {
          updateExportPreview();
        } else if (targetTab === 'tab-settings') {
          renderSavedForms();
        }
      });
    });
  }

  // Load settings
  function loadSettings() {
    return new Promise(resolve => {
      chrome.storage.local.get(['settings'], (res) => {
        if (res.settings) {
          settings = { ...settings, ...res.settings };
        }
        setAutoAccumulate.checked = settings.autoAccumulate !== false;
        setFloatingWidget.checked = settings.showFloatingWidget !== false;
        setBypassRequired.checked = settings.bypassRequiredForAutoCrawl !== false;
        if (setAutoNextPage) setAutoNextPage.checked = settings.autoNextPage === true;
        setOptionPrefix.value = settings.optionPrefix || 'letter';

        // Select format chip
        const formatRadio = document.querySelector(`input[name="export-format"][value="${settings.exportFormat || 'text'}"]`);
        if (formatRadio) {
          formatRadio.checked = true;
          document.querySelectorAll('.format-chip').forEach(c => c.classList.remove('active'));
          formatRadio.closest('.format-chip')?.classList.add('active');
        }

        resolve();
      });
    });
  }

  // Save settings
  function saveSettings() {
    settings.autoAccumulate = setAutoAccumulate.checked;
    settings.showFloatingWidget = setFloatingWidget.checked;
    settings.bypassRequiredForAutoCrawl = setBypassRequired.checked;
    if (setAutoNextPage) settings.autoNextPage = setAutoNextPage.checked;
    settings.optionPrefix = setOptionPrefix.value;

    const checkedFormat = document.querySelector('input[name="export-format"]:checked');
    if (checkedFormat) {
      settings.exportFormat = checkedFormat.value;
    }

    chrome.storage.local.set({ settings }, () => {
      // Notify active tab about floating widget
      if (activeTabId && isGoogleFormTab) {
        chrome.tabs.sendMessage(activeTabId, {
          action: 'TOGGLE_FLOATING_WIDGET',
          show: settings.showFloatingWidget
        }, () => {
          if (chrome.runtime.lastError) {}
        });
      }
    });
  }

  // Check active tab
  async function checkActiveTab() {
    return new Promise(resolve => {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs && tabs[0]) {
          const tab = tabs[0];
          activeTabId = tab.id;
          if (tab.url && tab.url.includes('docs.google.com/forms/')) {
            isGoogleFormTab = true;
            try {
              const match = tab.url.match(/\/d\/(?:e\/)?([a-zA-Z0-9_-]+)/);
              if (match && match[1]) {
                currentFormKey = 'form_' + match[1];
              }
            } catch (e) {}

            // Send PING to verify content script injection
            chrome.tabs.sendMessage(activeTabId, { action: 'PING' }, (resp) => {
              if (chrome.runtime.lastError || !resp) {
                // Try injecting content script programmatically
                chrome.scripting.executeScript({
                  target: { tabId: activeTabId },
                  files: ['content.js']
                }, () => {
                  chrome.scripting.insertCSS({
                    target: { tabId: activeTabId },
                    files: ['content.css']
                  }, () => resolve());
                });
              } else {
                resolve();
              }
            });
            return;
          }
        }
        resolve();
      });
    });
  }

  // Load current form data from storage
  function loadCurrentFormData() {
    chrome.storage.local.get(['forms', 'activeFormKey'], (res) => {
      const forms = res.forms || {};
      const key = currentFormKey || res.activeFormKey || Object.keys(forms)[0];

      if (key && forms[key]) {
        currentFormKey = key;
        currentFormData = forms[key];
        renderHeader();
        renderQuestions();
        updateExportPreview();
      } else {
        renderHeaderEmpty();
        renderQuestions();
      }
    });
  }

  // Render header
  function renderHeader() {
    if (!currentFormData) {
      renderHeaderEmpty();
      return;
    }

    formTitleEl.innerText = currentFormData.title || 'Biểu mẫu không có tiêu đề';
    formTitleEl.title = currentFormData.title || '';
    const totalQ = currentFormData.questions ? currentFormData.questions.length : 0;
    statCountEl.innerText = `${totalQ} câu`;
    tabCountBadge.innerText = String(totalQ);

    const visitedCount = currentFormData.visitedPages ? currentFormData.visitedPages.length : 0;
    statPageEl.innerText = visitedCount > 0 ? `${visitedCount} trang đã quét` : 'Trang 1';
  }

  function renderHeaderEmpty() {
    formTitleEl.innerText = isGoogleFormTab ? 'Sẵn sàng thu thập câu hỏi' : 'Chưa mở Google Form';
    statCountEl.innerText = '0 câu';
    tabCountBadge.innerText = '0';
    statPageEl.innerText = '-';
  }

  // Render question cards
  function renderQuestions() {
    questionsContainer.innerHTML = '';

    if (!currentFormData || !currentFormData.questions || currentFormData.questions.length === 0) {
      emptyState.style.display = 'flex';
      questionsContainer.style.display = 'none';
      return;
    }

    emptyState.style.display = 'none';
    questionsContainer.style.display = 'flex';

    // Populate section filter options
    const sections = Array.from(new Set(currentFormData.questions.map(q => q.section).filter(Boolean)));
    const currentFilter = selectFilterSection.value;
    selectFilterSection.innerHTML = '<option value="all">Tất cả phần / bài</option>';
    sections.forEach(sec => {
      const opt = document.createElement('option');
      opt.value = sec;
      opt.innerText = sec;
      selectFilterSection.appendChild(opt);
    });
    if (sections.includes(currentFilter)) {
      selectFilterSection.value = currentFilter;
    }

    const keyword = inputSearch.value.trim().toLowerCase();
    const filterSection = selectFilterSection.value;

    let filteredQuestions = currentFormData.questions.filter(q => {
      // Section filter
      if (filterSection !== 'all' && q.section !== filterSection) return false;

      // Keyword filter
      if (keyword) {
        const titleMatch = q.title && q.title.toLowerCase().includes(keyword);
        const descMatch = q.description && q.description.toLowerCase().includes(keyword);
        const optMatch = q.options && q.options.some(o => o.text && o.text.toLowerCase().includes(keyword));
        return titleMatch || descMatch || optMatch;
      }
      return true;
    });

    if (filteredQuestions.length === 0) {
      questionsContainer.innerHTML = `
        <div style="text-align: center; padding: 40px 10px; color: var(--text-secondary);">
          <p>Không tìm thấy câu hỏi phù hợp với từ khóa "${keyword}".</p>
        </div>
      `;
      return;
    }

    let lastSection = null;

    filteredQuestions.forEach((q, idx) => {
      // If section changes, render section divider
      if (q.section && q.section !== lastSection) {
        lastSection = q.section;
        const secDiv = document.createElement('div');
        secDiv.className = 'section-divider';
        secDiv.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M17 3H7c-1.1 0-1.99.9-1.99 2L5 21l7-3 7 3V5c0-1.1-.9-2-2-2z"/></svg>
          <span>${escapeHtml(q.section)}</span>
        `;
        questionsContainer.appendChild(secDiv);
      }

      const card = document.createElement('div');
      card.className = 'q-card';

      // Type label in Vietnamese
      const typeMap = {
        multiple_choice: 'Trắc nghiệm 1 đáp án',
        checkbox: 'Hộp kiểm (Nhiều đáp án)',
        short_text: 'Tự luận ngắn',
        paragraph: 'Tự luận dài',
        dropdown: 'Trình đơn thả xuống',
        linear_scale: 'Thang đo tuyến tính',
        grid: 'Ma trận lưới'
      };
      const typeLabel = typeMap[q.type] || 'Trắc nghiệm';

      // Option prefix
      const prefixType = settings.optionPrefix || 'letter';

      let optionsHtml = '';
      if (q.options && q.options.length > 0) {
        optionsHtml = '<div class="q-options">';
        q.options.forEach((opt, optIdx) => {
          let prefix = '';
          if (prefixType === 'letter') {
            prefix = String.fromCharCode(65 + optIdx) + '.';
          } else if (prefixType === 'number') {
            prefix = (optIdx + 1) + '.';
          } else {
            prefix = '•';
          }

          const isUserAns = q.userAnswer && q.userAnswer.includes(opt.text);
          const isCorrect = q.correctAnswer && (q.correctAnswer === opt.text || q.correctAnswer.includes(opt.text));
          const highlightClass = isCorrect ? 'correct' : '';

          optionsHtml += `
            <div class="q-option-item ${highlightClass}">
              <span class="q-option-prefix">${prefix}</span>
              <span class="q-option-text">${escapeHtml(opt.text)}</span>
              ${isUserAns ? '<span title="Đã chọn" style="color: #673ab7; margin-left: 4px;">✓</span>' : ''}
              ${opt.image ? `<a href="${opt.image}" target="_blank" style="margin-left: 6px; display: inline-flex; align-items: center;" title="Bấm để xem ảnh đáp án phóng to"><img src="${opt.image}" style="max-height: 24px; border-radius: 3px; border: 1px solid var(--border-color); vertical-align: middle;" alt="Ảnh" /></a>` : ''}
            </div>
          `;
        });
        optionsHtml += '</div>';
      }

      card.innerHTML = `
        <div class="q-card-header">
          <div class="q-card-meta">
            <span class="q-num">Câu ${idx + 1}</span>
            <span class="q-badge q-badge-type">${typeLabel}</span>
            ${q.points ? `<span class="q-badge q-badge-points">${escapeHtml(q.points)}</span>` : ''}
            ${q.isRequired ? `<span class="q-badge q-badge-req" title="Bắt buộc">* Bắt buộc</span>` : ''}
            ${q.isPersonalInfo ? `<span class="q-badge" style="background: #f1f3f4; color: #5f6368;" title="Trường thông tin hành chính">Thông tin</span>` : ''}
          </div>
          <div class="q-card-actions">
            <button class="btn-icon-tiny btn-copy-card" title="Sao chép câu này" data-hash="${q.hash || q.title}">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
            </button>
            <button class="btn-icon-tiny btn-delete" title="Xóa câu này" data-hash="${q.hash || q.title}">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
            </button>
          </div>
        </div>

        <div class="q-title">${escapeHtml(q.title)}</div>
        ${q.description ? `<div class="q-desc">${escapeHtml(q.description)}</div>` : ''}
        ${q.image ? `<img src="${q.image}" class="q-image-preview" alt="Ảnh câu hỏi" />` : ''}
        ${optionsHtml}
        ${q.correctAnswer ? `<div class="q-correct-box">✓ Đáp án đúng: ${escapeHtml(q.correctAnswer)}</div>` : ''}
        ${q.feedback ? `<div class="q-feedback-box">💡 Giải thích: ${escapeHtml(q.feedback)}</div>` : ''}
      `;

      questionsContainer.appendChild(card);
    });

    // Event listeners for card buttons
    questionsContainer.querySelectorAll('.btn-copy-card').forEach(btn => {
      btn.addEventListener('click', () => {
        const hash = btn.getAttribute('data-hash');
        const q = currentFormData.questions.find(item => (item.hash || item.title) === hash);
        if (q) {
          copySingleQuestion(q);
        }
      });
    });

    questionsContainer.querySelectorAll('.btn-delete').forEach(btn => {
      btn.addEventListener('click', () => {
        const hash = btn.getAttribute('data-hash');
        deleteSingleQuestion(hash);
      });
    });
  }

  // Delete single question
  function deleteSingleQuestion(hash) {
    if (!currentFormData || !currentFormData.questions) return;
    currentFormData.questions = currentFormData.questions.filter(q => (q.hash || q.title) !== hash);

    saveCurrentFormData(() => {
      renderHeader();
      renderQuestions();
      updateExportPreview();
      showToast('Đã xóa câu hỏi!');
    });
  }

  // Copy single question
  function copySingleQuestion(q) {
    let text = `${q.title}\n`;
    if (q.description) text += `(${q.description})\n`;
    if (q.options && q.options.length > 0) {
      q.options.forEach((opt, idx) => {
        text += `  ${String.fromCharCode(65 + idx)}. ${opt.text}\n`;
      });
    }
    if (q.correctAnswer) text += `=> Đáp án: ${q.correctAnswer}\n`;

    navigator.clipboard.writeText(text).then(() => {
      showToast('Đã sao chép câu hỏi vào bộ nhớ tạm!');
    });
  }

  // Generate & copy ready-to-paste Gemini Chat prompt
  function copyGeminiPromptFromPopup() {
    if (!currentFormData || !currentFormData.questions || currentFormData.questions.length === 0) {
      showToast('Chưa có câu hỏi nào để gửi Gemini!');
      return;
    }

    const excPersonal = chkExpExcludePersonal ? chkExpExcludePersonal.checked : true;
    let questions = currentFormData.questions;
    if (excPersonal) {
      questions = questions.filter(q => !q.isPersonalInfo);
    }

    if (questions.length === 0) {
      showToast('Không có câu hỏi nào (đã lọc hết câu hỏi thông tin cá nhân).');
      return;
    }

    // Exclude heavy base64 strings to keep prompt token size small
    const promptQuestions = questions.map((q, idx) => {
      return {
        id: q.id || String(idx + 1),
        section: q.section || '',
        title: q.title || '[Câu hỏi hình ảnh]',
        hasImage: !!q.image,
        options: q.options ? q.options.map(o => (typeof o === 'string' ? o : o.text)) : [],
        correctAnswer: q.correctAnswer || '',
        explanation: q.feedback || q.explanation || ''
      };
    });

    const promptText = `Bạn là một chuyên gia giáo dục và khảo thí. Tôi có bộ câu hỏi trắc nghiệm dưới đây (được trích xuất từ đề thi Google Forms).

NHIỆM VỤ CỦA BẠN:
1. Giải từng câu hỏi và điền đáp án chính xác vào trường "correctAnswer".
   LƯU Ý: Nội dung "correctAnswer" phải trùng khớp chính xác với 1 trong các giá trị trong mảng "options".
2. Viết lời giải thích ngắn gọn, súc tích và dễ hiểu vào trường "explanation" (nêu rõ lý do vì sao đáp án đó đúng).
3. Giữ nguyên toàn bộ cấu trúc và thứ tự câu hỏi trong file JSON.
4. Trả về DUY NHẤT một khối mã JSON hợp lệ (bọc trong \`\`\`json ... \`\`\`) để tôi có thể copy và import lại vào trang web ôn tập.

Dưới đây là dữ liệu JSON:
\`\`\`json
${JSON.stringify({
  title: currentFormData.title || 'Đề thi trắc nghiệm',
  totalQuestions: questions.length,
  questions: promptQuestions
}, null, 2)}
\`\`\`
`;

    navigator.clipboard.writeText(promptText).then(() => {
      showToast('Đã copy Prompt + Toàn bộ câu hỏi! Hãy dán vào Gemini chat.');
    }).catch(err => {
      showToast('Lỗi sao chép: ' + err.message);
    });
  }

  // Save current form data back to storage
  function saveCurrentFormData(callback) {
    chrome.storage.local.get(['forms'], (res) => {
      const forms = res.forms || {};
      if (currentFormKey) {
        forms[currentFormKey] = currentFormData;
        chrome.storage.local.set({ forms }, () => {
          chrome.runtime.sendMessage({
            action: 'UPDATE_BADGE',
            count: currentFormData.questions.length
          });
          if (callback) callback();
        });
      }
    });
  }

  // Generate formatted export content
  function generateExportContent(format) {
    if (!currentFormData || !currentFormData.questions || currentFormData.questions.length === 0) {
      return 'Chưa có câu hỏi nào để xuất.';
    }

    const incPoints = chkExpPoints.checked;
    const incSections = chkExpSections.checked;
    const incAnswers = chkExpAnswers.checked;
    const excPersonal = chkExpExcludePersonal ? chkExpExcludePersonal.checked : true;
    const prefixType = settings.optionPrefix || 'letter';

    let questions = currentFormData.questions;
    if (excPersonal) {
      questions = questions.filter(q => !q.isPersonalInfo);
    }

    if (questions.length === 0) {
      return 'Không có câu hỏi nào (tất cả là câu hỏi thông tin cá nhân đã được lọc).';
    }

    const title = currentFormData.title || 'Đề thi';

    // 1. TEXT FORMAT
    if (format === 'text') {
      let out = `ĐỀ THI: ${title}\n`;
      if (currentFormData.description) out += `Mô tả: ${currentFormData.description}\n`;
      out += `Tổng số câu hỏi: ${questions.length}\n`;
      out += '==================================================\n\n';

      let lastSec = null;
      questions.forEach((q, idx) => {
        if (incSections && q.section && q.section !== lastSec) {
          lastSec = q.section;
          out += `\n--- PHẦN: ${lastSec} ---\n\n`;
        }

        const pointStr = incPoints && q.points ? ` [${q.points}]` : '';
        out += `Câu ${idx + 1}: ${q.title}${pointStr}\n`;
        if (q.description) out += `(Ghi chú: ${q.description})\n`;

        if (q.options && q.options.length > 0) {
          q.options.forEach((opt, optIdx) => {
            let pref = '';
            if (prefixType === 'letter') pref = String.fromCharCode(65 + optIdx) + '.';
            else if (prefixType === 'number') pref = (optIdx + 1) + '.';
            else pref = '•';
            out += `  ${pref} ${opt.text}\n`;
          });
        }

        if (incAnswers && q.correctAnswer) {
          out += `  => Đáp án đúng: ${q.correctAnswer}\n`;
        }
        out += '\n';
      });
      return out;
    }

    // 2. MARKDOWN FORMAT
    if (format === 'markdown') {
      let out = `# ${title}\n\n`;
      if (currentFormData.description) out += `> ${currentFormData.description}\n\n`;
      out += `**Tổng số câu hỏi:** ${questions.length}\n\n---\n\n`;

      let lastSec = null;
      questions.forEach((q, idx) => {
        if (incSections && q.section && q.section !== lastSec) {
          lastSec = q.section;
          out += `## ${lastSec}\n\n`;
        }

        const pointStr = incPoints && q.points ? ` *(${q.points})*` : '';
        out += `### Câu ${idx + 1}: ${q.title}${pointStr}\n`;
        if (q.description) out += `*${q.description}*\n\n`;
        if (q.image) out += `![Hình ảnh câu hỏi](${q.image})\n\n`;

        if (q.options && q.options.length > 0) {
          q.options.forEach((opt, optIdx) => {
            const letter = String.fromCharCode(65 + optIdx);
            const isCorrect = incAnswers && q.correctAnswer && q.correctAnswer.includes(opt.text);
            const checkedBox = isCorrect ? '[x]' : '[ ]';
            out += `- ${checkedBox} **${letter}.** ${opt.text}\n`;
          });
          out += '\n';
        }

        if (incAnswers && q.correctAnswer) {
          out += `> **Đáp án đúng:** ${q.correctAnswer}\n\n`;
        }
      });
      return out;
    }

    // 3. CSV / EXCEL FORMAT
    if (format === 'csv') {
      // UTF-8 BOM for Excel
      let csv = '\uFEFF';
      // Find max options count
      let maxOpts = 4;
      questions.forEach(q => {
        if (q.options && q.options.length > maxOpts) maxOpts = q.options.length;
      });

      // Headers
      const headers = ['STT', 'Phần / Chủ đề', 'Nội dung câu hỏi', 'Điểm', 'Loại'];
      for (let i = 0; i < maxOpts; i++) {
        headers.push(`Đáp án ${String.fromCharCode(65 + i)}`);
      }
      headers.push('Đáp án đúng', 'Mô tả / Ghi chú');
      csv += headers.map(escapeCsv).join(',') + '\n';

      questions.forEach((q, idx) => {
        const row = [
          idx + 1,
          q.section || '',
          q.title || '',
          q.points || '',
          q.type || ''
        ];

        for (let i = 0; i < maxOpts; i++) {
          row.push((q.options && q.options[i]) ? q.options[i].text : '');
        }

        row.push(q.correctAnswer || '', q.description || '');
        csv += row.map(escapeCsv).join(',') + '\n';
      });
      return csv;
    }

    // 4. JSON FORMAT
    if (format === 'json') {
      return JSON.stringify({
        title: currentFormData.title,
        description: currentFormData.description,
        url: currentFormData.url,
        totalQuestions: questions.length,
        exportedAt: new Date().toISOString(),
        questions: questions
      }, null, 2);
    }

    // 5. AIKEN FORMAT (Moodle LMS)
    if (format === 'aiken') {
      let out = '';
      questions.forEach((q) => {
        if (!q.options || q.options.length === 0) return;

        out += `${q.title}\n`;
        let correctLetter = '';

        q.options.forEach((opt, optIdx) => {
          const letter = String.fromCharCode(65 + optIdx);
          out += `${letter}. ${opt.text}\n`;
          if (q.correctAnswer && (q.correctAnswer === opt.text || q.correctAnswer.includes(opt.text))) {
            correctLetter = letter;
          }
        });

        if (correctLetter) {
          out += `ANSWER: ${correctLetter}\n\n`;
        } else {
          out += `ANSWER: A\n\n`; // default fallback
        }
      });
      return out;
    }

    // 6. HTML PRINT FORMAT
    if (format === 'html') {
      let html = `<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>${escapeHtml(title)}</title>
  <style>
    body { font-family: "Times New Roman", Times, serif; font-size: 14pt; line-height: 1.4; margin: 30px; }
    h1 { text-align: center; font-size: 18pt; text-transform: uppercase; margin-bottom: 4px; }
    .subtitle { text-align: center; font-style: italic; margin-bottom: 24px; }
    .section-title { font-weight: bold; font-size: 15pt; margin-top: 24px; text-decoration: underline; }
    .question-block { margin-bottom: 18px; page-break-inside: avoid; }
    .question-title { font-weight: bold; }
    .points { font-style: italic; font-weight: normal; }
    .options-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; margin: 8px 0 8px 24px; }
    .option-item { }
    .correct-ans { font-weight: bold; color: #2e7d32; margin-left: 24px; }
    @media print {
      body { margin: 15mm; }
      .no-print { display: none; }
    }
  </style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  <div class="subtitle">Tổng số: ${questions.length} câu hỏi</div>
  <hr/>
`;
      let lastSec = null;
      questions.forEach((q, idx) => {
        if (incSections && q.section && q.section !== lastSec) {
          lastSec = q.section;
          html += `<div class="section-title">${escapeHtml(lastSec)}</div>\n`;
        }

        const pointStr = incPoints && q.points ? ` <span class="points">(${escapeHtml(q.points)})</span>` : '';
        html += `<div class="question-block">\n`;
        html += `  <div class="question-title">Câu ${idx + 1}: ${escapeHtml(q.title)}${pointStr}</div>\n`;

        if (q.options && q.options.length > 0) {
          html += `  <div class="options-grid">\n`;
          q.options.forEach((opt, optIdx) => {
            const letter = String.fromCharCode(65 + optIdx);
            html += `    <div class="option-item"><strong>${letter}.</strong> ${escapeHtml(opt.text)}</div>\n`;
          });
          html += `  </div>\n`;
        }

        if (incAnswers && q.correctAnswer) {
          html += `  <div class="correct-ans">Đáp án: ${escapeHtml(q.correctAnswer)}</div>\n`;
        }

        html += `</div>\n`;
      });

      html += `</body></html>`;
      return html;
    }

    return '';
  }

  function escapeCsv(val) {
    if (val === null || val === undefined) return '""';
    const str = String(val).replace(/"/g, '""');
    return `"${str}"`;
  }

  function escapeHtml(text) {
    if (!text) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Update export preview textarea
  function updateExportPreview() {
    const activeFormat = document.querySelector('input[name="export-format"]:checked')?.value || 'text';
    const content = generateExportContent(activeFormat);
    exportPreview.value = content;

    const lines = content.split('\n').length;
    const chars = content.length;
    previewInfo.innerText = `${lines} dòng | ${chars} ký tự`;
  }

  // Setup event listeners
  function setupEventListeners() {
    // Collect Current Page Button (if present)
    if (btnCollect) {
      btnCollect.addEventListener('click', () => {
        if (!isGoogleFormTab) {
          showToast('Hãy mở một trang Google Form trước!');
          return;
        }

        btnCollect.disabled = true;
        btnCollect.innerHTML = `<span>Đang quét...</span>`;

        const autoNext = settings.autoNextPage === true;

        chrome.tabs.sendMessage(activeTabId, { action: 'COLLECT_CURRENT_PAGE', autoNext }, (response) => {
          btnCollect.disabled = false;
          btnCollect.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
            <span>Thu thập</span>
          `;

          if (chrome.runtime.lastError || !response) {
            showToast('Không thể kết nối với trang Google Form. Vui lòng tải lại (F5) trang form!');
            return;
          }

          loadCurrentFormData();
          if (autoNext && response.transitioned) {
            showToast(`Đã thu thập ${response.data.questions.length} câu và chuyển sang trang kế tiếp!`);
          } else {
            showToast(`Đã thu thập ${response.data.questions.length} câu hỏi! (Mới thêm: ${response.result.newAdded})`);
          }
        });
      });
    }

    // Collect and Next Page Button (if present)
    if (btnCollectAndNext) {
      btnCollectAndNext.addEventListener('click', () => {
        if (!isGoogleFormTab) {
          showToast('Hãy mở một trang Google Form trước!');
          return;
        }

        btnCollectAndNext.disabled = true;
        btnCollectAndNext.innerHTML = `<span>Đang chuyển...</span>`;

        chrome.tabs.sendMessage(activeTabId, { action: 'COLLECT_AND_NEXT' }, (response) => {
          btnCollectAndNext.disabled = false;
          btnCollectAndNext.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z"/></svg>
            <span>Thu thập & Sang trang</span>
          `;

          if (chrome.runtime.lastError || !response) {
            showToast('Không thể kết nối với trang Google Form. Vui lòng tải lại (F5) trang form!');
            return;
          }

          loadCurrentFormData();
          if (response.transitioned) {
            showToast(`Đã thu thập ${response.data.questions.length} câu và chuyển sang trang tiếp theo!`);
          } else {
            showToast(`Đã thu thập ${response.data.questions.length} câu! (Hãy bấm Tiếp trên form nếu bị chặn)`);
          }
        });
      });
    }

    // Auto Crawl Button
    btnAutoCrawl.addEventListener('click', () => {
      if (!isGoogleFormTab) {
        showToast('Hãy mở một trang Google Form trước!');
        return;
      }

      if (isCrawling) {
        // Stop
        chrome.tabs.sendMessage(activeTabId, { action: 'STOP_AUTO_CRAWL' }, () => {
          updateCrawlButtonState(false);
          loadCurrentFormData();
          showToast('Đã dừng duyệt tự động!');
        });
      } else {
        // Start
        chrome.tabs.sendMessage(activeTabId, { action: 'START_AUTO_CRAWL' }, (resp) => {
          if (chrome.runtime.lastError || !resp || resp.status !== 'crawling') {
            updateCrawlButtonState(false);
            showToast('⚠️ Chưa kết nối được trang. Hãy F5 lại Google Form!');
            return;
          }
          updateCrawlButtonState(true);
          showToast('Bắt đầu duyệt tự động qua các trang...');
        });
      }
    });

    // Quick Copy
    btnQuickCopy.addEventListener('click', () => {
      const content = generateExportContent('text');
      navigator.clipboard.writeText(content).then(() => {
        showToast('Đã sao chép toàn bộ câu hỏi vào Clipboard!');
      });
    });

    // Open Web Quiz App
    if (btnOpenQuizApp) {
      btnOpenQuizApp.addEventListener('click', () => {
        chrome.tabs.create({ url: chrome.runtime.getURL('quiz_app.html') });
      });
    }

    // Copy Ready-to-paste Gemini Prompt
    if (btnGeminiPrompt) {
      btnGeminiPrompt.addEventListener('click', () => {
        copyGeminiPromptFromPopup();
      });
    }

    // Clear All
    btnClear.addEventListener('click', () => {
      if (!currentFormData || !currentFormData.questions || currentFormData.questions.length === 0) {
        showToast('Chưa có câu hỏi nào để xóa.');
        return;
      }

      if (confirm(`Bạn có chắc muốn xóa tất cả ${currentFormData.questions.length} câu hỏi đã thu thập?`)) {
        currentFormData.questions = [];
        currentFormData.visitedPages = [];
        saveCurrentFormData(() => {
          renderHeader();
          renderQuestions();
          updateExportPreview();
          showToast('Đã xóa toàn bộ câu hỏi.');
        });
      }
    });

    // Search input
    inputSearch.addEventListener('input', () => {
      renderQuestions();
    });

    // Filter section
    selectFilterSection.addEventListener('change', () => {
      renderQuestions();
    });

    // Format Chips
    document.querySelectorAll('.format-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        document.querySelectorAll('.format-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        saveSettings();
        updateExportPreview();
      });
    });

    // Export Checkboxes
    [chkExpPoints, chkExpSections, chkExpAnswers, chkExpExcludePersonal].forEach(chk => {
      if (chk) {
        chk.addEventListener('change', () => {
          updateExportPreview();
        });
      }
    });

    // Copy Export Content
    btnCopyExport.addEventListener('click', () => {
      const content = exportPreview.value;
      if (!content || content.startsWith('Chưa có câu hỏi')) {
        showToast('Không có nội dung để sao chép.');
        return;
      }
      navigator.clipboard.writeText(content).then(() => {
        showToast('Đã sao chép nội dung xuất vào Clipboard!');
      });
    });

    // Download Export Content
    btnDownloadExport.addEventListener('click', () => {
      const activeFormat = document.querySelector('input[name="export-format"]:checked')?.value || 'text';
      const content = exportPreview.value;

      if (!content || content.startsWith('Chưa có câu hỏi')) {
        showToast('Không có nội dung để tải về.');
        return;
      }

      const extMap = {
        text: 'txt',
        markdown: 'md',
        csv: 'csv',
        json: 'json',
        aiken: 'txt',
        html: 'html'
      };
      const ext = extMap[activeFormat] || 'txt';
      const safeTitle = (currentFormData?.title || 'google_form_quiz')
        .toLowerCase()
        .replace(/[^a-z0-9àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ\s_-]/g, '')
        .replace(/\s+/g, '_')
        .substring(0, 50);

      const filename = `${safeTitle}_cau_hoi.${ext}`;
      const mimeMap = {
        text: 'text/plain;charset=utf-8',
        markdown: 'text/markdown;charset=utf-8',
        csv: 'text/csv;charset=utf-8',
        json: 'application/json;charset=utf-8',
        aiken: 'text/plain;charset=utf-8',
        html: 'text/html;charset=utf-8'
      };
      const mime = mimeMap[activeFormat] || 'text/plain;charset=utf-8';

      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);

      chrome.downloads.download({
        url: url,
        filename: filename,
        saveAs: true
      }, () => {
        showToast(`Đang tải file ${filename}...`);
      });
    });

    // Settings switches
    setAutoAccumulate.addEventListener('change', saveSettings);
    setFloatingWidget.addEventListener('change', saveSettings);
    setBypassRequired.addEventListener('change', saveSettings);
    if (setAutoNextPage) setAutoNextPage.addEventListener('change', saveSettings);
    setOptionPrefix.addEventListener('change', () => {
      saveSettings();
      renderQuestions();
      updateExportPreview();
    });
  }

  // Render list of saved forms in Settings
  function renderSavedForms() {
    chrome.storage.local.get(['forms'], (res) => {
      const forms = res.forms || {};
      savedFormsList.innerHTML = '';

      const keys = Object.keys(forms);
      if (keys.length === 0) {
        savedFormsList.innerHTML = '<div style="font-size: 11px; color: var(--text-secondary);">Chưa lưu biểu mẫu nào.</div>';
        return;
      }

      keys.forEach(k => {
        const f = forms[k];
        const item = document.createElement('div');
        item.className = 'saved-form-item';
        item.innerHTML = `
          <div>
            <div class="saved-form-name">${escapeHtml(f.title || k)}</div>
            <div class="saved-form-count">${f.questions ? f.questions.length : 0} câu hỏi | ${new Date(f.lastUpdated || f.createdAt).toLocaleDateString('vi-VN')}</div>
          </div>
          <div style="display: flex; gap: 4px;">
            <button class="btn-icon-tiny btn-switch-form" data-key="${k}" title="Xem biểu mẫu này">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
            </button>
            <button class="btn-icon-tiny btn-delete btn-del-form" data-key="${k}" title="Xóa biểu mẫu">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
            </button>
          </div>
        `;
        savedFormsList.appendChild(item);
      });

      // Handlers
      savedFormsList.querySelectorAll('.btn-switch-form').forEach(b => {
        b.addEventListener('click', () => {
          const k = b.getAttribute('data-key');
          currentFormKey = k;
          currentFormData = forms[k];
          chrome.storage.local.set({ activeFormKey: k }, () => {
            renderHeader();
            renderQuestions();
            updateExportPreview();
            // Switch to questions tab
            document.querySelector('.tab-btn[data-tab="tab-questions"]')?.click();
            showToast('Đã chuyển sang biểu mẫu: ' + (currentFormData.title || ''));
          });
        });
      });

      savedFormsList.querySelectorAll('.btn-del-form').forEach(b => {
        b.addEventListener('click', () => {
          const k = b.getAttribute('data-key');
          if (confirm('Bạn có chắc muốn xóa biểu mẫu này khỏi bộ nhớ?')) {
            delete forms[k];
            chrome.storage.local.set({ forms }, () => {
              if (currentFormKey === k) {
                currentFormKey = null;
                currentFormData = null;
                renderHeader();
                renderQuestions();
                updateExportPreview();
              }
              renderSavedForms();
              showToast('Đã xóa biểu mẫu đã lưu.');
            });
          }
        });
      });
    });
  }

});
