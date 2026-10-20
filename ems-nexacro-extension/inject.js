/**
 * inject.js - Page Context Interceptor
 * Overrides XHR and Fetch to capture raw Nexacro XML request and response payloads.
 */
(function () {
  'use strict';

  // Prevent double-injection
  if (window.__NEXACRO_INTERCEPTOR_INJECTED__) return;
  window.__NEXACRO_INTERCEPTOR_INJECTED__ = true;

  const MESSAGE_SOURCE = 'EMS_NEXACRO_INTERCEPTOR';

  /**
   * Helper to inspect if text content or headers represent Nexacro XML traffic.
   */
  function isNexacroOrXml(body, headers) {
    if (typeof headers === 'string' && /xml|nexacro/i.test(headers)) return true;
    if (typeof headers === 'object' && headers !== null) {
      for (const [k, v] of Object.entries(headers)) {
        if (/content-type/i.test(k) && /xml|nexacro/i.test(v)) return true;
      }
    }
    if (typeof body === 'string') {
      const trimmed = body.trim();
      return (
        trimmed.startsWith('<?xml') ||
        trimmed.includes('<Root') ||
        trimmed.includes('<Dataset') ||
        trimmed.includes('<Parameters')
      );
    }
    return false;
  }

  /**
   * Sends the intercepted network record to content.js via window.postMessage.
   */
  function emitCapturedTraffic(record) {
    try {
      window.postMessage(
        {
          source: MESSAGE_SOURCE,
          type: 'API_INTERCEPTED',
          data: record
        },
        '*'
      );
    } catch (err) {
      console.warn('[NexacroInterceptor] Failed to emit postMessage:', err);
    }
  }

  // ==========================================
  // 1. Monkey-Patch XMLHttpRequest
  // ==========================================
  const OriginalXHR = window.XMLHttpRequest;
  const originalOpen = OriginalXHR.prototype.open;
  const originalSetRequestHeader = OriginalXHR.prototype.setRequestHeader;
  const originalSend = OriginalXHR.prototype.send;

  OriginalXHR.prototype.open = function (method, url, async, user, password) {
    this._emsData = {
      id: 'xhr_' + Date.now() + '_' + Math.random().toString(36).substring(2, 8),
      method: method || 'GET',
      url: typeof url === 'string' ? url : (url ? url.toString() : ''),
      requestHeaders: {},
      startTime: Date.now()
    };
    return originalOpen.apply(this, arguments);
  };

  OriginalXHR.prototype.setRequestHeader = function (header, value) {
    if (this._emsData && this._emsData.requestHeaders) {
      this._emsData.requestHeaders[header] = value;
    }
    return originalSetRequestHeader.apply(this, arguments);
  };

  OriginalXHR.prototype.send = function (body) {
    if (!this._emsData) {
      return originalSend.apply(this, arguments);
    }

    const self = this;
    this._emsData.requestBody = typeof body === 'string' ? body : (body ? String(body) : '');

    const handleCompletion = function () {
      if (self.readyState === 4) {
        try {
          const responseHeaders = self.getAllResponseHeaders() || '';
          let responseText = '';
          try {
            responseText = self.responseText || '';
          } catch (e) {
            responseText = '';
          }

          const isReqXml = isNexacroOrXml(self._emsData.requestBody, self._emsData.requestHeaders);
          const isResXml = isNexacroOrXml(responseText, responseHeaders);

          // Only forward when request or response contains Nexacro XML
          if (isReqXml || isResXml) {
            const record = {
              id: self._emsData.id,
              clientType: 'XHR',
              method: self._emsData.method.toUpperCase(),
              url: self._emsData.url,
              requestHeaders: self._emsData.requestHeaders,
              requestBody: self._emsData.requestBody,
              status: self.status,
              statusText: self.statusText,
              responseHeaders: responseHeaders,
              responseBody: responseText,
              timestamp: self._emsData.startTime,
              durationMs: Date.now() - self._emsData.startTime
            };
            emitCapturedTraffic(record);
          }
        } catch (err) {
          console.error('[NexacroInterceptor] Error capturing XHR result:', err);
        }
      }
    };

    this.addEventListener('readystatechange', handleCompletion, false);
    return originalSend.apply(this, arguments);
  };

  // ==========================================
  // 2. Monkey-Patch window.fetch
  // ==========================================
  const originalFetch = window.fetch;
  window.fetch = async function (input, init) {
    const startTime = Date.now();
    const id = 'fetch_' + startTime + '_' + Math.random().toString(36).substring(2, 8);

    let url = '';
    let method = 'GET';
    let requestHeaders = {};
    let requestBody = '';

    try {
      if (typeof input === 'string') {
        url = input;
      } else if (input instanceof Request) {
        url = input.url;
        method = input.method;
      }

      if (init) {
        if (init.method) method = init.method;
        if (init.headers) {
          if (init.headers instanceof Headers) {
            init.headers.forEach((val, key) => {
              requestHeaders[key] = val;
            });
          } else if (Array.isArray(init.headers)) {
            init.headers.forEach(([k, v]) => {
              requestHeaders[k] = v;
            });
          } else if (typeof init.headers === 'object') {
            requestHeaders = { ...init.headers };
          }
        }
        if (init.body) {
          requestBody = typeof init.body === 'string' ? init.body : String(init.body);
        }
      }
    } catch (e) {
      console.warn('[NexacroInterceptor] Fetch pre-process error:', e);
    }

    try {
      const response = await originalFetch.apply(this, arguments);
      const clonedResponse = response.clone();

      clonedResponse.text().then((responseText) => {
        const resHeadersObj = {};
        if (response.headers && typeof response.headers.forEach === 'function') {
          response.headers.forEach((val, key) => {
            resHeadersObj[key] = val;
          });
        }

        const isReqXml = isNexacroOrXml(requestBody, requestHeaders);
        const isResXml = isNexacroOrXml(responseText, resHeadersObj);

        if (isReqXml || isResXml) {
          emitCapturedTraffic({
            id: id,
            clientType: 'FETCH',
            method: method.toUpperCase(),
            url: url,
            requestHeaders: requestHeaders,
            requestBody: requestBody,
            status: response.status,
            statusText: response.statusText,
            responseHeaders: JSON.stringify(resHeadersObj),
            responseBody: responseText,
            timestamp: startTime,
            durationMs: Date.now() - startTime
          });
        }
      }).catch(() => {
        // Body reading error ignored
      });

      return response;
    } catch (fetchError) {
      throw fetchError;
    }
  };

  console.info('[NexacroInterceptor] XHR and Fetch successfully hooked.');
})();