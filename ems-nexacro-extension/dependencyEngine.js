/**
 * dependencyEngine.js - Core Nexacro XML Parser & Dependency Engine
 * Provides XML architecture extraction, exact XPath generation, and cross-API data lineage resolution.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.NexacroDependencyEngine = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /**
   * Safely parses an XML string with DOMParser and checks for XML parsing errors.
   * @param {string} xmlString
   * @returns {Document|null}
   */
  function parseXmlDoc(xmlString) {
    if (!xmlString || typeof xmlString !== 'string') return null;
    const trimmed = xmlString.trim();
    if (!trimmed.startsWith('<')) return null;

    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(trimmed, 'application/xml');
      const parserError = doc.getElementsByTagName('parsererror');
      if (parserError && parserError.length > 0) {
        return null;
      }
      return doc;
    } catch (e) {
      return null;
    }
  }

  /**
   * Parses raw Nexacro XML strings into structured Parameters, Datasets, and flattened key-values with XPaths.
   *
   * Nexacro Schema Supported:
   * <Root>
   *   <Parameters>
   *     <Parameter id="KEY">VALUE</Parameter>
   *   </Parameters>
   *   <Dataset id="ds_name">
   *     <ColumnInfo>
   *       <Column id="COL_ID" type="STRING" size="256"/>
   *     </ColumnInfo>
   *     <Rows>
   *       <Row>
   *         <Col id="COL_ID">VALUE</Col> <!-- or index positional without id -->
   *       </Row>
   *     </Rows>
   *   </Dataset>
   * </Root>
   *
   * @param {string} xmlString
   * @returns {Object} Structured metadata and flat element list
   */
  function parseNexacroXML(xmlString) {
    const result = {
      parameters: {},
      datasets: {},
      flatItems: [], // Flat list used for fast dependency cross-matching
      isValidNexacro: false
    };

    const doc = parseXmlDoc(xmlString);
    if (!doc) return result;

    const rootElement = doc.documentElement;
    const rootTagName = rootElement.tagName || 'Root';

    // 1. Extract <Parameters>
    const parametersNodes = doc.getElementsByTagName('Parameters');
    for (let pIdx = 0; pIdx < parametersNodes.length; pIdx++) {
      const paramNode = parametersNodes[pIdx];
      const paramChildren = paramNode.getElementsByTagName('Parameter');

      for (let i = 0; i < paramChildren.length; i++) {
        const item = paramChildren[i];
        const id = item.getAttribute('id') || `param_${i + 1}`;
        const val = (item.textContent || '').trim();
        const xpath = `/${rootTagName}/Parameters/Parameter[@id='${id}']`;

        result.parameters[id] = {
          id: id,
          value: val,
          xpath: xpath,
          type: 'Parameter'
        };

        result.flatItems.push({
          sourceType: 'Parameter',
          key: id,
          value: val,
          xpath: xpath,
          datasetId: null,
          rowIndex: null
        });
        result.isValidNexacro = true;
      }
    }

    // 2. Extract <Dataset> elements
    const datasetNodes = doc.getElementsByTagName('Dataset');
    for (let d = 0; d < datasetNodes.length; d++) {
      const dsNode = datasetNodes[d];
      const datasetId = dsNode.getAttribute('id') || `ds_${d + 1}`;

      const datasetObj = {
        id: datasetId,
        columns: [],
        rows: []
      };

      // 2a. Map ColumnInfo
      const columnInfoNodes = dsNode.getElementsByTagName('ColumnInfo');
      if (columnInfoNodes.length > 0) {
        const colElements = columnInfoNodes[0].getElementsByTagName('Column');
        for (let c = 0; c < colElements.length; c++) {
          const colEl = colElements[c];
          datasetObj.columns.push({
            index: c,
            id: colEl.getAttribute('id') || `col_${c}`,
            type: colEl.getAttribute('type') || 'STRING',
            size: colEl.getAttribute('size') || '256'
          });
        }
      }

      // 2b. Map Rows & Cols
      const rowsContainers = dsNode.getElementsByTagName('Rows');
      if (rowsContainers.length > 0) {
        // Select direct children <Row> to avoid nested sub-elements
        const rowNodes = Array.from(rowsContainers[0].children).filter(
          (el) => el.tagName === 'Row' || el.tagName === 'OrgRow'
        );

        for (let r = 0; r < rowNodes.length; r++) {
          const rowEl = rowNodes[r];
          const rowIndex = r + 1; // 1-indexed for XPath
          const rowData = {};
          const colNodes = Array.from(rowEl.children).filter((el) => el.tagName === 'Col');

          colNodes.forEach((colEl, cIdx) => {
            let colId = colEl.getAttribute('id');
            // If <Col> has no explicit id, correlate by position against ColumnInfo
            if (!colId && datasetObj.columns[cIdx]) {
              colId = datasetObj.columns[cIdx].id;
            }
            if (!colId) {
              colId = `col_${cIdx + 1}`;
            }

            const cellVal = (colEl.textContent || '').trim();
            const colXPath = `/${rootTagName}/Dataset[@id='${datasetId}']/Rows/Row[${rowIndex}]/Col[@id='${colId}']`;

            rowData[colId] = cellVal;

            result.flatItems.push({
              sourceType: 'Dataset',
              key: colId,
              value: cellVal,
              xpath: colXPath,
              datasetId: datasetId,
              rowIndex: rowIndex
            });
            result.isValidNexacro = true;
          });

          datasetObj.rows.push(rowData);
        }
      }

      result.datasets[datasetId] = datasetObj;
    }

    return result;
  }

  /**
   * Tests whether a value is meaningful for correlation (excludes trivial values like 0, null, true, Y, N).
   * @param {string} val
   * @returns {boolean}
   */
  function isMeaningfulValue(val) {
    if (!val || typeof val !== 'string') return false;
    const clean = val.trim();
    if (clean.length <= 2) return false;

    // Common system codes to exclude from false-positive dependency mappings
    const trivialList = new Set([
      'null',
      'undefined',
      'true',
      'false',
      'success',
      'fail',
      'error',
      '0000',
      'select',
      'insert',
      'update',
      'delete',
      'utf-8'
    ]);
    if (trivialList.has(clean.toLowerCase())) return false;
    return true;
  }

  /**
   * Compares the target API payload against past API responses to identify lineage.
   *
   * @param {string|Object} currentPayload - Raw XML string or parsed result of current API request
   * @param {Array<Object>} pastApisList - List of prior captured API items in chronological order
   * @returns {Array<Object>} Found dependencies
   */
  function findDependencies(currentPayload, pastApisList) {
    const dependencies = [];
    if (!currentPayload || !pastApisList || !Array.isArray(pastApisList) || pastApisList.length === 0) {
      return dependencies;
    }

    const currentParsed =
      typeof currentPayload === 'string'
        ? parseNexacroXML(currentPayload)
        : currentPayload;

    if (!currentParsed || !currentParsed.flatItems || currentParsed.flatItems.length === 0) {
      return dependencies;
    }

    // Pre-parse and index past API responses
    const indexedPastResponses = [];
    for (const priorApi of pastApisList) {
      if (!priorApi.responseBody) continue;
      const parsedResp = parseNexacroXML(priorApi.responseBody);
      if (parsedResp.flatItems && parsedResp.flatItems.length > 0) {
        indexedPastResponses.push({
          api: priorApi,
          flatItems: parsedResp.flatItems
        });
      }
    }

    // Compare each value in the current request payload against historical response values
    const seenMatches = new Set();

    for (const targetItem of currentParsed.flatItems) {
      const targetVal = targetItem.value;
      if (!isMeaningfulValue(targetVal)) continue;

      // Search prior responses (reverse order to prioritize most recent origin)
      for (let i = indexedPastResponses.length - 1; i >= 0; i--) {
        const candidate = indexedPastResponses[i];

        for (const sourceItem of candidate.flatItems) {
          if (sourceItem.value === targetVal) {
            const matchSignature = `${targetItem.xpath}->${candidate.api.id}:${sourceItem.xpath}`;
            if (seenMatches.has(matchSignature)) continue;
            seenMatches.add(matchSignature);

            dependencies.push({
              targetLocation: targetItem.xpath,
              targetKey: targetItem.key,
              targetValue: targetVal,
              sourceApiId: candidate.api.id,
              sourceApiNo: candidate.api.index || null,
              sourceApiUrl: candidate.api.url,
              sourceMethod: candidate.api.method,
              sourceType: sourceItem.sourceType,
              sourceKey: sourceItem.key,
              sourceDatasetId: sourceItem.datasetId || null,
              sourceXPath: sourceItem.xpath
            });

            // Found the latest upstream source for this target element
            break;
          }
        }
      }
    }

    return dependencies;
  }

  /**
   * Resolves the full upstream dependency chain (direct and transitive) for the given target API(s).
   *
   * @param {number|string|Array<number|string>} targetIdentifiers - Target API index(es) (1-based) or id(s)
   * @param {Array<Object>} allApis - List of all captured/computed APIs
   * @returns {Object} Lineage resolution summary
   */
  function resolveDependencyChain(targetIdentifiers, allApis) {
    if (!allApis || !Array.isArray(allApis) || allApis.length === 0) {
      return {
        targetApis: [],
        dependencyApis: [],
        chainApis: [],
        edges: [],
        stats: { totalTarget: 0, totalDependencies: 0, totalInChain: 0 }
      };
    }

    const rawTargets = Array.isArray(targetIdentifiers) ? targetIdentifiers : [targetIdentifiers];

    // Build lookup maps
    const apiById = new Map();
    const apiByIndex = new Map();

    allApis.forEach((api, idx) => {
      const idxNum = api.index !== undefined ? api.index : idx + 1;
      if (api.id) apiById.set(String(api.id), api);
      apiByIndex.set(idxNum, api);
      apiByIndex.set(String(idxNum), api);
    });

    function findApi(ident) {
      if (ident === null || ident === undefined) return null;
      if (typeof ident === 'object' && ident.index !== undefined) return ident;
      if (apiByIndex.has(ident)) return apiByIndex.get(ident);
      const str = String(ident);
      if (apiByIndex.has(str)) return apiByIndex.get(str);
      if (apiById.has(str)) return apiById.get(str);
      return null;
    }

    const resolvedTargetApis = [];
    const targetKeysSet = new Set();

    rawTargets.forEach((ident) => {
      const a = findApi(ident);
      if (a) {
        const key = a.id || a.index;
        if (!targetKeysSet.has(key)) {
          targetKeysSet.add(key);
          resolvedTargetApis.push(a);
        }
      }
    });

    const dependencyApisMap = new Map();
    const edges = [];
    const queue = [...resolvedTargetApis];
    const visited = new Set();

    resolvedTargetApis.forEach((a) => visited.add(a.id || a.index));

    while (queue.length > 0) {
      const current = queue.shift();
      const currentDeps = current.dependencies || [];

      for (const dep of currentDeps) {
        let srcApi = null;
        if (dep.sourceApiId && apiById.has(String(dep.sourceApiId))) {
          srcApi = apiById.get(String(dep.sourceApiId));
        } else if (dep.sourceApiNo && apiByIndex.has(dep.sourceApiNo)) {
          srcApi = apiByIndex.get(dep.sourceApiNo);
        }

        if (srcApi) {
          edges.push({
            targetIndex: current.index,
            targetMethod: current.method,
            targetUrl: current.url,
            targetKey: dep.targetKey,
            targetLocation: dep.targetLocation,
            targetValue: dep.targetValue,
            sourceIndex: srcApi.index,
            sourceMethod: srcApi.method,
            sourceUrl: srcApi.url,
            sourceKey: dep.sourceKey,
            sourceXPath: dep.sourceXPath,
            sourceType: dep.sourceType
          });

          const srcKey = srcApi.id || srcApi.index;
          if (!targetKeysSet.has(srcKey)) {
            dependencyApisMap.set(srcKey, srcApi);
          }

          if (!visited.has(srcKey)) {
            visited.add(srcKey);
            queue.push(srcApi);
          }
        }
      }
    }

    const dependencyApis = Array.from(dependencyApisMap.values()).sort(
      (a, b) => (a.index || 0) - (b.index || 0)
    );

    const allChainMap = new Map();
    resolvedTargetApis.forEach((a) => allChainMap.set(a.id || a.index, a));
    dependencyApis.forEach((a) => allChainMap.set(a.id || a.index, a));

    const chainApis = Array.from(allChainMap.values()).sort(
      (a, b) => (a.index || 0) - (b.index || 0)
    );

    return {
      targetApis: resolvedTargetApis,
      dependencyApis: dependencyApis,
      chainApis: chainApis,
      edges: edges,
      stats: {
        totalTarget: resolvedTargetApis.length,
        totalDependencies: dependencyApis.length,
        totalInChain: chainApis.length
      }
    };
  }

  return {
    parseXmlDoc: parseXmlDoc,
    parseNexacroXML: parseNexacroXML,
    findDependencies: findDependencies,
    resolveDependencyChain: resolveDependencyChain,
    isMeaningfulValue: isMeaningfulValue
  };
});