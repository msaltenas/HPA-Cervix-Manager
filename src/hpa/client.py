"""HTTP client for the official Human Protein Atlas (HPA) endpoints.

Only endpoints that were manually verified against the live HPA server are
used here (see docs/HPA_DATA_SOURCE.md for the investigation). No URL is
guessed or constructed from assumptions about HPA's internal structure.

Verified endpoints:
- https://www.proteinatlas.org/api/search_download.php  -- gene search / Ensembl ID lookup
- https://www.proteinatlas.org/<ENSEMBL_ID>.xml          -- full per-gene entry (incl. images)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.proteinatlas.org"
SEARCH_ENDPOINT = f"{BASE_URL}/api/search_download.php"

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

# Identify ourselves honestly; HPA is a public academic resource, not an
# API meant for anonymous scraping-looking traffic.
USER_AGENT = "HPA-Cervix-Manager/0.1 (research tool; contact via GitHub repo)"


class HPAClientError(RuntimeError):
    """Raised when an HPA request fails after retries or returns unexpected data."""


@dataclass(frozen=True)
class GeneLookup:
    gene_symbol: str
    ensembl_id: str


def _request_with_retries(url: str, params: dict | None = None) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(1, DEFAULT_RETRIES + 1):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:  # noqa: PERF203
            last_exc = exc
            logger.warning("HPA request failed (attempt %d/%d): %s", attempt, DEFAULT_RETRIES, exc)
            if attempt < DEFAULT_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise HPAClientError(f"Request to {url} failed after {DEFAULT_RETRIES} attempts") from last_exc


def lookup_ensembl_id(gene_symbol: str) -> GeneLookup:
    """Resolve a gene symbol to its Ensembl gene ID via the official search API.

    Never guesses Ensembl IDs -- always asks HPA directly, because gene
    symbols are ambiguous and a wrong hand-typed Ensembl ID silently fetches
    the wrong gene (this happened once during investigation, see
    docs/HPA_DATA_SOURCE.md).
    """
    response = _request_with_retries(
        SEARCH_ENDPOINT,
        params={
            "search": gene_symbol,
            "format": "json",
            "columns": "g,eg",
            "compress": "no",
        },
    )
    results = response.json()
    for row in results:
        if row.get("Gene", "").upper() == gene_symbol.upper():
            return GeneLookup(gene_symbol=row["Gene"], ensembl_id=row["Ensembl"])
    raise HPAClientError(f"No exact gene-symbol match for {gene_symbol!r} in HPA search results")


def fetch_gene_xml(ensembl_id: str) -> str:
    """Fetch the full per-gene XML entry (includes tissue images) for one Ensembl gene ID."""
    url = f"{BASE_URL}/{ensembl_id}.xml"
    response = _request_with_retries(url)
    return response.text


def download_image_bytes(image_url: str) -> bytes:
    """Download raw image bytes from images.proteinatlas.org (or any HPA-supplied URL)."""
    response = _request_with_retries(image_url)
    return response.content
