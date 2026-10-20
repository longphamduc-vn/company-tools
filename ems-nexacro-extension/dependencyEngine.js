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

  return {
    parseXmlDoc: parseXmlDoc,
    parseNexacroXML: parseNexacroXML,
    findDependencies: findDependencies,
    isMeaningfulValue: isMeaningfulValue
  };
});