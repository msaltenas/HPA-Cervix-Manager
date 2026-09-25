#!/usr/bin/env python3
"""Phase 11, step 2: download + convert the image bytes for pending SQLite rows.

This is the step meant to run on whichever machine actually holds the data
folder (e.g. an iCloud Drive-synced Mac with enough disk space) -- see
docs/MASS_DOWNLOAD.md. It only needs:
  1. This repository (git pull), a Python environment with dependencies installed.
  2. A data directory containing metadata/hpa_cervix.sqlite already populated
     by scripts/sync_cervix_metadata.py (copy it over, or point --data-dir at
     a synced folder that already has it).

It never re-derives metadata from HPA -- it only reads `images` rows with
download_status != 'downloaded_converted', downloads image_url, converts to
a real JPEG (Pillow), and updates the row. Safe to interrupt and re-run:
already-converted images are skipped.

Usage:
    python scripts/download_pending_images.py --data-dir /path/to/HPA_Cervix \\
        [--limit N] [--workers N]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from database import database, repositories  # noqa: E402
from hpa import client  # noqa: E402
from images import converter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("download_pending_images")

# Polite default: HPA is a public academic server, not a CDN meant for bulk
# scraping -- keep concurrency low unless the operator explicitly raises it.
DEFAULT_WORKERS = 2


def download_one(images_dir: Path, row: dict) -> tuple[int, str, Exception | None]:
    internal_id = row["internal_id"]
    try:
        image_bytes = client.download_image_bytes(row["original_url"])
        destination = images_dir / row["filename"]
        result = converter.convert_to_jpeg(image_bytes, destination)
        return row["id"], "ok", result
    except Exception as exc:  # noqa: BLE001 -- reported to caller, not swallowed
        logger.warning("Failed to download/convert %s: %s", internal_id, exc)
        return row["id"], "failed", exc


def run(data_dir: Path, limit: int | None, workers: int) -> None:
    images_dir = data_dir / "images"
    metadata_dir = data_dir / "metadata"
    images_dir.mkdir(parents=True, exist_ok=True)
    db_path = metadata_dir / "hpa_cervix.sqlite"

    if not db_path.exists():
        raise SystemExit(
            f"No database found at {db_path}. Run scripts/sync_cervix_metadata.py first "
            "(on this machine or another one, then copy/sync the data folder here)."
        )

    with database.get_connection(db_path) as conn:
        pending_rows = repositories.list_pending_images(conn, limit=limit)
        pending = [dict(row) for row in pending_rows]
        logger.info("Pending images to download: %d", len(pending))

        succeeded = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(download_one, images_dir, row): row for row in pending
            }
            for i, future in enumerate(as_completed(futures), start=1):
                row = futures[future]
                image_id, status, payload = future.result()

                if status == "ok":
                    result = payload
                    repositories.update_download_status(
                        conn,
                        image_id,
                        local_path=str(images_dir / row["filename"]),
                        width=result.width,
                        height=result.height,
                        original_format=result.original_format,
                        file_size=result.file_size,
                        download_status="downloaded_converted",
                        download_date=datetime.now(UTC).isoformat(),
                    )
                    succeeded += 1
                else:
                    repositories.mark_download_failed(conn, image_id)
                    failed += 1

                if i % 50 == 0:
                    conn.commit()
                    logger.info(
                        "Progress: %d/%d (ok=%d, failed=%d)", i, len(pending), succeeded, failed
                    )

        conn.commit()
        status_counts = repositories.count_images_by_status(conn)

    logger.info("--- Summary ---")
    logger.info("Succeeded: %d, Failed: %d", succeeded, failed)
    logger.info("Current images table status breakdown: %s", status_counts)


def main() -> None:
    parser_args = argparse.ArgumentParser(description=__doc__)
    parser_args.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "data",
        help="Data directory (default: ./data, gitignored)",
    )
    parser_args.add_argument(
        "--limit", type=int, default=None, help="Only process this many pending images"
    )
    parser_args.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Concurrent downloads (default: {DEFAULT_WORKERS}, keep low to be polite to HPA)",
    )
    args = parser_args.parse_args()

    start = time.monotonic()
    run(args.data_dir, args.limit, args.workers)
    logger.info("Done in %.1fs", time.monotonic() - start)


if __name__ == "__main__":
    main()
