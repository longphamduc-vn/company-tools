/**
 * popup.js - High-Performance Extension UI & Multi-Table Exporter
 * Features: Full-Tab Mode, Data Origin Lineage (User Input vs Prior Response), and Paged Table Matrix.
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'ems_captured_apis';
  const CARDS_BATCH_SIZE = 25;

  // Check if opened in full tab mode
  const urlParams = new URLSearchParams(window.location.search);
  const isFullTab = urlParams.get('mode') === 'tab' || window.innerWidth > 800;
  if (isFullTab) {
    document.body.classList.add('full-tab-mode');
  }

  // DOM elements
  const btnOpenFullTab = document.getElementById('btnOpenFullTab');
  const apiListContainer = document.getElementById('apiList');
  const cardsFooterBar = document.getElementById('cardsFooterBar');
  const cardsCountLabel = document.getElementById('cardsCountLabel');
  const btnLoadMoreCards = document.getElementById('btnLoadMoreCards');

  const tableViewContainer = document.getElementById('tableViewContainer');
  const matrixTable = document.getElementById('matrixTable');
  const tablePaginationInfo = document.getElementById('tablePaginationInfo');
  const pageCurrentDisplay = document.getElementById('pageCurrentDisplay');
  const pageSizeSelect = document.getElementById('pageSizeSelect');
  const btnPrevTablePage = document.getElementById('btnPrevTablePage');
  const btnNextTablePage = document.getElementById('btnNextTablePage');

  const btnToggleView = document.getElementById('btnToggleView');
  const viewToggleLabel = document.getElementById('viewToggleLabel');

  const exportDropdownContainer = document.getElementById('exportDropdownContainer');
  const btnExportMenu = document.getElementById('btnExportMenu');
  const btnExportCsvDeps = document.getElementById('btnExportCsvDeps');
  const btnExportCsvApis = document.getElementById('btnExportCsvApis');
  const btnExportCsvPayloads = document.getElementById('btnExportCsvPayloads');
  const btnExportCsvResponses = document.getElementById('btnExportCsvResponses');
  const btnExportJson = document.getElementById('btnExportJson');
  const btnDownloadActiveTableCsv = document.getElementById('btnDownloadActiveTableCsv');

  const btnClear = document.getElementById('btnClear');
  const searchInput = document.getElementById('searchInput');
  const countAllEl = document.getElementById('countAll');
  const countDepsEl = document.getElementById('countDeps');
  const countInputsEl = document.getElementById('countInputs');
  const countErrorsEl = document.getElementById('countErrors');
  
  const tableDepsCount = document.getElementById('tableDepsCount');
  const tableApisCount = document.getElementById('tableApisCount');
  const tablePayloadsCount = document.getElementById('tablePayloadsCount');
  const tableResponsesCount = document.getElementById('tableResponsesCount');
  
  const toastEl = document.getElementById('toast');
  const filterChips = document.querySelectorAll('.chip');
  const tableSubtabs = document.querySelectorAll('.table-subtab');

  // Application State
  let currentLogs = [];
  let computedLogs = [];
  let activeFilter = 'all'; // 'all', 'deps', 'user_inputs', 'errors'
  let currentViewMode = 'cards'; // 'cards' | 'table'
  let activeTableTab = 'matrix'; // 'matrix' | 'summary' | 'payloads' | 'responses'
  
  // Performance State
  let cardsRenderedCount = 0;
  let tableCurrentPage = 1;
  let tablePageSize = 50;
  let searchDebounceTimer = null;
  let toastTimer = null;

  document.addEventListener('DOMContentLoaded', () => {
    loadLogs();
    setupEventListeners();
  });

  function setupEventListeners() {
    // 1. Full Tab Button
    btnOpenFullTab.addEventListener('click', () => {
      chrome.tabs.create({ url: chrome.runtime.getURL('popup.html?mode=tab') });
    });

    // 2. Export Menu
    btnExportMenu.addEventListener('click', (e) => {
      e.stopPropagation();
      exportDropdownContainer.classList.toggle('open');
    });

    document.addEventListener('click', () => {
      exportDropdownContainer.classList.remove('open');
    });

    btnExportCsvDeps.addEventListener('click', () => {
      exportDropdownContainer.classList.remove('open');
      handleExportCsvDependencies();
    });

    btnExportCsvApis.addEventListener('click', () => {
      exportDropdownContainer.classList.remove('open');
      handleExportCsvApis();
    });

    btnExportCsvPayloads.addEventListener('click', () => {
      exportDropdownContainer.classList.remove('open');
      handleExportCsvPayloads();
    });

    btnExportCsvResponses.addEventListener('click', () => {
      exportDropdownContainer.classList.remove('open');
      handleExportCsvResponses();
    });

    btnExportJson.addEventListener('click', () => {
      exportDropdownContainer.classList.remove('open');
      handleExportJSON();
    });

    btnDownloadActiveTableCsv.addEventListener('click', () => {
      if (activeTableTab === 'matrix') {
        handleExportCsvDependencies();
      } else if (activeTableTab === 'summary') {
        handleExportCsvApis();
      } else if (activeTableTab === 'payloads') {
        handleExportCsvPayloads();
      } else if (activeTableTab === 'responses') {
        handleExportCsvResponses();
      }
    });

    // 3. View Mode Toggle
    btnToggleView.addEventListener('click', () => {
      if (currentViewMode === 'cards') {
        currentViewMode = 'table';
        btnToggleView.classList.add('active-view');
        viewToggleLabel.textContent = 'Cards View';
        document.getElementById('cardsViewContainer').style.display = 'none';
        tableViewContainer.style.display = 'flex';
        tableCurrentPage = 1;
        renderActiveTableView();
      } else {
        currentViewMode = 'cards';
        btnToggleView.classList.remove('active-view');
        viewToggleLabel.textContent = 'Table View';
        document.getElementById('cardsViewContainer').style.display = 'flex';
        tableViewContainer.style.display = 'none';
        renderList();
      }
    });

    // 4. Cards Batch Load More & Infinite Scroll
    btnLoadMoreCards.addEventListener('click', () => {
      renderNextCardsBatch();
    });

    apiListContainer.addEventListener('scroll', () => {
      if (apiListContainer.scrollTop + apiListContainer.clientHeight >= apiListContainer.scrollHeight - 60) {
        renderNextCardsBatch();
      }
    });

    // 5. Table Sub-tabs
    tableSubtabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        tableSubtabs.forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        activeTableTab = tab.getAttribute('data-table-tab') || 'matrix';
        tableCurrentPage = 1;
        renderActiveTableView();
      });
    });

    // 6. Table Pagination Controls
    pageSizeSelect.addEventListener('change', (e) => {
      tablePageSize = parseInt(e.target.value, 10);
      tableCurrentPage = 1;
      renderActiveTableView();
    });

    btnPrevTablePage.addEventListener('click', () => {
      if (tableCurrentPage > 1) {
        tableCurrentPage--;
        renderActiveTableView();
      }
    });

    btnNextTablePage.addEventListener('click', () => {
      tableCurrentPage++;
      renderActiveTableView();
    });

    // 7. Search & Filters with Debounce
    btnClear.addEventListener('click', handleClearLogs);
    searchInput.addEventListener('input', () => {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        tableCurrentPage = 1;
        if (currentViewMode === 'cards') {
          renderList();
        } else {
          renderActiveTableView();
        }
      }, 180);
    });

    filterChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        filterChips.forEach((c) => c.classList.remove('active'));
        chip.classList.add('active');
        activeFilter = chip.getAttribute('data-filter') || 'all';
        tableCurrentPage = 1;
        if (currentViewMode === 'cards') {
          renderList();
        } else {
          renderActiveTableView();
        }
      });
    });
  }

  function loadLogs() {
    chrome.storage.local.get([STORAGE_KEY], (res) => {
      currentLogs = res[STORAGE_KEY] || [];
      if (!Array.isArray(currentLogs)) currentLogs = [];

      computeDataAndLineage();
      updateHeaderCounts();
      if (currentViewMode === 'cards') {
        renderList();
      } else {
        renderActiveTableView();
      }
    });
  }

  function computeDataAndLineage() {
    computedLogs = [];

    for (let i = 0; i < currentLogs.length; i++) {
      const current = currentLogs[i];
      const pastApis = currentLogs.slice(0, i);

      let dependencies = [];
      let parsedRequest = null;
      let parsedResponse = null;

      if (window.NexacroDependencyEngine) {
        if (current.requestBody) {
          parsedRequest = window.NexacroDependencyEngine.parseNexacroXML(current.requestBody);
          if (pastApis.length > 0) {
            dependencies = window.NexacroDependencyEngine.findDependencies(parsedRequest, pastApis);
          }
        }
        if (current.responseBody) {
          parsedResponse = window.NexacroDependencyEngine.parseNexacroXML(current.responseBody);
        }
      }

      dependencies = dependencies.map((dep, depIdx) => ({
        ...dep,
        depIndex: depIdx + 1,
        targetApiNo: i + 1,
        targetMethod: current.method,
        targetUrl: current.url
      }));

      // Pre-index sourced targets for O(1) origin lookup
      const sourcedTargetsMap = new Map();
      dependencies.forEach((d) => {
        sourcedTargetsMap.set(d.targetLocation, d);
      });

      computedLogs.push({
        ...current,
        index: i + 1,
        parsedRequest: parsedRequest,
        parsedResponse: parsedResponse,
        dependencies: dependencies,
        sourcedTargetsMap: sourcedTargetsMap
      });
    }
  }

  function updateHeaderCounts() {
    const total = computedLogs.length;
    const depsCount = computedLogs.filter((item) => item.dependencies && item.dependencies.length > 0).length;
    const errorsCount = computedLogs.filter((item) => item.status >= 400 || item.status === 0).length;

    let totalDepMappings = 0;
    let totalReqItems = 0;
    let totalResItems = 0;
    let totalUserInputs = 0;

    computedLogs.forEach((item) => {
      totalDepMappings += (item.dependencies || []).length;
      if (item.parsedRequest && item.parsedRequest.flatItems) {
        totalReqItems += item.parsedRequest.flatItems.length;
        item.parsedRequest.flatItems.forEach((f) => {
          if (!item.sourcedTargetsMap.has(f.xpath)) {
            totalUserInputs++;
          }
        });
      }
      if (item.parsedResponse && item.parsedResponse.flatItems) {
        totalResItems += item.parsedResponse.flatItems.length;
      }
    });

    countAllEl.textContent = String(total);
    countDepsEl.textContent = String(depsCount);
    countInputsEl.textContent = String(totalUserInputs);
    countErrorsEl.textContent = String(errorsCount);

    tableDepsCount.textContent = String(totalDepMappings);
    tableApisCount.textContent = String(total);
    tablePayloadsCount.textContent = String(totalReqItems);
    tableResponsesCount.textContent = String(totalResItems);
  }

  function getFilteredApis() {
    const query = (searchInput.value || '').trim().toLowerCase();

    return computedLogs.filter((item) => {
      if (activeFilter === 'deps' && (!item.dependencies || item.dependencies.length === 0)) {
        return false;
      }
      if (activeFilter === 'user_inputs') {
        const hasInputs = item.parsedRequest && item.parsedRequest.flatItems &&
          item.parsedRequest.flatItems.some((f) => !item.sourcedTargetsMap.has(f.xpath));
        if (!hasInputs) return false;
      }
      if (activeFilter === 'errors' && !(item.status >= 400 || item.status === 0)) {
        return false;
      }

      if (!query) return true;
      const inUrl = item.url.toLowerCase().includes(query);
      const inMethod = item.method.toLowerCase().includes(query);
      const inStatus = String(item.status).includes(query);

      let inDeps = false;
      if (item.dependencies) {
        inDeps = item.dependencies.some(
          (d) =>
            d.targetKey.toLowerCase().includes(query) ||
            d.targetValue.toLowerCase().includes(query) ||
            d.sourceKey.toLowerCase().includes(query) ||
            d.targetLocation.toLowerCase().includes(query) ||
            d.sourceXPath.toLowerCase().includes(query)
        );
      }

      let inPayload = false;
      if (item.parsedRequest && item.parsedRequest.flatItems) {
        inPayload = item.parsedRequest.flatItems.some(
          (f) => f.key.toLowerCase().includes(query) || f.value.toLowerCase().includes(query)
        );
      }

      let inResponse = false;
      if (item.parsedResponse && item.parsedResponse.flatItems) {
        inResponse = item.parsedResponse.flatItems.some(
          (f) => f.key.toLowerCase().includes(query) || f.value.toLowerCase().includes(query)
        );
      }

      return inUrl || inMethod || inStatus || inDeps || inPayload || inResponse;
    });
  }
  // ========================================================
  // RENDER 1: Card List View with Virtual Incremental Batching & Lazy Drawers
  // ========================================================
  function renderList() {
    apiListContainer.innerHTML = '';
    cardsRenderedCount = 0;
    renderNextCardsBatch();
  }

  function renderNextCardsBatch() {
    const filtered = getFilteredApis();
    const total = filtered.length;

    if (total === 0) {
      apiListContainer.innerHTML = `
        <div class="empty-state">
          <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          </svg>
          <div class="empty-title">No Nexacro Traffic Found</div>
          <div class="empty-desc">Make HTTP requests on your EMS Nexacro application to monitor parameters, datasets, and API data dependencies.</div>
        </div>
      `;
      cardsFooterBar.style.display = 'none';
      return;
    }

    cardsFooterBar.style.display = 'flex';

    if (cardsRenderedCount >= total) {
      cardsCountLabel.textContent = `Showing all ${total} requests`;
      btnLoadMoreCards.style.display = 'none';
      return;
    }

    const nextBatch = filtered.slice(cardsRenderedCount, cardsRenderedCount + CARDS_BATCH_SIZE);
    nextBatch.forEach((api) => {
      const card = createApiCard(api);
      apiListContainer.appendChild(card);
    });

    cardsRenderedCount += nextBatch.length;
    cardsCountLabel.textContent = `Showing ${cardsRenderedCount} of ${total} requests`;

    if (cardsRenderedCount < total) {
      btnLoadMoreCards.style.display = 'inline-block';
      btnLoadMoreCards.textContent = `Load More (+${Math.min(CARDS_BATCH_SIZE, total - cardsRenderedCount)})`;
    } else {
      btnLoadMoreCards.style.display = 'none';
    }
  }

  function createApiCard(api) {
    const card = document.createElement('div');
    card.className = 'api-card';

    const isPost = api.method === 'POST';
    const methodClass = isPost ? 'method-post' : 'method-get';
    const isSuccess = api.status >= 200 && api.status < 300;
    const statusClass = isSuccess ? 'status-2xx' : 'status-err';
    const depCount = api.dependencies ? api.dependencies.length : 0;

    let urlPath = api.url;
    let urlHost = '';
    try {
      const parsedUrl = new URL(api.url);
      urlPath = parsedUrl.pathname + parsedUrl.search;
      urlHost = parsedUrl.host;
    } catch (e) {}

    const durationText = api.durationMs ? `${api.durationMs}ms` : '';

    card.innerHTML = `
      <div class="card-header">
        <div class="card-meta-left">
          <span style="font-size: 11px; font-weight: 700; color: var(--text-faint);">#${api.index}</span>
          <span class="method-badge ${methodClass}">${escapeHtml(api.method)}</span>
          <span class="status-badge ${statusClass}">${api.status || 'ERR'}</span>
          <div class="url-display" title="${escapeHtml(api.url)}">
            <span class="url-path">${escapeHtml(urlPath)}</span>
            ${urlHost ? `<span class="url-host">${escapeHtml(urlHost)}</span>` : ''}
          </div>
        </div>
        <div class="card-meta-right">
          ${
            depCount > 0
              ? `<div class="dep-pill" title="${depCount} variables linked from prior APIs">
                   <span>⚡</span> ${depCount} Linked
                 </div>`
              : ''
          }
          ${durationText ? `<span class="duration-label">${durationText}</span>` : ''}
          <svg class="chevron-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>
      <div class="card-drawer"></div>
    `;

    const header = card.querySelector('.card-header');
    header.addEventListener('click', () => {
      const isCurrentlyOpen = card.classList.contains('open');
      if (!isCurrentlyOpen) {
        if (!card.dataset.drawerBuilt) {
          buildDrawerContent(api, card);
          card.dataset.drawerBuilt = 'true';
        }
        card.classList.add('open');
      } else {
        card.classList.remove('open');
      }
    });

    return card;
  }

  function buildDrawerContent(api, card) {
    const drawer = card.querySelector('.card-drawer');
    const depCount = api.dependencies ? api.dependencies.length : 0;

    drawer.innerHTML = `
      <div class="drawer-tabs">
        <div class="nav-tabs">
          <button class="tab-btn tab-dep ${depCount > 0 ? 'active' : ''}" data-pane="deps">
            ⚡ Dependencies (${depCount})
          </button>
          <button class="tab-btn ${depCount === 0 ? 'active' : ''}" data-pane="payload">
            Payload (Request)
          </button>
          <button class="tab-btn" data-pane="response">
            Response
          </button>
        </div>
        <div class="view-mode-toggle" title="Switch between structured tables and raw formatted XML">
          <div class="toggle-opt active" data-mode="structured">Structured</div>
          <div class="toggle-opt" data-mode="raw">Raw XML</div>
        </div>
      </div>

      <div class="tab-pane ${depCount > 0 ? 'active' : ''}" data-pane-content="deps">
        ${renderDependenciesPane(api.dependencies)}
      </div>

      <div class="tab-pane ${depCount === 0 ? 'active' : ''}" data-pane-content="payload">
        <div class="pane-view-structured">
          ${renderStructuredXml(api.parsedRequest, 'Request', api.index, api.sourcedTargetsMap)}
        </div>
        <div class="pane-view-raw" style="display: none;">
          <div class="raw-code-container">
            <div class="raw-code-actions">
              <button class="btn-secondary btn-copy-raw" data-copy="${escapeAttr(api.requestBody)}">
                Copy XML
              </button>
            </div>
            <pre class="code-view">${formatAndHighlightXml(api.requestBody)}</pre>
          </div>
        </div>
      </div>

      <div class="tab-pane" data-pane-content="response">
        <div class="pane-view-structured">
          ${renderStructuredXml(api.parsedResponse, 'Response', api.index, null)}
        </div>
        <div class="pane-view-raw" style="display: none;">
          <div class="raw-code-container">
            <div class="raw-code-actions">
              <button class="btn-secondary btn-copy-raw" data-copy="${escapeAttr(api.responseBody)}">
                Copy XML
              </button>
            </div>
            <pre class="code-view">${formatAndHighlightXml(api.responseBody)}</pre>
          </div>
        </div>
      </div>
    `;

    const tabBtns = drawer.querySelectorAll('.tab-btn');
    const tabPanes = drawer.querySelectorAll('.tab-pane');

    tabBtns.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const target = btn.getAttribute('data-pane');
        tabBtns.forEach((b) => b.classList.remove('active'));
        tabPanes.forEach((p) => p.classList.remove('active'));

        btn.classList.add('active');
        const targetPane = drawer.querySelector(`.tab-pane[data-pane-content="${target}"]`);
        if (targetPane) targetPane.classList.add('active');
      });
    });

    const toggleOpts = drawer.querySelectorAll('.toggle-opt');
    toggleOpts.forEach((opt) => {
      opt.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleOpts.forEach((o) => o.classList.remove('active'));
        opt.classList.add('active');
        const mode = opt.getAttribute('data-mode');

        const activePane = drawer.querySelector('.tab-pane.active');
        if (activePane) {
          const structView = activePane.querySelector('.pane-view-structured');
          const rawView = activePane.querySelector('.pane-view-raw');
          if (structView && rawView) {
            if (mode === 'structured') {
              structView.style.display = 'block';
              rawView.style.display = 'none';
            } else {
              structView.style.display = 'none';
              rawView.style.display = 'block';
            }
          }
        }
      });
    });

    drawer.querySelectorAll('.btn-copy-raw').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        copyToClipboard(btn.getAttribute('data-copy'));
      });
    });

    drawer.addEventListener('click', (e) => {
      const copyTarget = e.target.closest('[data-copy-text]');
      if (copyTarget) {
        e.stopPropagation();
        copyToClipboard(copyTarget.getAttribute('data-copy-text'));
      }

      const singleExportBtn = e.target.closest('.btn-export-single-csv');
      if (singleExportBtn) {
        e.stopPropagation();
        const aIndex = parseInt(singleExportBtn.getAttribute('data-api-index'), 10);
        const aType = singleExportBtn.getAttribute('data-type');
        handleExportSingleApiCsv(aIndex, aType);
      }
    });
  }

  function renderDependenciesPane(dependencies) {
    if (!dependencies || dependencies.length === 0) {
      return `
        <div style="padding: 14px; text-align: center; color: var(--text-muted); font-size: 11.5px;">
          No incoming data dependencies detected. All values appear to be direct user inputs or static constants.
        </div>
      `;
    }

    let itemsHtml = '';
    dependencies.forEach((d) => {
      let sourceUrlShort = d.sourceApiUrl;
      try {
        const u = new URL(d.sourceApiUrl);
        sourceUrlShort = u.pathname;
      } catch (e) {}

      itemsHtml += `
        <div class="dep-flow-item">
          <div class="dep-row-top">
            <div class="dep-target-field">
              <span>Target: <strong>${escapeHtml(d.targetKey)}</strong></span>
            </div>
            <div class="dep-val-pill" title="Click to copy value" data-copy-text="${escapeAttr(d.targetValue)}" style="cursor: pointer;">
              "${escapeHtml(d.targetValue)}" 📋
            </div>
          </div>

          <div class="dep-lineage-flow">
            <div class="flow-col">
              <span class="flow-label">Target XPath (This Request)</span>
              <div class="xpath-pill">
                <span>${escapeHtml(d.targetLocation)}</span>
                <button class="copy-btn" title="Copy XPath" data-copy-text="${escapeAttr(d.targetLocation)}">📋</button>
              </div>
            </div>

            <div class="flow-arrow">➔</div>

            <div class="flow-col">
              <span class="flow-label">Source Origin: ${escapeHtml(d.sourceMethod)} ${escapeHtml(sourceUrlShort)}</span>
              <div class="xpath-pill source">
                <span>${escapeHtml(d.sourceXPath)}</span>
                <button class="copy-btn" title="Copy XPath" data-copy-text="${escapeAttr(d.sourceXPath)}">📋</button>
              </div>
            </div>
          </div>
        </div>
      `;
    });

    return `<div class="dep-flow-container">${itemsHtml}</div>`;
  }

  function renderStructuredXml(parsedObj, label, apiIndex, sourcedTargetsMap) {
    if (!parsedObj || !parsedObj.isValidNexacro) {
      return `
        <div style="padding: 10px; color: var(--text-muted); font-size: 11.5px;">
          No Nexacro Parameters or Datasets detected in this ${label}. Switch to "Raw XML" view to see full payload.
        </div>
      `;
    }

    let html = `
      <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
        <button class="btn-secondary btn-export-single-csv" data-api-index="${apiIndex}" data-type="${label.toLowerCase()}" style="font-size: 10.5px; padding: 2px 7px;">
          📊 Export ${label} as CSV Table
        </button>
      </div>
    `;

    const isRequest = label.toLowerCase() === 'request';
    const paramKeys = Object.keys(parsedObj.parameters || {});
    if (paramKeys.length > 0) {
      let rows = '';
      paramKeys.forEach((key) => {
        const p = parsedObj.parameters[key];
        
        let originBadge = '';
        if (isRequest && sourcedTargetsMap) {
          if (sourcedTargetsMap.has(p.xpath)) {
            const dep = sourcedTargetsMap.get(p.xpath);
            originBadge = `<span class="badge-origin sourced" title="Sourced from Response of API #${dep.sourceApiNo} (${dep.sourceKey})">🔗 API #${dep.sourceApiNo} (${escapeHtml(dep.sourceKey)})</span>`;
          } else {
            originBadge = `<span class="badge-origin input" title="Direct user input or static constant">✍️ User Input</span>`;
          }
        }

        rows += `
          <tr>
            <td style="font-weight: 600; color: #60a5fa;">${escapeHtml(p.id)}</td>
            <td style="color: #34d399;">${escapeHtml(p.value)}</td>
            ${isRequest ? `<td>${originBadge}</td>` : ''}
            <td style="color: var(--text-faint);">${escapeHtml(p.xpath)}</td>
            <td style="text-align: right;">
              <button class="copy-btn" title="Copy XPath" data-copy-text="${escapeAttr(p.xpath)}">📋</button>
            </td>
          </tr>
        `;
      });

      html += `
        <div class="structured-section">
          <div class="structured-header">
            <span>Parameters (${paramKeys.length})</span>
          </div>
          <div class="data-table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Parameter ID</th>
                  <th>Value</th>
                  ${isRequest ? `<th>Data Origin</th>` : ''}
                  <th>XPath</th>
                  <th style="width: 25px;"></th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>
      `;
    }

    const datasetKeys = Object.keys(parsedObj.datasets || {});
    if (datasetKeys.length > 0) {
      datasetKeys.forEach((dsId) => {
        const ds = parsedObj.datasets[dsId];
        const cols = ds.columns || [];
        const rows = ds.rows || [];

        let ths = `<th>#</th>`;
        cols.forEach((col) => {
          ths += `<th>${escapeHtml(col.id)}</th>`;
        });

        let trs = '';
        rows.forEach((row, rIdx) => {
          const rowNum = rIdx + 1;
          let tds = `<td style="color: var(--text-faint);">${rowNum}</td>`;
          cols.forEach((col) => {
            const cellVal = row[col.id] || '';
            const cellXPath = `/Root/Dataset[@id='${dsId}']/Rows/Row[${rowNum}]/Col[@id='${col.id}']`;
            
            let cellStyle = '';
            let originIcon = '';
            if (isRequest && sourcedTargetsMap && sourcedTargetsMap.has(cellXPath)) {
              cellStyle = 'color: #c084fc; font-weight: 600;';
              originIcon = ' <span title="Sourced from prior API response" style="font-size: 10px;">🔗</span>';
            }

            tds += `<td style="${cellStyle}">${escapeHtml(cellVal)}${originIcon}</td>`;
          });
          trs += `<tr>${tds}</tr>`;
        });

        if (rows.length === 0) {
          trs = `<tr><td colspan="${cols.length + 1}" style="text-align: center; color: var(--text-faint);">0 rows</td></tr>`;
        }

        html += `
          <div class="structured-section" style="margin-top: 8px;">
            <div class="structured-header">
              <span>Dataset: <strong style="color: #c084fc;">${escapeHtml(dsId)}</strong> (${rows.length} rows, ${cols.length} cols)</span>
            </div>
            <div class="data-table-wrapper">
              <table class="data-table">
                <thead><tr>${ths}</tr></thead>
                <tbody>${trs}</tbody>
              </table>
            </div>
          </div>
        `;
      });
    }

    return html;
  }

  function formatAndHighlightXml(xml) {
    if (!xml || typeof xml !== 'string') return '<span style="color: var(--text-faint);">(empty)</span>';
    const trimmed = xml.trim();
    if (!trimmed.startsWith('<')) return escapeHtml(trimmed);

    try {
      let formatted = '';
      const reg = /(>)(<)(\/*)/g;
      const cleanXml = trimmed.replace(reg, '$1\r\n$2$3');
      let pad = 0;

      const lines = cleanXml.split('\r\n');
      lines.forEach((node) => {
        let indent = 0;
        if (node.match(/.+<\/\w[^>]*>$/)) {
          indent = 0;
        } else if (node.match(/^<\/\w/)) {
          if (pad !== 0) pad -= 1;
        } else if (node.match(/^<\w[^>]*[^\/]>.*$/)) {
          indent = 1;
        } else {
          indent = 0;
        }

        let padding = '';
        for (let i = 0; i < pad; i++) {
          padding += '  ';
        }
        formatted += padding + node + '\n';
        pad += indent;
      });

      const escaped = escapeHtml(formatted.trim());
      const highlighted = escaped
        .replace(/(&lt;\/?)([\w:-]+)/g, '$1<span class="xml-tag">$2</span>')
        .replace(/([\w:-]+)(=)(&quot;.*?&quot;)/g, '<span class="xml-attr-name">$1</span>$2<span class="xml-attr-val">$3</span>')
        .replace(/(&gt;)([^&<\n]+)(&lt;)/g, '$1<span class="xml-text">$2</span>$3');

      return highlighted;
    } catch (e) {
      return escapeHtml(trimmed);
    }
  }
  // ========================================================
  // RENDER 2: High-Performance Paged Table Matrix View
  // ========================================================
  function renderActiveTableView() {
    matrixTable.innerHTML = '';
    const filteredApis = getFilteredApis();

    if (activeTableTab === 'matrix') {
      renderDependenciesMatrixTable(filteredApis);
    } else if (activeTableTab === 'summary') {
      renderApisSummaryTable(filteredApis);
    } else if (activeTableTab === 'payloads') {
      renderPayloadsOrResponsesTable(filteredApis, 'request');
    } else if (activeTableTab === 'responses') {
      renderPayloadsOrResponsesTable(filteredApis, 'response');
    }
  }

  function updateTablePaginationBar(totalItems) {
    if (totalItems === 0) {
      tablePaginationInfo.textContent = 'Showing 0-0 of 0';
      pageCurrentDisplay.textContent = 'Page 0 / 0';
      btnPrevTablePage.disabled = true;
      btnNextTablePage.disabled = true;
      return;
    }

    const totalPages = Math.ceil(totalItems / tablePageSize) || 1;
    if (tableCurrentPage > totalPages) tableCurrentPage = totalPages;
    if (tableCurrentPage < 1) tableCurrentPage = 1;

    const startIdx = (tableCurrentPage - 1) * tablePageSize + 1;
    const endIdx = Math.min(tableCurrentPage * tablePageSize, totalItems);

    tablePaginationInfo.textContent = `Showing ${startIdx}-${endIdx} of ${totalItems}`;
    pageCurrentDisplay.textContent = `Page ${tableCurrentPage} / ${totalPages}`;

    btnPrevTablePage.disabled = tableCurrentPage <= 1;
    btnNextTablePage.disabled = tableCurrentPage >= totalPages;
  }

  function renderDependenciesMatrixTable(apis) {
    const allDeps = [];
    apis.forEach((api) => {
      if (api.dependencies && api.dependencies.length > 0) {
        api.dependencies.forEach((d) => allDeps.push(d));
      }
    });

    const totalItems = allDeps.length;
    updateTablePaginationBar(totalItems);

    if (totalItems === 0) {
      matrixTable.innerHTML = `
        <tbody>
          <tr>
            <td colspan="8" style="padding: 40px; text-align: center; color: var(--text-muted);">
              No dependencies found matching current filters.
            </td>
          </tr>
        </tbody>
      `;
      return;
    }

    const pagedDeps = allDeps.slice((tableCurrentPage - 1) * tablePageSize, tableCurrentPage * tablePageSize);

    let thead = `
      <thead>
        <tr>
          <th style="width: 40px;">#</th>
          <th>Target API</th>
          <th>Target Field</th>
          <th>Target XPath</th>
          <th>Matched Value</th>
          <th>Source API</th>
          <th>Source Field</th>
          <th>Source XPath</th>
        </tr>
      </thead>
    `;

    let tbody = '<tbody>';
    pagedDeps.forEach((dep, idx) => {
      const globalIdx = (tableCurrentPage - 1) * tablePageSize + idx + 1;
      let targetPath = dep.targetUrl;
      let sourcePath = dep.sourceApiUrl;
      try {
        targetPath = new URL(dep.targetUrl).pathname;
        sourcePath = new URL(dep.sourceApiUrl).pathname;
      } catch (e) {}

      tbody += `
        <tr>
          <td style="color: var(--text-faint);">${globalIdx}</td>
          <td>
            <span style="color: #60a5fa; font-weight: 600;">#${dep.targetApiNo} ${dep.targetMethod}</span>
            <span style="color: var(--text-main);" title="${escapeHtml(dep.targetUrl)}">${escapeHtml(targetPath)}</span>
          </td>
          <td style="font-weight: 600; color: #93c5fd;">${escapeHtml(dep.targetKey)}</td>
          <td style="color: #38bdf8; cursor: pointer;" title="Click to copy XPath" data-copy-text="${escapeAttr(dep.targetLocation)}">
            ${escapeHtml(dep.targetLocation)} 📋
          </td>
          <td>
            <span class="dep-val-pill" style="cursor: pointer;" title="Click to copy value" data-copy-text="${escapeAttr(dep.targetValue)}">
              "${escapeHtml(dep.targetValue)}" 📋
            </span>
          </td>
          <td>
            <span style="color: #facc15; font-weight: 600;">${dep.sourceMethod}</span>
            <span style="color: var(--text-muted);" title="${escapeHtml(dep.sourceApiUrl)}">${escapeHtml(sourcePath)}</span>
          </td>
          <td style="color: #c084fc;">${escapeHtml(dep.sourceKey)} (${dep.sourceType})</td>
          <td style="color: #c084fc; cursor: pointer;" title="Click to copy XPath" data-copy-text="${escapeAttr(dep.sourceXPath)}">
            ${escapeHtml(dep.sourceXPath)} 📋
          </td>
        </tr>
      `;
    });
    tbody += '</tbody>';

    matrixTable.innerHTML = thead + tbody;

    matrixTable.querySelectorAll('[data-copy-text]').forEach((el) => {
      el.addEventListener('click', () => {
        copyToClipboard(el.getAttribute('data-copy-text'));
      });
    });
  }

  function renderApisSummaryTable(apis) {
    const totalItems = apis.length;
    updateTablePaginationBar(totalItems);

    if (totalItems === 0) {
      matrixTable.innerHTML = `
        <tbody>
          <tr>
            <td colspan="9" style="padding: 40px; text-align: center; color: var(--text-muted);">
              No API requests matching current filter.
            </td>
          </tr>
        </tbody>
      `;
      return;
    }

    const pagedApis = apis.slice((tableCurrentPage - 1) * tablePageSize, tableCurrentPage * tablePageSize);

    let thead = `
      <thead>
        <tr>
          <th style="width: 40px;">#</th>
          <th>Time</th>
          <th>Method</th>
          <th>Status</th>
          <th>Duration</th>
          <th>URL</th>
          <th>⚡ Dependencies</th>
          <th>Req Datasets</th>
          <th>Res Datasets</th>
        </tr>
      </thead>
    `;

    let tbody = '<tbody>';
    pagedApis.forEach((api) => {
      const timeStr = new Date(api.timestamp).toLocaleTimeString();
      const depCount = (api.dependencies || []).length;
      const isSuccess = api.status >= 200 && api.status < 300;
      const statusColor = isSuccess ? '#34d399' : '#fb7185';

      const reqDsCount = api.parsedRequest ? Object.keys(api.parsedRequest.datasets || {}).length : 0;
      const resDsCount = api.parsedResponse ? Object.keys(api.parsedResponse.datasets || {}).length : 0;

      tbody += `
        <tr>
          <td style="color: var(--text-faint);">${api.index}</td>
          <td style="color: var(--text-muted);">${timeStr}</td>
          <td style="font-weight: 700; color: ${api.method === 'POST' ? '#34d399' : '#60a5fa'};">${api.method}</td>
          <td style="font-weight: 600; color: ${statusColor};">${api.status || 'ERR'}</td>
          <td style="color: var(--text-faint);">${api.durationMs || 0}ms</td>
          <td style="color: var(--text-main); max-width: 250px; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(api.url)}">
            ${escapeHtml(api.url)}
          </td>
          <td>
            ${
              depCount > 0
                ? `<span style="background: rgba(139, 92, 246, 0.2); color: #c084fc; padding: 2px 6px; border-radius: 4px; font-weight: 600;">⚡ ${depCount}</span>`
                : '<span style="color: var(--text-faint);">0</span>'
            }
          </td>
          <td style="color: var(--text-muted);">${reqDsCount}</td>
          <td style="color: var(--text-muted);">${resDsCount}</td>
        </tr>
      `;
    });
    tbody += '</tbody>';

    matrixTable.innerHTML = thead + tbody;
  }

  function extractXmlFlatItems(apis, type) {
    const list = [];
    apis.forEach((api) => {
      const parsed = type === 'request' ? api.parsedRequest : api.parsedResponse;
      if (!parsed || !parsed.flatItems) return;
      parsed.flatItems.forEach((item) => {
        let isSourced = false;
        let sourceDep = null;
        if (type === 'request' && api.sourcedTargetsMap && api.sourcedTargetsMap.has(item.xpath)) {
          isSourced = true;
          sourceDep = api.sourcedTargetsMap.get(item.xpath);
        }

        list.push({
          apiIndex: api.index,
          method: api.method,
          url: api.url,
          category: item.sourceType,
          datasetId: item.datasetId || '-',
          rowIndex: item.rowIndex ? `#${item.rowIndex}` : '-',
          fieldName: item.key,
          value: item.value,
          xpath: item.xpath,
          isSourced: isSourced,
          sourceDep: sourceDep
        });
      });
    });
    return list;
  }

  function renderPayloadsOrResponsesTable(apis, type) {
    let allItems = extractXmlFlatItems(apis, type);
    const label = type === 'request' ? 'Payload (Request)' : 'Response';

    // Filter by user_inputs if active
    if (activeFilter === 'user_inputs' && type === 'request') {
      allItems = allItems.filter((i) => !i.isSourced);
    } else if (activeFilter === 'deps' && type === 'request') {
      allItems = allItems.filter((i) => i.isSourced);
    }

    const totalItems = allItems.length;
    updateTablePaginationBar(totalItems);

    if (totalItems === 0) {
      matrixTable.innerHTML = `
        <tbody>
          <tr>
            <td colspan="8" style="padding: 40px; text-align: center; color: var(--text-muted);">
              No Nexacro parameters or datasets found in ${label} matching filters.
            </td>
          </tr>
        </tbody>
      `;
      return;
    }

    const pagedItems = allItems.slice((tableCurrentPage - 1) * tablePageSize, tableCurrentPage * tablePageSize);
    const isRequest = type === 'request';

    let thead = `
      <thead>
        <tr>
          <th style="width: 40px;">#</th>
          <th>API</th>
          <th>Category / Dataset</th>
          <th>Row</th>
          <th>Field Name</th>
          <th>Value</th>
          ${isRequest ? `<th>Data Origin (Nguồn gốc)</th>` : ''}
          <th>XPath</th>
        </tr>
      </thead>
    `;

    let tbody = '<tbody>';
    pagedItems.forEach((item, idx) => {
      const globalIdx = (tableCurrentPage - 1) * tablePageSize + idx + 1;
      let pathOnly = item.url;
      try {
        pathOnly = new URL(item.url).pathname;
      } catch (e) {}

      const catBadge = item.category === 'Parameter'
        ? `<span style="color: #60a5fa; font-weight: 600;">Parameter</span>`
        : `<span style="color: #c084fc; font-weight: 600;">Dataset: ${escapeHtml(item.datasetId)}</span>`;

      let originBadge = '';
      if (isRequest) {
        if (item.isSourced && item.sourceDep) {
          originBadge = `<span class="badge-origin sourced" title="Sourced from Response of API #${item.sourceDep.sourceApiNo} (${item.sourceDep.sourceKey})">🔗 API #${item.sourceDep.sourceApiNo} (${escapeHtml(item.sourceDep.sourceKey)})</span>`;
        } else {
          originBadge = `<span class="badge-origin input" title="Direct input by user or static constant">✍️ User Input</span>`;
        }
      }

      tbody += `
        <tr>
          <td style="color: var(--text-faint);">${globalIdx}</td>
          <td>
            <span style="color: #38bdf8; font-weight: 600;">#${item.apiIndex} ${item.method}</span>
            <span style="color: var(--text-main); margin-left: 4px;" title="${escapeHtml(item.url)}">${escapeHtml(pathOnly)}</span>
          </td>
          <td>${catBadge}</td>
          <td style="color: var(--text-muted);">${item.rowIndex}</td>
          <td style="font-weight: 600; color: #93c5fd;">${escapeHtml(item.fieldName)}</td>
          <td>
            <span class="dep-val-pill" style="cursor: pointer;" title="Click to copy value" data-copy-text="${escapeAttr(item.value)}">
              "${escapeHtml(item.value)}" 📋
            </span>
          </td>
          ${isRequest ? `<td>${originBadge}</td>` : ''}
          <td style="color: #38bdf8; cursor: pointer;" title="Click to copy XPath" data-copy-text="${escapeAttr(item.xpath)}">
            ${escapeHtml(item.xpath)} 📋
          </td>
        </tr>
      `;
    });
    tbody += '</tbody>';

    matrixTable.innerHTML = thead + tbody;

    matrixTable.querySelectorAll('[data-copy-text]').forEach((el) => {
      el.addEventListener('click', () => {
        copyToClipboard(el.getAttribute('data-copy-text'));
      });
    });
  }
  // ========================================================
  // EXPORT FUNCTIONS: CSV & JSON (Unpaginated Full Export)
  // ========================================================
  function escapeCsvCell(val) {
    if (val === null || val === undefined) return '""';
    const str = String(val).replace(/"/g, '""');
    return `"${str}"`;
  }

  function createCsvContent(headers, rows) {
    const headerLine = headers.map(escapeCsvCell).join(',');
    const dataLines = rows.map((row) => row.map(escapeCsvCell).join(','));
    return '\uFEFF' + [headerLine, ...dataLines].join('\r\n');
  }

  function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast(`Exported ${filename}`);
  }

  function handleExportCsvDependencies() {
    if (computedLogs.length === 0) {
      alert('No data available to export.');
      return;
    }

    const headers = [
      'Index',
      'Target_API_No',
      'Target_Method',
      'Target_URL',
      'Target_Field',
      'Target_XPath',
      'Matched_Value',
      'Source_API_ID',
      'Source_Method',
      'Source_URL',
      'Source_Field',
      'Source_XPath',
      'Source_Type'
    ];

    const rows = [];
    let count = 0;

    computedLogs.forEach((api) => {
      (api.dependencies || []).forEach((d) => {
        count++;
        rows.push([
          count,
          api.index,
          api.method,
          api.url,
          d.targetKey,
          d.targetLocation,
          d.targetValue,
          d.sourceApiId,
          d.sourceMethod,
          d.sourceApiUrl,
          d.sourceKey,
          d.sourceXPath,
          d.sourceType
        ]);
      });
    });

    if (rows.length === 0) {
      alert('No cross-API dependencies found yet to export.');
      return;
    }

    const csvData = createCsvContent(headers, rows);
    downloadFile(csvData, `nexacro_dependencies_matrix_${Date.now()}.csv`, 'text/csv;charset=utf-8;');
  }

  function handleExportCsvApis() {
    if (computedLogs.length === 0) {
      alert('No API records captured yet.');
      return;
    }

    const headers = [
      'No',
      'Timestamp',
      'Formatted_Time',
      'Client_Type',
      'Method',
      'Status',
      'Duration_ms',
      'URL',
      'Dependencies_Count',
      'Req_Params_Count',
      'Req_Datasets_Count',
      'Res_Params_Count',
      'Res_Datasets_Count'
    ];

    const rows = computedLogs.map((api) => {
      const reqParamsCount = api.parsedRequest ? Object.keys(api.parsedRequest.parameters || {}).length : 0;
      const reqDatasetsCount = api.parsedRequest ? Object.keys(api.parsedRequest.datasets || {}).length : 0;
      const resParamsCount = api.parsedResponse ? Object.keys(api.parsedResponse.parameters || {}).length : 0;
      const resDatasetsCount = api.parsedResponse ? Object.keys(api.parsedResponse.datasets || {}).length : 0;

      return [
        api.index,
        api.timestamp,
        new Date(api.timestamp).toISOString(),
        api.clientType,
        api.method,
        api.status,
        api.durationMs || 0,
        api.url,
        (api.dependencies || []).length,
        reqParamsCount,
        reqDatasetsCount,
        resParamsCount,
        resDatasetsCount
      ];
    });

    const csvData = createCsvContent(headers, rows);
    downloadFile(csvData, `nexacro_apis_summary_${Date.now()}.csv`, 'text/csv;charset=utf-8;');
  }

  function handleExportCsvPayloads() {
    const items = extractXmlFlatItems(computedLogs, 'request');
    if (items.length === 0) {
      alert('No Nexacro parameters or datasets found in request payloads.');
      return;
    }

    const headers = [
      'Index',
      'API_No',
      'Method',
      'URL',
      'Category',
      'Dataset_ID',
      'Row_Index',
      'Field_Name',
      'Value',
      'Data_Origin',
      'Source_API_No',
      'Source_Field',
      'Source_XPath',
      'XPath'
    ];

    const rows = items.map((item, idx) => [
      idx + 1,
      item.apiIndex,
      item.method,
      item.url,
      item.category,
      item.datasetId,
      item.rowIndex,
      item.fieldName,
      item.value,
      item.isSourced ? 'Sourced from Prior Response' : 'User Input',
      item.sourceDep ? item.sourceDep.sourceApiNo : '-',
      item.sourceDep ? item.sourceDep.sourceKey : '-',
      item.sourceDep ? item.sourceDep.sourceXPath : '-',
      item.xpath
    ]);

    const csvData = createCsvContent(headers, rows);
    downloadFile(csvData, `nexacro_payloads_table_${Date.now()}.csv`, 'text/csv;charset=utf-8;');
  }

  function handleExportCsvResponses() {
    const items = extractXmlFlatItems(computedLogs, 'response');
    if (items.length === 0) {
      alert('No Nexacro parameters or datasets found in responses.');
      return;
    }

    const headers = [
      'Index',
      'API_No',
      'Method',
      'URL',
      'Category',
      'Dataset_ID',
      'Row_Index',
      'Field_Name',
      'Value',
      'XPath'
    ];

    const rows = items.map((item, idx) => [
      idx + 1,
      item.apiIndex,
      item.method,
      item.url,
      item.category,
      item.datasetId,
      item.rowIndex,
      item.fieldName,
      item.value,
      item.xpath
    ]);

    const csvData = createCsvContent(headers, rows);
    downloadFile(csvData, `nexacro_responses_table_${Date.now()}.csv`, 'text/csv;charset=utf-8;');
  }

  function handleExportSingleApiCsv(apiIndex, type) {
    const api = computedLogs.find((a) => a.index === apiIndex);
    if (!api) return;

    const parsed = type === 'request' ? api.parsedRequest : api.parsedResponse;
    if (!parsed || !parsed.flatItems || parsed.flatItems.length === 0) {
      alert(`No parsed Nexacro data found for this ${type}.`);
      return;
    }

    const isRequest = type === 'request';
    const headers = isRequest
      ? ['Index', 'API_No', 'Method', 'URL', 'Category', 'Dataset_ID', 'Row_Index', 'Field_Name', 'Value', 'Data_Origin', 'Source_Origin', 'XPath']
      : ['Index', 'API_No', 'Method', 'URL', 'Category', 'Dataset_ID', 'Row_Index', 'Field_Name', 'Value', 'XPath'];

    const rows = parsed.flatItems.map((item, idx) => {
      if (isRequest) {
        let isSourced = false;
        let sourceDetail = '-';
        if (api.sourcedTargetsMap && api.sourcedTargetsMap.has(item.xpath)) {
          isSourced = true;
          const d = api.sourcedTargetsMap.get(item.xpath);
          sourceDetail = `API #${d.sourceApiNo} (${d.sourceKey})`;
        }
        return [
          idx + 1,
          api.index,
          api.method,
          api.url,
          item.sourceType,
          item.datasetId || '-',
          item.rowIndex ? `#${item.rowIndex}` : '-',
          item.key,
          item.value,
          isSourced ? 'Sourced from Prior Response' : 'User Input',
          sourceDetail,
          item.xpath
        ];
      } else {
        return [
          idx + 1,
          api.index,
          api.method,
          api.url,
          item.sourceType,
          item.datasetId || '-',
          item.rowIndex ? `#${item.rowIndex}` : '-',
          item.key,
          item.value,
          item.xpath
        ];
      }
    });

    const csvData = createCsvContent(headers, rows);
    downloadFile(csvData, `api_${api.index}_${type}_table_${Date.now()}.csv`, 'text/csv;charset=utf-8;');
  }

  function handleExportJSON() {
    if (computedLogs.length === 0) {
      alert('No API records captured yet.');
      return;
    }

    const exportPayload = {
      exportedAt: new Date().toISOString(),
      generator: 'EMS Nexacro XML Interceptor & Dependency Engine',
      totalRequests: computedLogs.length,
      chain: computedLogs.map((item) => ({
        id: item.id,
        index: item.index,
        timestamp: item.timestamp,
        durationMs: item.durationMs,
        clientType: item.clientType,
        method: item.method,
        url: item.url,
        status: item.status,
        statusText: item.statusText,
        requestHeaders: item.requestHeaders,
        requestBodyRaw: item.requestBody,
        requestParsed: item.parsedRequest,
        responseHeaders: item.responseHeaders,
        responseBodyRaw: item.responseBody,
        responseParsed: item.parsedResponse,
        dependencies: item.dependencies || []
      }))
    };

    const jsonStr = JSON.stringify(exportPayload, null, 2);
    downloadFile(jsonStr, `nexacro_api_chain_${Date.now()}.json`, 'application/json;charset=utf-8;');
  }

  function handleClearLogs() {
    if (!confirm('Clear all captured Nexacro API logs?')) return;
    chrome.storage.local.set({ [STORAGE_KEY]: [] }, () => {
      currentLogs = [];
      computedLogs = [];
      chrome.action.setBadgeText({ text: '' });
      updateHeaderCounts();
      if (currentViewMode === 'cards') {
        renderList();
      } else {
        renderActiveTableView();
      }
      showToast('Logs cleared');
    });
  }

  function copyToClipboard(text) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      showToast('Copied to clipboard!');
    }).catch(() => {
      showToast('Failed to copy');
    });
  }

  function showToast(msg) {
    if (toastTimer) clearTimeout(toastTimer);
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    toastTimer = setTimeout(() => {
      toastEl.classList.remove('show');
    }, 1800);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function escapeAttr(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
})();