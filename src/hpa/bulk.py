"""Resumable download and streaming parse of the official HPA bulk export.

This implements "Strategy A" from the Phase 11 architecture decision: one
official bulk file (~730 MB compressed, verified via `curl -I`) instead of
~13,600 individual per-gene requests. See docs/HPA_DATA_SOURCE.md and
docs/MASS_DOWNLOAD.md for the full reasoning.

The bulk file is too large to hold in memory as a DOM (uncompressed size is
in the 15-30 GB range, extrapolated from real per-gene file sizes). Parsing
therefore streams the gzip data through `xml.etree.ElementTree.iterparse`
and clears each `<entry>` element once processed, per the standard
memory-bounded iterparse pattern -- no lxml dependency required.
"""

from __future__ import annotations

import gzip
import json
import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import requests

from hpa.client import DEFAULT_RETRIES, DEFAULT_TIMEOUT, USER_AGENT, HPAClientError
from hpa.parser import CervixExtraction, extract_cervix_data_from_entry

logger = logging.getLogger(__name__)

BULK_XML_URL = "https://www.proteinatlas.org/download/proteinatlas.xml.gz"
CHUNK_SIZE = 1024 * 1024  # 1 MB

ProgressCallback = Callable[[int, int | None], None]


@dataclass(frozen=True)
class BulkFileInfo:
    content_length: int | None
    etag: str | None
    last_modified: str | None
    accepts_ranges: bool


def get_bulk_file_info() -> BulkFileInfo:
    """HEAD the bulk export to learn its current size/version markers."""
    response = requests.head(
        BULK_XML_URL, timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    content_length = response.headers.get("Content-Length")
    return BulkFileInfo(
        content_length=int(content_length) if content_length else None,
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
        accepts_ranges=response.headers.get("Accept-Ranges") == "bytes",
    )


def _meta_path(destination: Path) -> Path:
    return destination.with_name(destination.name + ".meta.json")


def _read_meta(destination: Path) -> dict | None:
    meta_path = _meta_path(destination)
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_meta(destination: Path, info: BulkFileInfo) -> None:
    _meta_path(destination).write_text(
        json.dumps(
            {
                "url": BULK_XML_URL,
                "content_length": info.content_length,
                "etag": info.etag,
                "last_modified": info.last_modified,
            },
            indent=2,
        )
    )


def download_bulk_xml(
    destination: Path,
    *,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    """Download (or resume) proteinatlas.xml.gz to `destination`.

    Safe to interrupt and re-run: if a partial download exists and the
    remote file is unchanged (same ETag), the download resumes via HTTP
    Range. If the remote file changed (new HPA release), the partial/old
    file is discarded and a fresh download starts, so we never silently
    stitch together bytes from two different releases.
    """
    info = get_bulk_file_info()
    destination.parent.mkdir(parents=True, exist_ok=True)

    resume_from = 0
    local_meta = _read_meta(destination)
    if destination.exists() and local_meta is not None:
        same_version = local_meta.get("etag") == info.etag
        current_size = destination.stat().st_size
        if same_version and info.content_length is not None:
            if current_size == info.content_length:
                logger.info(
                    "Bulk file already complete and up to date (etag=%s); skipping download.",
                    info.etag,
                )
                return destination
            if current_size < info.content_length and info.accepts_ranges:
                resume_from = current_size
                logger.info(
                    "Resuming bulk download from byte %d of %d", resume_from, info.content_length
                )
        if not same_version:
            logger.info("Remote bulk file changed (etag mismatch) -- restarting from scratch.")

    if resume_from == 0 and destination.exists():
        destination.unlink()

    headers = {"User-Agent": USER_AGENT}
    mode = "wb"
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"
        mode = "ab"

    last_exc: Exception | None = None
    for attempt in range(1, DEFAULT_RETRIES + 1):
        try:
            with requests.get(
                BULK_XML_URL, headers=headers, stream=True, timeout=DEFAULT_TIMEOUT
            ) as response:
                response.raise_for_status()
                downloaded = resume_from
                with destination.open(mode) as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, info.content_length)
            break
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("Bulk download attempt %d/%d failed: %s", attempt, DEFAULT_RETRIES, exc)
    else:
        raise HPAClientError(
            f"Bulk download failed after {DEFAULT_RETRIES} attempts"
        ) from last_exc

    final_size = destination.stat().st_size
    if info.content_length is not None and final_size != info.content_length:
        raise HPAClientError(
            f"Bulk download size mismatch: got {final_size} bytes, expected {info.content_length}"
        )

    _write_meta(destination, info)
    return destination


def iter_cervix_entries(gz_path: Path) -> Iterator[CervixExtraction]:
    """Stream-parse the bulk export, yielding one CervixExtraction per gene that has Cervix images.

    Memory-bounded: each `<entry>` element is cleared immediately after
    being processed, regardless of the total file size.
    """
    with gzip.open(gz_path, "rb") as xml_file:
        context = ET.iterparse(xml_file, events=("end",))
        for _event, elem in context:
            if elem.tag != "entry":
                continue
            extraction = extract_cervix_data_from_entry(elem)
            elem.clear()
            if extraction.images:
                yield extraction
