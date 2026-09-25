#!/usr/bin/env python3
"""Phase 11, step 1: Strategy A metadata sync (no image bytes downloaded here).

Downloads (or resumes) the official genome-wide `proteinatlas.xml.gz` bulk
export, stream-parses it (memory-bounded, does not load the whole ~15-30 GB
uncompressed file into memory), and upserts every Cervix IHC image's full
metadata into SQLite with download_status='pending'.

This step is metadata-only and safe to run on any machine -- it does not
download the actual image bytes (that step, scripts/download_pending_images.py,
is meant to run on whichever machine holds the real data folder; see
docs/MASS_DOWNLOAD.md for the two-phase, multi-Mac workflow).

Usage:
    python scripts/sync_cervix_metadata.py --data-dir /path/to/HPA_Cervix [--limit-genes N]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from database import database, repositories  # noqa: E402
from hpa import bulk  # noqa: E402
from services.metadata_service import store_extraction  # noqa: E402

DATA_SOURCE = "HPA bulk XML export (proteinatlas.org/download/proteinatlas.xml.gz)"
COMMIT_EVERY_N_GENES = 200

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_cervix_metadata")


def _progress(downloaded: int, total: int | None) -> None:
    if total:
        pct = downloaded / total * 100
        logger.info("Downloading bulk export: %.1f%% (%d / %d bytes)", pct, downloaded, total)
    else:
        logger.info("Downloading bulk export: %d bytes", downloaded)


def run(data_dir: Path, limit_genes: int | None) -> None:
    cache_dir = data_dir / "cache"
    metadata_dir = data_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = metadata_dir / "hpa_cervix.sqlite"
    gz_path = cache_dir / "proteinatlas.xml.gz"

    logger.info("Data directory: %s", data_dir)
    logger.info("Bulk export cache: %s", gz_path)
    logger.info("Database: %s", db_path)

    last_logged_pct = -1

    def progress_throttled(downloaded: int, total: int | None) -> None:
        nonlocal last_logged_pct
        if total:
            pct = int(downloaded / total * 100)
            if pct != last_logged_pct:
                last_logged_pct = pct
                _progress(downloaded, total)
        else:
            _progress(downloaded, total)

    bulk.download_bulk_xml(gz_path, progress_callback=progress_throttled)
    logger.info("Bulk export ready at %s (%d bytes)", gz_path, gz_path.stat().st_size)

    genes_processed = 0
    genes_with_cervix = 0
    images_upserted = 0

    with database.get_connection(db_path) as conn:
        for extraction in bulk.iter_cervix_entries(gz_path):
            genes_with_cervix += 1
            genes_processed += 1
            stored = store_extraction(conn, extraction, data_source=DATA_SOURCE)
            images_upserted += len(stored)

            if genes_with_cervix % COMMIT_EVERY_N_GENES == 0:
                conn.commit()
                logger.info(
                    "Progress: %d genes with Cervix data processed, %d images upserted so far",
                    genes_with_cervix,
                    images_upserted,
                )

            if limit_genes is not None and genes_with_cervix >= limit_genes:
                logger.info("Reached --limit-genes=%d, stopping early.", limit_genes)
                break

        conn.commit()

        status_counts = repositories.count_images_by_status(conn)

    logger.info("--- Summary ---")
    logger.info("Genes with Cervix IHC data processed: %d", genes_with_cervix)
    logger.info("Images upserted (metadata only, download_status='pending'): %d", images_upserted)
    logger.info("Current images table status breakdown: %s", status_counts)
    logger.info(
        "Next step: run scripts/download_pending_images.py on the machine that should "
        "actually download and convert the image bytes."
    )


def main() -> None:
    parser_args = argparse.ArgumentParser(description=__doc__)
    parser_args.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "data",
        help="Data directory (default: ./data, gitignored)",
    )
    parser_args.add_argument(
        "--limit-genes",
        type=int,
        default=None,
        help="Stop after this many genes with Cervix data (for testing; omit for a full run)",
    )
    args = parser_args.parse_args()

    run(args.data_dir, args.limit_genes)


if __name__ == "__main__":
    main()
