"""
Drawing Service implementation for LG Display Vault.
Handles:
- Search Endpoint: POST http://fdm.lgdisplay.com:8008/
- Non-CAD Filter: Skip records where typeName == "CAD"
- Detail Page Scraper: GET /Windchill/extcore/jsp/lgdfdm/drawing/detailNonCAD.jsp
  Regex pattern: href=['"](http[s]?://[^'"]+viewContent/[^'"]+)['"]
- Binary Downloader: stream binary, verify visual payload, prefix custom_name, error recovery.
- Batch Download Orchestration.
"""

import json
import logging
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Callable

import requests
from bs4 import BeautifulSoup

from lgd_vault.config import (
    FDM_BASE_URL,
    FDM_SEARCH_URL,
    FDM_DETAIL_NONCAD_URL,
    DEFAULT_SITE,
    DEFAULT_FAB,
    DEFAULT_VERSION,
    DEFAULT_PAGE_START,
    DEFAULT_PAGE_END,
    DEFAULT_TIMEOUT_CONNECT,
    DEFAULT_TIMEOUT_READ,
    RASTER_EXTENSIONS,
    USER_AGENT,
)
from lgd_vault.exceptions import (
    VaultAutomationError,
    SSOConnectionRefusedError,
    AuthExpiredError,
    DrawingNotFoundError,
    CorruptPayloadError,
)
from lgd_vault.models import (
    DrawingItem,
    DrawingRecord,
    DownloadResult,
    BatchDownloadSummary,
)
from lgd_vault.sso_client import SSOClient

logger = logging.getLogger("lgd_vault.service")

# Regex patterns for viewContent
VIEW_CONTENT_REGEX = re.compile(r"""href=['"](http[s]?://[^'"]+viewContent/[^'"]+)['"]""", re.IGNORECASE)
VIEW_CONTENT_RELATIVE_REGEX = re.compile(r"""href=['"](/[^'"]*viewContent/[^'"]+)['"]""", re.IGNORECASE)
SRC_VIEW_CONTENT_REGEX = re.compile(r"""src=['"](http[s]?://[^'"]+viewContent/[^'"]+)['"]""", re.IGNORECASE)


class DrawingService:
    """Manages searching, scraping, filtering, and batch downloading drawings from LGD Vault."""

    def __init__(self, sso_client: Optional[SSOClient] = None):
        self.sso_client = sso_client or SSOClient()
        self._session: Optional[requests.Session] = None

    def get_session(self, force_refresh: bool = False) -> requests.Session:
        """Retrieves or refreshes an authenticated session."""
        if self._session is None or force_refresh:
            self._session = self.sso_client.get_authenticated_session(force_refresh=force_refresh)
        return self._session

    def invalidate_session(self) -> None:
        """Forces session reset and clears cached session file."""
        self._session = None
        self.sso_client.session_manager.clear_session()

    def search_drawings(
        self,
        qcode: str,
        site: str = DEFAULT_SITE,
        fab: str = DEFAULT_FAB,
        version: str = DEFAULT_VERSION,
        start: str = DEFAULT_PAGE_START,
        end: str = DEFAULT_PAGE_END,
    ) -> List[DrawingRecord]:
        """
        Executes search on FDM Vault (POST http://fdm.lgdisplay.com:8008/).
        Filters out 3D CAD records (typeName == 'CAD').
        Returns list of eligible visual drawing records.
        """
        session = self.get_session()
        payload = {
            "site": site,
            "fab": fab,
            "qcode": qcode,
            "version": version,
            "start": start,
            "end": end,
        }

        logger.info("Searching drawings for QCode '%s' at %s (site=%s, fab=%s)", qcode, FDM_SEARCH_URL, site, fab)

        try:
            resp = session.post(
                FDM_SEARCH_URL,
                data=payload,
                timeout=(DEFAULT_TIMEOUT_CONNECT, DEFAULT_TIMEOUT_READ),
                headers={"User-Agent": USER_AGENT},
            )
        except requests.RequestException as e:
            logger.error("Network error during FDM search for %s: %s", qcode, e)
            raise VaultAutomationError(f"Network error querying FDM Vault: {e}") from e

        # Check for authentication expiry
        if resp.status_code in (401, 403):
            logger.warning("FDM search returned HTTP %d - session expired", resp.status_code)
            raise AuthExpiredError(f"HTTP {resp.status_code} during FDM Search", code=f"HTTP_{resp.status_code}")

        # Check for HTML login redirection
        if self._is_html_login_page(resp.text, resp.headers.get("Content-Type", "")):
            logger.warning("FDM search returned HTML login page instead of search result")
            raise AuthExpiredError("FDM session expired - redirected to login page", code="HTTP_401")

        # Parse records from response (supports JSON or HTML table responses)
        records = self._parse_search_response(resp, qcode, fab)

        # Asset Filter Policy: Skip CAD
        visual_records = [r for r in records if not r.is_cad]
        logger.info(
            "Found %d total records for QCode '%s', %d non-CAD visual candidates",
            len(records),
            qcode,
            len(visual_records),
        )

        if not visual_records:
            raise DrawingNotFoundError(qcode)

        return visual_records

    def scrape_detail_page(self, record: DrawingRecord) -> str:
        """
        Scrapes direct viewContent URL from Windchill detail Non-CAD JSP.
        GET /Windchill/extcore/jsp/lgdfdm/drawing/detailNonCAD.jsp
        Params: drawingOid, fabOid, folderPath, lang=en
        """
        session = self.get_session()
        params = {
            "drawingOid": record.drawing_oid,
            "fabOid": record.fab_oid,
            "folderPath": record.folder_path,
            "lang": "en",
        }

        logger.debug("Scraping detail page %s with params %s", FDM_DETAIL_NONCAD_URL, params)

        try:
            resp = session.get(
                FDM_DETAIL_NONCAD_URL,
                params=params,
                timeout=(DEFAULT_TIMEOUT_CONNECT, DEFAULT_TIMEOUT_READ),
                headers={"User-Agent": USER_AGENT},
            )
        except requests.RequestException as e:
            logger.error("Error scraping detail page for OID %s: %s", record.drawing_oid, e)
            raise VaultAutomationError(f"Failed to fetch detailNonCAD.jsp: {e}") from e

        if resp.status_code in (401, 403):
            raise AuthExpiredError(f"HTTP {resp.status_code} scraping detail page")

        html_text = resp.text

        # 1. Primary Regex: Absolute href
        match = VIEW_CONTENT_REGEX.search(html_text)
        if match:
            url = match.group(1)
            logger.debug("Found viewContent absolute link: %s", url)
            return url

        # 2. Secondary Regex: Relative href
        rel_match = VIEW_CONTENT_RELATIVE_REGEX.search(html_text)
        if rel_match:
            rel_url = rel_match.group(1)
            full_url = urllib.parse.urljoin(FDM_BASE_URL, rel_url)
            logger.debug("Found viewContent relative link resolved to: %s", full_url)
            return full_url

        # 3. Fallback: <img src="...viewContent...">
        src_match = SRC_VIEW_CONTENT_REGEX.search(html_text)
        if src_match:
            return src_match.group(1)

        # 4. BeautifulSoup DOM parser fallback
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup.find_all(["a", "img", "iframe", "embed"]):
            src = tag.get("href") or tag.get("src")
            if src and "viewContent" in src:
                return urllib.parse.urljoin(FDM_BASE_URL, src)

        logger.warning("No viewContent link found in detail Non-CAD JSP for OID %s", record.drawing_oid)
        return ""

    def download_record_file(
        self,
        record: DrawingRecord,
        download_dir: str,
        custom_name: str = "",
        direct_url: Optional[str] = None,
    ) -> DownloadResult:
        """
        Downloads visual blueprint drawing binary stream to disk.
        Detects corrupt payload (HTML login page) and raises CorruptPayloadError.
        Applies custom_name prefix when provided.
        """
        url = direct_url or self.scrape_detail_page(record)
        if not url:
            return DownloadResult(
                qcode=record.qcode,
                custom_name=custom_name,
                status="Failed: Drawing Not Found",
                file_name="",
                local_path="",
                file_size_bytes=0,
            )

        session = self.get_session()
        logger.info("Downloading binary stream from: %s", url)

        try:
            resp = session.get(
                url,
                stream=True,
                timeout=(DEFAULT_TIMEOUT_CONNECT, DEFAULT_TIMEOUT_READ),
                headers={"User-Agent": USER_AGENT},
            )
        except requests.RequestException as e:
            logger.error("Download stream error: %s", e)
            raise VaultAutomationError(f"Download stream error: {e}") from e

        if resp.status_code in (401, 403):
            raise AuthExpiredError(f"HTTP {resp.status_code} during binary download")

        # Read initial chunk to check if payload is HTML login page
        first_chunk = b""
        chunks = []
        for chunk in resp.iter_content(chunk_size=4096):
            if chunk:
                if not first_chunk:
                    first_chunk = chunk
                chunks.append(chunk)

        content_type = resp.headers.get("Content-Type", "").lower()
        if self._is_html_content(first_chunk, content_type):
            logger.error("Corrupt payload detected: server returned HTML instead of image binary")
            raise CorruptPayloadError("Server returned HTML login/error page instead of binary stream.")

        # Determine target file name
        raw_filename = self._extract_filename(resp, record, url)
        sanitized_filename = self._sanitize_filename(raw_filename)

        if custom_name:
            final_filename = f"{self._sanitize_filename(custom_name)}_{sanitized_filename}"
        else:
            final_filename = sanitized_filename

        os.makedirs(download_dir, exist_ok=True)
        target_path = os.path.join(download_dir, final_filename)

        # Write chunks to disk
        total_bytes = 0
        with open(target_path, "wb") as f:
            for chunk in chunks:
                f.write(chunk)
                total_bytes += len(chunk)

        # Probe image dimensions if Pillow is available
        img_w, img_h = 0, 0
        try:
            from PIL import Image
            with Image.open(target_path) as im:
                img_w, img_h = im.size
        except Exception:
            pass

        logger.info("Successfully saved drawing: %s (%d bytes, %dx%d)", target_path, total_bytes, img_w, img_h)

        return DownloadResult(
            qcode=record.qcode,
            custom_name=custom_name,
            status="Success",
            file_name=final_filename,
            local_path=os.path.abspath(target_path),
            file_size_bytes=total_bytes,
            image_width=img_w,
            image_height=img_h,
        )

    def process_item(
        self,
        item: DrawingItem,
        download_dir: str,
        max_retries: int = 1,
    ) -> DownloadResult:
        """
        Executes search & download for a single item with error recovery:
        - HTTP_401/403 or CORRUPT_PAYLOAD -> invalidate session, re-auth, retry once.
        - DRAWING_NOT_FOUND -> return Failed: Drawing Not Found.
        """
        attempt = 0
        while attempt <= max_retries:
            try:
                # 1. Search drawings
                records = self.search_drawings(item.qcode)

                # 2. Pick primary visual record (first non-CAD record)
                primary_record = records[0]

                # 3. Download drawing
                result = self.download_record_file(
                    record=primary_record,
                    download_dir=download_dir,
                    custom_name=item.custom_name,
                )
                return result

            except DrawingNotFoundError as e:
                logger.info("Drawing not found for QCode %s: %s", item.qcode, e)
                return DownloadResult(
                    qcode=item.qcode,
                    custom_name=item.custom_name,
                    status="Failed: Drawing Not Found",
                    file_name="",
                    local_path="",
                    file_size_bytes=0,
                )

            except (AuthExpiredError, CorruptPayloadError) as e:
                attempt += 1
                logger.warning(
                    "Encountered %s (%s) for QCode %s. Attempt %d/%d to re-authenticate and retry.",
                    type(e).__name__,
                    e,
                    item.qcode,
                    attempt,
                    max_retries,
                )
                if attempt <= max_retries:
                    self.invalidate_session()
                    self.get_session(force_refresh=True)
                    continue
                else:
                    return DownloadResult(
                        qcode=item.qcode,
                        custom_name=item.custom_name,
                        status=f"Failed: {type(e).__name__}",
                        file_name="",
                        local_path="",
                        file_size_bytes=0,
                    )

            except Exception as e:
                logger.exception("Unexpected error processing QCode %s: %s", item.qcode, e)
                return DownloadResult(
                    qcode=item.qcode,
                    custom_name=item.custom_name,
                    status=f"Failed: {str(e)}",
                    file_name="",
                    local_path="",
                    file_size_bytes=0,
                )

        return DownloadResult(
            qcode=item.qcode,
            custom_name=item.custom_name,
            status="Failed: Max retries exceeded",
        )

    def execute_batch(
        self,
        items: List[DrawingItem],
        download_dir: str,
        progress_callback: Optional[Callable[[int, int, DownloadResult], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> BatchDownloadSummary:
        """
        Executes batch downloading for multiple items with progress callback support.
        """
        start_time = time.time()
        total_requested = len(items)
        if total_requested == 0:
            return BatchDownloadSummary(
                total_requested=0,
                total_downloaded=0,
                total_failed=0,
                results=[],
                elapsed_seconds=0.0,
            )

        # Ensure SSO Session is ready
        try:
            self.get_session()
        except SSOConnectionRefusedError as e:
            logger.error("SSO Connection failed: %s", e)
            return BatchDownloadSummary(
                total_requested=total_requested,
                total_downloaded=0,
                total_failed=total_requested,
                results=[],
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )
        except Exception as e:
            logger.error("Auth initialization failed: %s", e)
            return BatchDownloadSummary(
                total_requested=total_requested,
                total_downloaded=0,
                total_failed=total_requested,
                results=[],
                error_message=f"Authentication Failed: {e}",
                elapsed_seconds=time.time() - start_time,
            )

        results: List[DownloadResult] = []
        downloaded_count = 0
        failed_count = 0

        for i, item in enumerate(items):
            if cancel_check and cancel_check():
                logger.info("Batch download cancelled by user at item %d/%d", i + 1, total_requested)
                break

            res = self.process_item(item, download_dir)
            results.append(res)

            if res.status == "Success":
                downloaded_count += 1
            else:
                failed_count += 1

            if progress_callback:
                try:
                    progress_callback(i + 1, total_requested, res)
                except Exception as cb_err:
                    logger.debug("Progress callback error: %s", cb_err)

        return BatchDownloadSummary(
            total_requested=total_requested,
            total_downloaded=downloaded_count,
            total_failed=failed_count,
            results=results,
            error_message=None,
            elapsed_seconds=round(time.time() - start_time, 2),
        )

    # ------------------ Parsing Helpers ------------------

    def _parse_search_response(self, resp: requests.Response, qcode: str, fab: str) -> List[DrawingRecord]:
        """Parses FDM search response from either JSON or HTML table."""
        records: List[DrawingRecord] = []

        # Try JSON
        try:
            data = resp.json()
            items_list = []
            if isinstance(data, list):
                items_list = data
            elif isinstance(data, dict):
                for key in ("items", "list", "rows", "data", "result", "drawings"):
                    if key in data and isinstance(data[key], list):
                        items_list = data[key]
                        break

            for item in items_list:
                if isinstance(item, dict):
                    rec = DrawingRecord(
                        qcode=qcode,
                        drawing_oid=str(item.get("drawingOid") or item.get("oid") or item.get("id") or ""),
                        fab_oid=str(item.get("fabOid") or fab),
                        folder_path=str(item.get("folderPath") or ""),
                        type_name=str(item.get("typeName") or item.get("type") or "Non-CAD"),
                        file_name=str(item.get("fileName") or item.get("name") or ""),
                        doc_number=str(item.get("docNumber") or item.get("number") or ""),
                        raw_data=item,
                    )
                    if rec.drawing_oid:
                        records.append(rec)
            if records:
                return records
        except (ValueError, json.JSONDecodeError):
            pass

        # Parse HTML table
        soup = BeautifulSoup(resp.text, "html.parser")
        for tr in soup.find_all("tr"):
            attrs = tr.attrs
            drawing_oid = attrs.get("drawingoid") or attrs.get("data-drawing-oid") or attrs.get("oid")
            type_name = attrs.get("typename") or attrs.get("data-type") or ""

            # Check links inside tr
            if not drawing_oid:
                for a in tr.find_all("a", href=True):
                    href = a["href"]
                    if "drawingOid=" in href:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        if "drawingOid" in parsed:
                            drawing_oid = parsed["drawingOid"][0]
                        if "fabOid" in parsed:
                            fab = parsed["fabOid"][0]
                        if "folderPath" in parsed:
                            attrs["folderPath"] = parsed["folderPath"][0]
                        break

            # Check text cells
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if not type_name and cells:
                for cell in cells:
                    if cell.upper() in ("CAD", "NON-CAD", "JPG", "PDF", "2D", "3D"):
                        type_name = cell
                        break

            if drawing_oid:
                records.append(
                    DrawingRecord(
                        qcode=qcode,
                        drawing_oid=str(drawing_oid),
                        fab_oid=str(attrs.get("faboid") or fab),
                        folder_path=str(attrs.get("folderpath") or ""),
                        type_name=type_name or "Non-CAD",
                        file_name=cells[1] if len(cells) > 1 else "",
                        raw_data=attrs,
                    )
                )

        return records

    @staticmethod
    def _is_html_login_page(text: str, content_type: str) -> bool:
        """Determines if a response is an SSO redirect / login page."""
        t = (text or "").lower()
        if "login" in t and ("form" in t or "password" in t or "sso" in t):
            return True
        if "user authentication" in t or "sign in" in t:
            return True
        return False

    @staticmethod
    def _is_html_content(chunk: bytes, content_type: str) -> bool:
        """Detects if a downloaded payload chunk is HTML instead of binary image data."""
        if "text/html" in content_type:
            return True
        lowered = chunk[:512].lower().strip()
        if lowered.startswith(b"<!doctype html") or lowered.startswith(b"<html"):
            return True
        if b"<head>" in lowered or b"<body>" in lowered:
            return True
        return False

    @staticmethod
    def _extract_filename(resp: requests.Response, record: DrawingRecord, url: str) -> str:
        """Extracts appropriate filename from HTTP headers or record metadata."""
        # 1. Content-Disposition header
        cd = resp.headers.get("Content-Disposition", "")
        if cd:
            match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)["\']?', cd, re.IGNORECASE)
            if match:
                return urllib.parse.unquote(match.group(1).strip())

        # 2. Record file_name
        if record.file_name:
            ext = os.path.splitext(record.file_name)[1].lower()
            if ext in RASTER_EXTENSIONS or ext:
                return record.file_name

        # 3. URL path basename
        parsed_path = urllib.parse.urlparse(url).path
        base = os.path.basename(parsed_path)
        if base and "." in base:
            return urllib.parse.unquote(base)

        # 4. Default fallback
        return f"{record.qcode}_{record.drawing_oid}.jpg"

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Removes illegal filesystem characters."""
        clean = re.sub(r'[\\/*?:"<>|\r\n\t]', "_", name).strip()
        return clean or "drawing.jpg"
