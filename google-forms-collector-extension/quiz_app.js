(function () {
      'use strict';

      // Application State
      let examData = {
        title: 'Đề thi trắc nghiệm',
        description: '',
        questions: []
      };
      let currentIndex = 0;
      let userAnswers = {}; // { questionId: selectedOptionText }
      let starredQuestions = new Set();
      let currentMode = 'practice'; // 'practice' | 'exam' | 'flashcard' | 'sheet'
      let activeSection = 'all';

      // DOM Elements
      const topFormTitle = document.getElementById('top-form-title');
      const questionCard = document.getElementById('question-card');
      const sheetCard = document.getElementById('sheet-card');
      const sheetListContainer = document.getElementById('sheet-list-container');
      const qIndexBadge = document.getElementById('q-index-badge');
      const qSectionBadge = document.getElementById('q-section-badge');
      const qPointsBadge = document.getElementById('q-points-badge');
      const btnStarQuestion = document.getElementById('btn-star-question');
      const qTitleText = document.getElementById('q-title-text');
      const qImageContainer = document.getElementById('q-image-container');
      const qImageEl = document.getElementById('q-image-el');
      const optionsContainer = document.getElementById('options-container');
      const explanationBox = document.getElementById('explanation-box');
      const explanationText = document.getElementById('explanation-text');
      const btnPrevQ = document.getElementById('btn-prev-q');
      const btnNextQ = document.getElementById('btn-next-q');
      const btnShowAnswer = document.getElementById('btn-show-answer');
      const paletteGrid = document.getElementById('palette-grid');
      const paletteProgressText = document.getElementById('palette-progress-text');
      const statCorrectCount = document.getElementById('stat-correct-count');
      const statWrongCount = document.getElementById('stat-wrong-count');
      const filterSectionSelect = document.getElementById('filter-section-select');
      const btnShuffle = document.getElementById('btn-shuffle');
      const btnResetProgress = document.getElementById('btn-reset-progress');
      const btnCopyGeminiPrompt = document.getElementById('btn-copy-gemini-prompt');
      const btnImportModal = document.getElementById('btn-import-modal');
      const importModal = document.getElementById('import-modal');
      const btnCloseImport = document.getElementById('btn-close-import');
      const btnCancelImport = document.getElementById('btn-cancel-import');
      const btnConfirmImport = document.getElementById('btn-confirm-import');
      const importJsonInput = document.getElementById('import-json-input');
      const fileInputJson = document.getElementById('file-input-json');
      const folderInputJson = document.getElementById('folder-input-json');
      const btnBrowseFolder = document.getElementById('btn-browse-folder');
      const btnBrowseFiles = document.getElementById('btn-browse-files');
      const importDropZone = document.getElementById('import-drop-zone');
      const scannedFilesContainer = document.getElementById('scanned-files-container');
      const scannedSummaryText = document.getElementById('scanned-summary-text');
      const scannedFilesList = document.getElementById('scanned-files-list');
      const btnClearScanned = document.getElementById('btn-clear-scanned');
      const examSetContainer = document.getElementById('exam-set-container');
      const selectExamSet = document.getElementById('select-exam-set');
      const btnExportJson = document.getElementById('btn-export-json');
      const btnToggleTheme = document.getElementById('btn-toggle-theme');
      const appToast = document.getElementById('app-toast');

      let examSets = []; // [{ id, name, title, description, questions }]
      let pendingScannedFiles = []; // [{ file, name, path, title, description, questions }]

      // Initialize
      initApp();

      async function initApp() {
        setupEventListeners();
        loadTheme();
        await tryLoadFromExtensionStorage();
        if (examData.questions.length === 0) {
          loadFromLocalStorage();
        }
        renderExamSetSelector();
        renderExam();
      }

      function showToast(msg, duration = 2500) {
        appToast.innerText = msg;
        appToast.style.display = 'block';
        setTimeout(() => { appToast.style.display = 'none'; }, duration);
      }

      // Check if running inside Chrome Extension and load active form
      function tryLoadFromExtensionStorage() {
        return new Promise(resolve => {
          if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
            chrome.storage.local.get(['forms', 'activeFormKey'], (res) => {
              const forms = res.forms || {};
              const key = res.activeFormKey || Object.keys(forms)[0];
              if (key && forms[key] && forms[key].questions && forms[key].questions.length > 0) {
                examData = forms[key];
                showToast(`Đã tự động tải đề thi "${examData.title}" từ tiện ích!`);
              }
              resolve();
            });
          } else {
            resolve();
          }
        });
      }

      function loadFromLocalStorage() {
        const saved = localStorage.getItem('gfc_quiz_data');
        if (saved) {
          try {
            examData = JSON.parse(saved);
          } catch (e) {}
        }
        const savedSets = localStorage.getItem('gfc_exam_sets');
        if (savedSets) {
          try {
            examSets = JSON.parse(savedSets);
          } catch (e) {}
        }
      }

      function renderExamSetSelector() {
        if (!examSetContainer || !selectExamSet) return;
        if (!examSets || examSets.length <= 1) {
          examSetContainer.style.display = 'none';
          return;
        }

        examSetContainer.style.display = 'flex';
        let optionsHtml = '';

        const mergedCount = examSets.reduce((acc, s) => acc + (s.questions ? s.questions.length : 0), 0);
        const isMergedSelected = (!examData.title || examData.title.startsWith('Ngân hàng') || examData.title.startsWith('Tổng hợp')) ? 'selected' : '';
        optionsHtml += `<option value="all" ${isMergedSelected}>📁 Tất cả các đề (Gộp ${mergedCount} câu)</option>`;

        examSets.forEach((set, i) => {
          const isSelected = examData.title === set.title ? 'selected' : '';
          optionsHtml += `<option value="set_${i}" ${isSelected}>📄 Đề ${i + 1}: ${set.title} (${set.questions.length} câu)</option>`;
        });

        selectExamSet.innerHTML = optionsHtml;
      }

      function saveProgressToLocalStorage() {
        try {
          localStorage.setItem('gfc_quiz_answers', JSON.stringify(userAnswers));
          localStorage.setItem('gfc_quiz_starred', JSON.stringify(Array.from(starredQuestions)));
        } catch (e) {}
      }

      // Render entire exam UI
      function renderExam() {
        topFormTitle.innerText = examData.title || 'Đề thi trắc nghiệm';
        topFormTitle.title = examData.title || '';

        // Populate section filter
        const sections = Array.from(new Set(examData.questions.map(q => q.section).filter(Boolean)));
        filterSectionSelect.innerHTML = '<option value="all">Tất cả các phần</option>';
        sections.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s;
          opt.innerText = s;
          filterSectionSelect.appendChild(opt);
        });

        // Filter active questions
        updateActiveQuestions();
      }

      function getActiveQuestions() {
        if (activeSection === 'all') return examData.questions;
        return examData.questions.filter(q => q.section === activeSection);
      }

      function updateActiveQuestions() {
        const questions = getActiveQuestions();
        if (questions.length === 0) {
          qTitleText.innerText = 'Chưa có câu hỏi nào. Hãy bấm nút "Import JSON" ở góc trên để tải đề!';
          optionsContainer.innerHTML = '';
          qImageContainer.style.display = 'none';
          explanationBox.style.display = 'none';
          paletteGrid.innerHTML = '';
          return;
        }

        if (currentIndex >= questions.length) {
          currentIndex = 0;
        }

        renderCurrentQuestion();
        renderPalette();
        updateStats();
      }

      // Render Current Question Card
      function renderCurrentQuestion() {
        const questions = getActiveQuestions();
        if (questions.length === 0) return;

        const q = questions[currentIndex];
        qIndexBadge.innerText = `Câu ${currentIndex + 1} / ${questions.length}`;
        qSectionBadge.innerText = q.section || 'Chung';
        qPointsBadge.innerText = q.points || '1 điểm';

        // Starred state
        const isStarred = starredQuestions.has(q.id || q.title);
        btnStarQuestion.innerText = isStarred ? '★ Đã đánh dấu' : '☆ Đánh dấu';
        btnStarQuestion.className = isStarred ? 'badge badge-star' : 'badge';

        // Title
        qTitleText.innerText = q.title || '[Câu hỏi hình ảnh]';

        // Image (Base64)
        if (q.image) {
          qImageEl.src = q.image;
          qImageContainer.style.display = 'block';
        } else {
          qImageContainer.style.display = 'none';
        }

        // Render Options
        optionsContainer.innerHTML = '';
        const userChoice = userAnswers[q.id || q.title];
        const hasAnswered = !!userChoice;

        if (q.options && q.options.length > 0) {
          q.options.forEach((opt, optIdx) => {
            const optText = typeof opt === 'string' ? opt : (opt.text || '');
            const optImg = typeof opt === 'object' ? opt.image : null;
            const letter = String.fromCharCode(65 + optIdx);
            const btn = document.createElement('button');
            btn.className = 'option-btn';

            // Check if correct
            const isThisCorrect = q.correctAnswer && (q.correctAnswer.trim().toLowerCase() === optText.trim().toLowerCase() || q.correctAnswer.trim() === letter);
            const isUserSelected = userChoice === optText;

            if (currentMode === 'practice' && hasAnswered) {
              if (isThisCorrect) {
                btn.classList.add('correct');
              } else if (isUserSelected) {
                btn.classList.add('wrong');
              }
            } else if (isUserSelected) {
              btn.classList.add('selected');
            }

            btn.innerHTML = `
              <span class="option-prefix">${letter}</span>
              <span class="option-text">${escapeHtml(optText)}</span>
              ${optImg ? `<img src="${optImg}" class="option-img" alt="Ảnh đáp án" />` : ''}
            `;

            btn.addEventListener('click', () => {
              handleOptionSelect(q, optText);
            });

            optionsContainer.appendChild(btn);
          });
        }

        // Explanation Box
        if (currentMode === 'practice' && (hasAnswered || q.userAnswered)) {
          explanationBox.style.display = 'block';
          if (q.explanation) {
            explanationText.innerHTML = `
              ${q.correctAnswer ? `<div style="font-weight: bold; margin-bottom: 6px;">✓ Đáp án chính xác: ${escapeHtml(q.correctAnswer)}</div>` : ''}
              <div>${escapeHtml(q.explanation)}</div>
            `;
          } else {
            explanationText.innerHTML = `
              ${q.correctAnswer ? `<div style="font-weight: bold; margin-bottom: 6px;">✓ Đáp án: ${escapeHtml(q.correctAnswer)}</div>` : ''}
              <div style="color: var(--text-sub); font-style: italic;">Chưa có lời giải thích chi tiết cho câu hỏi này. Bạn hãy bấm nút "Copy Prompt cho Gemini" ở trên để tạo giải thích!</div>
            `;
          }
        } else {
          explanationBox.style.display = 'none';
        }

        // Footer buttons state
        btnPrevQ.disabled = currentIndex === 0;
        btnNextQ.disabled = currentIndex === questions.length - 1;
      }

      // Handle Option Selection
      function handleOptionSelect(q, selectedText) {
        const qKey = q.id || q.title;
        userAnswers[qKey] = selectedText;
        q.userAnswered = true;

        saveProgressToLocalStorage();
        renderCurrentQuestion();
        renderPalette();
        updateStats();
      }

      // Render Question Palette Grid
      function renderPalette() {
        paletteGrid.innerHTML = '';
        const questions = getActiveQuestions();
        paletteProgressText.innerText = `${Object.keys(userAnswers).length}/${questions.length}`;

        questions.forEach((q, idx) => {
          const btn = document.createElement('button');
          btn.className = 'palette-btn';
          btn.innerText = String(idx + 1);

          const qKey = q.id || q.title;
          const userAns = userAnswers[qKey];

          if (idx === currentIndex) btn.classList.add('current');
          if (starredQuestions.has(qKey)) btn.classList.add('starred');

          if (userAns) {
            btn.classList.add('answered');
            if (q.correctAnswer) {
              const isRight = (q.correctAnswer.trim().toLowerCase() === userAns.trim().toLowerCase());
              btn.classList.add(isRight ? 'correct' : 'wrong');
            }
          }

          btn.addEventListener('click', () => {
            currentIndex = idx;
            renderCurrentQuestion();
            renderPalette();
          });

          paletteGrid.appendChild(btn);
        });
      }

      // Update Statistics
      function updateStats() {
        const questions = getActiveQuestions();
        let correct = 0;
        let wrong = 0;

        questions.forEach(q => {
          const userAns = userAnswers[q.id || q.title];
          if (userAns && q.correctAnswer) {
            if (q.correctAnswer.trim().toLowerCase() === userAns.trim().toLowerCase()) {
              correct++;
            } else {
              wrong++;
            }
          }
        });

        statCorrectCount.innerText = String(correct);
        statWrongCount.innerText = String(wrong);
      }

      // Render Study Sheet View
      function renderStudySheet() {
        sheetListContainer.innerHTML = '';
        const questions = getActiveQuestions();

        questions.forEach((q, idx) => {
          const item = document.createElement('div');
          item.className = 'sheet-item';

          let optionsHtml = '';
          if (q.options) {
            optionsHtml = '<div style="margin: 6px 0 6px 16px;">';
            q.options.forEach((opt, oIdx) => {
              const optText = typeof opt === 'string' ? opt : (opt.text || '');
              const letter = String.fromCharCode(65 + oIdx);
              const isCorrect = q.correctAnswer && (q.correctAnswer.trim().toLowerCase() === optText.trim().toLowerCase() || q.correctAnswer.trim() === letter);
              optionsHtml += `
                <div style="${isCorrect ? 'font-weight: bold; color: var(--success-dark);' : ''}">
                  ${letter}. ${escapeHtml(optText)} ${isCorrect ? '✓' : ''}
                </div>
              `;
            });
            optionsHtml += '</div>';
          }

          item.innerHTML = `
            <div class="sheet-title">Câu ${idx + 1}: ${escapeHtml(q.title)} ${q.points ? `(${escapeHtml(q.points)})` : ''}</div>
            ${q.image ? `<img src="${q.image}" style="max-height: 180px; margin: 6px 0;" />` : ''}
            ${optionsHtml}
            ${q.correctAnswer ? `<div class="sheet-ans">Đáp án đúng: ${escapeHtml(q.correctAnswer)}</div>` : ''}
            ${q.explanation ? `<div class="sheet-explain">💡 Giải thích: ${escapeHtml(q.explanation)}</div>` : ''}
          `;
          sheetListContainer.appendChild(item);
        });
      }

      // Setup Event Listeners
      function setupEventListeners() {
        document.getElementById("btn-print-sheet")?.addEventListener("click", () => window.print());
        // Mode switching
        document.querySelectorAll('.mode-tab').forEach(tab => {
          tab.addEventListener('click', () => {
            document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentMode = tab.getAttribute('data-mode');

            if (currentMode === 'sheet') {
              questionCard.style.display = 'none';
              sheetCard.style.display = 'block';
              renderStudySheet();
            } else {
              questionCard.style.display = 'block';
              sheetCard.style.display = 'none';
              renderCurrentQuestion();
            }
          });
        });

        // Navigation buttons
        btnPrevQ.addEventListener('click', () => {
          if (currentIndex > 0) {
            currentIndex--;
            renderCurrentQuestion();
            renderPalette();
          }
        });

        btnNextQ.addEventListener('click', () => {
          const questions = getActiveQuestions();
          if (currentIndex < questions.length - 1) {
            currentIndex++;
            renderCurrentQuestion();
            renderPalette();
          }
        });

        btnShowAnswer.addEventListener('click', () => {
          const questions = getActiveQuestions();
          const q = questions[currentIndex];
          if (q) {
            q.userAnswered = true;
            renderCurrentQuestion();
          }
        });

        // Star Question
        btnStarQuestion.addEventListener('click', () => {
          const questions = getActiveQuestions();
          const q = questions[currentIndex];
          if (!q) return;
          const qKey = q.id || q.title;

          if (starredQuestions.has(qKey)) {
            starredQuestions.delete(qKey);
          } else {
            starredQuestions.add(qKey);
          }
          saveProgressToLocalStorage();
          renderCurrentQuestion();
          renderPalette();
        });

        // Section filter
        filterSectionSelect.addEventListener('change', () => {
          activeSection = filterSectionSelect.value;
          currentIndex = 0;
          updateActiveQuestions();
        });

        // Shuffle questions
        btnShuffle.addEventListener('click', () => {
          if (confirm('Bạn có muốn trộn ngẫu nhiên thứ tự các câu hỏi không?')) {
            examData.questions.sort(() => Math.random() - 0.5);
            // Also shuffle options
            examData.questions.forEach(q => {
              if (q.options && q.options.length > 0) {
                q.options.sort(() => Math.random() - 0.5);
              }
            });
            currentIndex = 0;
            updateActiveQuestions();
            showToast('Đã trộn ngẫu nhiên câu hỏi & đáp án!');
          }
        });

        // Reset progress
        btnResetProgress.addEventListener('click', () => {
          if (confirm('Bạn có muốn xóa tiến độ làm bài và bắt đầu lại?')) {
            userAnswers = {};
            examData.questions.forEach(q => q.userAnswered = false);
            saveProgressToLocalStorage();
            currentIndex = 0;
            updateActiveQuestions();
            showToast('Đã làm mới tiến độ!');
          }
        });

        // Select Exam Set from dropdown
        if (selectExamSet) {
          selectExamSet.addEventListener('change', () => {
            const val = selectExamSet.value;
            if (val === 'all') {
              examData = mergeMultipleExamFiles(examSets);
            } else if (val.startsWith('set_')) {
              const idx = parseInt(val.replace('set_', ''), 10);
              if (examSets[idx]) {
                examData = {
                  title: examSets[idx].title,
                  description: examSets[idx].description || '',
                  questions: examSets[idx].questions
                };
              }
            }
            currentIndex = 0;
            userAnswers = {};
            renderExam();
            showToast(`Đang ôn tập: ${examData.title}`);
          });
        }

        // Copy Gemini Prompt
        btnCopyGeminiPrompt.addEventListener('click', () => {
          copyGeminiPrompt();
        });

        // Import Modal Handlers
        btnImportModal.addEventListener('click', () => {
          importJsonInput.value = '';
          pendingScannedFiles = [];
          renderScannedFilesPreview();
          importModal.style.display = 'flex';
        });
        btnCloseImport.addEventListener('click', () => { importModal.style.display = 'none'; });
        btnCancelImport.addEventListener('click', () => { importModal.style.display = 'none'; });

        // Browse Folder (webkitdirectory)
        if (btnBrowseFolder && folderInputJson) {
          btnBrowseFolder.addEventListener('click', () => {
            folderInputJson.value = '';
            folderInputJson.click();
          });
          folderInputJson.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
              processSelectedFileList(e.target.files);
            }
          });
        }

        // Browse Files (multiple)
        if (btnBrowseFiles && fileInputJson) {
          btnBrowseFiles.addEventListener('click', () => {
            fileInputJson.value = '';
            fileInputJson.click();
          });
          fileInputJson.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
              processSelectedFileList(e.target.files);
            }
          });
        }

        // Clear Scanned List
        if (btnClearScanned) {
          btnClearScanned.addEventListener('click', () => {
            pendingScannedFiles = [];
            renderScannedFilesPreview();
          });
        }

        // Drop Zone drag & drop (folder & files)
        if (importDropZone) {
          importDropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            importDropZone.classList.add('dragover');
          });
          importDropZone.addEventListener('dragleave', () => {
            importDropZone.classList.remove('dragover');
          });
          importDropZone.addEventListener('drop', async (e) => {
            e.preventDefault();
            importDropZone.classList.remove('dragover');
            const files = await getDroppedFiles(e.dataTransfer);
            if (files.length > 0) {
              processSelectedFileList(files);
            } else {
              showToast('Không tìm thấy file .json nào trong thư mục/lựa chọn!');
            }
          });
        }

        // Confirm Import Button
        btnConfirmImport.addEventListener('click', () => {
          if (pendingScannedFiles.length > 0) {
            const modeChoice = document.querySelector('input[name="import-mode-choice"]:checked')?.value || 'merge';

            examSets = pendingScannedFiles.map((f, i) => ({
              id: 'set_' + i,
              name: f.name,
              title: f.title || f.name.replace(/\.[^/.]+$/, ''),
              description: f.description || '',
              questions: f.questions.map((q, qIdx) => normalizeQuestion(q, null, qIdx))
            }));

            if (modeChoice === 'merge') {
              examData = mergeMultipleExamFiles(pendingScannedFiles);
            } else {
              examData = {
                title: examSets[0].title,
                description: examSets[0].description || '',
                questions: examSets[0].questions
              };
            }

            localStorage.setItem('gfc_quiz_data', JSON.stringify(examData));
            localStorage.setItem('gfc_exam_sets', JSON.stringify(examSets));

            if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
              chrome.storage.local.get(['forms', 'activeFormKey'], (res) => {
                const forms = res.forms || {};
                const key = res.activeFormKey || 'default_form';
                forms[key] = examData;
                chrome.storage.local.set({ forms });
              });
            }

            importModal.style.display = 'none';
            currentIndex = 0;
            userAnswers = {};
            renderExamSetSelector();
            renderExam();
            showToast(`Đã tải thành công ${examData.questions.length} câu hỏi từ ${pendingScannedFiles.length} file!`);
            pendingScannedFiles = [];
            return;
          }

          const raw = importJsonInput.value.trim();
          if (!raw) {
            showToast('Vui lòng chọn thư mục, chọn file hoặc dán mã JSON!');
            return;
          }
          processJsonImport(raw);
        });

        // Export JSON
        btnExportJson.addEventListener('click', () => {
          const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(examData, null, 2));
          const dlAnchor = document.createElement('a');
          dlAnchor.setAttribute('href', dataStr);
          dlAnchor.setAttribute('download', `${(examData.title || 'de_thi').replace(/\s+/g, '_')}_gemini_ready.json`);
          dlAnchor.click();
        });

        // Toggle Theme
        btnToggleTheme.addEventListener('click', () => {
          const cur = document.body.getAttribute('data-theme');
          const next = cur === 'dark' ? 'light' : 'dark';
          document.body.setAttribute('data-theme', next);
          localStorage.setItem('gfc_theme', next);
          btnToggleTheme.innerText = next === 'dark' ? '☀️' : '🌙';
        });

        // Drag and drop JSON/folders anywhere into window
        window.addEventListener('dragover', (e) => { e.preventDefault(); });
        window.addEventListener('drop', async (e) => {
          e.preventDefault();
          const files = await getDroppedFiles(e.dataTransfer);
          if (files.length > 0) {
            importModal.style.display = 'flex';
            processSelectedFileList(files);
          }
        });
      }

      // Recursive directory scanner for FileSystemEntry (drag and drop folder)
      async function scanDirectoryEntry(entry) {
        const files = [];
        if (entry.isFile) {
          if (entry.name.endsWith('.json') || entry.name.endsWith('.txt')) {
            const file = await new Promise(res => entry.file(res));
            files.push(file);
          }
        } else if (entry.isDirectory) {
          const reader = entry.createReader();
          const entries = await new Promise(res => {
            const results = [];
            function readNext() {
              reader.readEntries(batch => {
                if (batch.length === 0) res(results);
                else { results.push(...batch); readNext(); }
              }, () => res(results));
            }
            readNext();
          });
          for (const sub of entries) {
            const subFiles = await scanDirectoryEntry(sub);
            files.push(...subFiles);
          }
        }
        return files;
      }

      // Extract all files from drop event (handles folder drop)
      async function getDroppedFiles(dataTransfer) {
        const files = [];
        const items = dataTransfer.items;
        if (items && items.length > 0) {
          for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item.webkitGetAsEntry) {
              const entry = item.webkitGetAsEntry();
              if (entry) {
                const scanned = await scanDirectoryEntry(entry);
                files.push(...scanned);
                continue;
              }
            }
            const f = item.getAsFile ? item.getAsFile() : null;
            if (f && (f.name.endsWith('.json') || f.name.endsWith('.txt'))) {
              files.push(f);
            }
          }
        } else if (dataTransfer.files) {
          for (const f of dataTransfer.files) {
            if (f.name.endsWith('.json') || f.name.endsWith('.txt')) {
              files.push(f);
            }
          }
        }
        return files;
      }

      function readFileAsText(file) {
        return new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (e) => resolve(e.target.result);
          reader.onerror = reject;
          reader.readAsText(file);
        });
      }

      // Process selected / dropped files list
      async function processSelectedFileList(fileList) {
        const files = Array.from(fileList).filter(f => f.name.endsWith('.json') || f.name.endsWith('.txt'));
        if (files.length === 0) {
          showToast('Không tìm thấy file .json nào trong thư mục/lựa chọn!');
          return;
        }

        showToast(`Đang quét ${files.length} file...`, 1500);
        pendingScannedFiles = [];

        for (const file of files) {
          try {
            const text = await readFileAsText(file);
            let clean = text.trim();
            const fence = clean.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
            if (fence && fence[1]) clean = fence[1].trim();

            const parsed = JSON.parse(clean);
            let questions = [];
            let title = file.name.replace(/\.[^/.]+$/, '');
            let desc = '';

            if (parsed.questions && Array.isArray(parsed.questions)) {
              questions = parsed.questions;
              if (parsed.title) title = parsed.title;
              if (parsed.description) desc = parsed.description;
            } else if (Array.isArray(parsed)) {
              questions = parsed;
            }

            if (questions.length > 0) {
              pendingScannedFiles.push({
                file: file,
                name: file.name,
                path: file.webkitRelativePath || file.name,
                title: title,
                description: desc,
                questions: questions
              });
            }
          } catch (e) {
            console.warn(`Bỏ qua file lỗi ${file.name}:`, e);
          }
        }

        renderScannedFilesPreview();
      }

      // Render preview of scanned files inside modal
      function renderScannedFilesPreview() {
        if (!scannedFilesContainer || !scannedFilesList) return;

        if (pendingScannedFiles.length === 0) {
          scannedFilesContainer.style.display = 'none';
          return;
        }

        scannedFilesContainer.style.display = 'block';
        const totalQ = pendingScannedFiles.reduce((acc, f) => acc + f.questions.length, 0);
        scannedSummaryText.innerText = `✅ Đã quét ${pendingScannedFiles.length} file JSON (Tổng: ${totalQ} câu)`;

        scannedFilesList.innerHTML = pendingScannedFiles.map(f => `
          <div class="scanned-file-item">
            <div class="scanned-file-name" title="${f.path}">
              <span>📄</span>
              <span>${f.name}</span>
              <span style="font-size: 11px; color: var(--text-sub); font-weight: normal;">(${f.title})</span>
            </div>
            <span class="scanned-file-count">${f.questions.length} câu</span>
          </div>
        `).join('');
      }

      // Get question canonical key for deduplication
      function getQuestionKey(q) {
        if (q.id && !String(q.id).startsWith('q_')) return 'id:' + q.id;
        const cleanTitle = (q.title || '')
          .toLowerCase()
          .replace(/^(câu|bài|question)\s*\d+[\s\:\.\-]/i, '')
          .replace(/\s+/g, ' ')
          .trim();
        if ((cleanTitle === '[câu hỏi hình ảnh]' || !cleanTitle) && q.image) {
          return 'img:' + q.image.slice(0, 100);
        }
        return 'title:' + (q.section ? q.section.toLowerCase() + '::' : '') + cleanTitle;
      }

      // Normalize a question object
      function normalizeQuestion(q, existing, idx = 0) {
        let normalizedOptions = [];
        if (Array.isArray(q.options)) {
          normalizedOptions = q.options.map((opt, optIdx) => {
            const optText = typeof opt === 'string' ? opt : (opt.text || '');
            const existingOpt = existing && existing.options ? existing.options[optIdx] : null;
            const optImage = (typeof opt === 'object' && opt.image) || (existingOpt && existingOpt.image) || null;
            return { text: optText, image: optImage };
          });
        } else if (existing && existing.options) {
          normalizedOptions = existing.options;
        }

        return {
          id: q.id || (existing && existing.id) || String(idx + 1),
          title: q.title || (existing && existing.title) || '[Câu hỏi]',
          description: q.description || (existing && existing.description) || '',
          section: q.section || (existing && existing.section) || '',
          type: q.type || (existing && existing.type) || 'multiple_choice',
          image: q.image || (existing && existing.image) || null,
          options: normalizedOptions,
          correctAnswer: q.correctAnswer || (existing && existing.correctAnswer) || '',
          explanation: q.explanation || q.feedback || (existing && (existing.explanation || existing.feedback)) || '',
          points: q.points || (existing && existing.points) || ''
        };
      }

      // Merge multiple exam files into one combined exam bank with smart deduplication
      function mergeMultipleExamFiles(filesList) {
        const map = new Map();
        let combinedTitle = '';

        filesList.forEach((f, fileIdx) => {
          if (fileIdx === 0) combinedTitle = f.title;
          else if (!combinedTitle.includes(f.title) && fileIdx < 3) {
            combinedTitle += ' + ' + f.title;
          }

          f.questions.forEach((rawQ, qIdx) => {
            const q = normalizeQuestion(rawQ, null, qIdx);
            const key = getQuestionKey(q);

            if (map.has(key)) {
              const existing = map.get(key);
              if (!existing.points && q.points) existing.points = q.points;
              if (!existing.section && q.section) existing.section = q.section;
              if (!existing.correctAnswer && q.correctAnswer) existing.correctAnswer = q.correctAnswer;
              if (!existing.explanation && q.explanation) existing.explanation = q.explanation;
              if ((!existing.image || !existing.image.startsWith('data:image/')) && q.image) {
                existing.image = q.image;
              }
              if (q.options && q.options.length > 0) {
                if (!existing.options || existing.options.length === 0) {
                  existing.options = q.options;
                } else {
                  q.options.forEach(opt => {
                    if (!existing.options.some(o => o.text.trim().toLowerCase() === opt.text.trim().toLowerCase())) {
                      existing.options.push(opt);
                    }
                  });
                }
              }
            } else {
              map.set(key, q);
            }
          });
        });

        const mergedQuestions = Array.from(map.values());
        return {
          title: filesList.length > 1 ? `Ngân hàng câu hỏi gộp (${filesList.length} đề thi)` : combinedTitle,
          description: `Được tổng hợp từ ${filesList.length} file JSON (${mergedQuestions.length} câu hỏi duy nhất)`,
          questions: mergedQuestions
        };
      }

      // Process and sanitize imported JSON (handles raw JSON or Gemini Markdown response)
      function processJsonImport(raw) {
        try {
          let cleanJson = raw.trim();
          // Extract from markdown ```json ... ``` code fence if present
          const fenceMatch = cleanJson.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
          if (fenceMatch && fenceMatch[1]) {
            cleanJson = fenceMatch[1].trim();
          }

          const parsed = JSON.parse(cleanJson);
          let newQuestions = [];
          if (parsed.questions && Array.isArray(parsed.questions)) {
            newQuestions = parsed.questions;
            if (parsed.title) examData.title = parsed.title;
          } else if (Array.isArray(parsed)) {
            newQuestions = parsed;
          } else {
            showToast('Cấu trúc JSON không hợp lệ! Cần có mảng "questions".');
            return;
          }

          // Build map of existing questions to preserve images when Gemini strips them
          const existingMap = new Map();
          if (examData.questions && Array.isArray(examData.questions)) {
            examData.questions.forEach((q, i) => {
              if (q.id) existingMap.set(String(q.id), q);
              if (q.title) existingMap.set(q.title.trim().toLowerCase(), q);
              existingMap.set(`idx_${i}`, q);
            });
          }

          examData.questions = newQuestions.map((q, idx) => {
            const existing = (q.id && existingMap.get(String(q.id))) ||
                             (q.title && existingMap.get(q.title.trim().toLowerCase())) ||
                             existingMap.get(`idx_${idx}`);

            // Normalize options to [{ text: string, image: string|null }]
            let normalizedOptions = [];
            if (Array.isArray(q.options)) {
              normalizedOptions = q.options.map((opt, optIdx) => {
                const optText = typeof opt === 'string' ? opt : (opt.text || '');
                const existingOpt = existing && existing.options ? existing.options[optIdx] : null;
                const optImage = (typeof opt === 'object' && opt.image) || (existingOpt && existingOpt.image) || null;
                return { text: optText, image: optImage };
              });
            } else if (existing && existing.options) {
              normalizedOptions = existing.options;
            }

            return {
              id: q.id || (existing && existing.id) || String(idx + 1),
              title: q.title || (existing && existing.title) || '[Câu hỏi]',
              description: q.description || (existing && existing.description) || '',
              section: q.section || (existing && existing.section) || '',
              type: q.type || (existing && existing.type) || 'multiple_choice',
              image: q.image || (existing && existing.image) || null,
              options: normalizedOptions,
              correctAnswer: q.correctAnswer || (existing && existing.correctAnswer) || '',
              explanation: q.explanation || q.feedback || (existing && (existing.explanation || existing.feedback)) || '',
              points: q.points || (existing && existing.points) || ''
            };
          });

          localStorage.setItem('gfc_quiz_data', JSON.stringify(examData));
          examSets = [{
            id: 'set_0',
            name: examData.title || 'Đề thi trắc nghiệm',
            title: examData.title || 'Đề thi trắc nghiệm',
            questions: examData.questions
          }];
          localStorage.setItem('gfc_exam_sets', JSON.stringify(examSets));

          // Also sync to chrome.storage.local if available
          if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
            chrome.storage.local.get(['forms', 'activeFormKey'], (res) => {
              const forms = res.forms || {};
              const key = res.activeFormKey || 'default_form';
              forms[key] = examData;
              chrome.storage.local.set({ forms });
            });
          }

          importModal.style.display = 'none';
          currentIndex = 0;
          userAnswers = {};
          renderExamSetSelector();
          renderExam();
          showToast(`Đã import thành công ${examData.questions.length} câu hỏi kèm đáp án & giải thích!`);
        } catch (err) {
          showToast('Lỗi phân tích JSON: ' + err.message);
        }
      }

      // Generate and copy ready-to-paste Gemini Chat prompt
      function copyGeminiPrompt() {
        if (!examData || !examData.questions || examData.questions.length === 0) {
          showToast('Chưa có câu hỏi nào để gửi Gemini!');
          return;
        }

        // Prepare clean questions array for Gemini (excluding heavy base64 to save prompt tokens)
        const promptQuestions = examData.questions.map((q, idx) => {
          return {
            id: q.id || String(idx + 1),
            section: q.section || '',
            title: q.title || '[Câu hỏi hình ảnh]',
            hasImage: !!q.image,
            options: q.options ? q.options.map(o => o.text) : [],
            correctAnswer: q.correctAnswer || '',
            explanation: q.explanation || ''
          };
        });

        const promptText = `Bạn là một chuyên gia giáo dục và khảo thí. Tôi có bộ câu hỏi trắc nghiệm dưới đây (được trích xuất từ đề thi).

NHIỆM VỤ CỦA BẠN:
1. Giải từng câu hỏi và điền đáp án chính xác vào trường "correctAnswer".
   LƯU Ý: Nội dung "correctAnswer" phải trùng khớp chính xác với 1 trong các giá trị trong mảng "options".
2. Viết lời giải thích ngắn gọn, súc tích và dễ hiểu vào trường "explanation" (nêu rõ lý do vì sao đáp án đó đúng).
3. Giữ nguyên toàn bộ cấu trúc và thứ tự câu hỏi trong file JSON.
4. Trả về DUY NHẤT một khối mã JSON hợp lệ (bọc trong \`\`\`json ... \`\`\`) để tôi có thể copy và import lại vào trang web ôn tập.

Dưới đây là dữ liệu JSON:
\`\`\`json
${JSON.stringify({
  title: examData.title || 'Đề thi trắc nghiệm',
  totalQuestions: examData.questions.length,
  questions: promptQuestions
}, null, 2)}
\`\`\`
`;

        navigator.clipboard.writeText(promptText).then(() => {
          showToast('Đã copy Prompt + Toàn bộ câu hỏi vào Clipboard! Hãy dán vào Gemini chat.');
        }).catch(err => {
          showToast('Lỗi sao chép: ' + err.message);
        });
      }

      function loadTheme() {
        const t = localStorage.getItem('gfc_theme') || 'light';
        document.body.setAttribute('data-theme', t);
        btnToggleTheme.innerText = t === 'dark' ? '☀️' : '🌙';
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

    })();