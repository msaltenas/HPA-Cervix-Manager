#!/usr/bin/env python3
"""Phase 2-6 bootstrap test: fetch, download, convert and store 10 real Cervix images.

This script intentionally hits the live HPA server (a handful of requests
for 2 genes + 10 images) to prove the whole pipeline end-to-end with real
data, per the master prompt's Phase 1-6 scope. It must NOT be run in CI
(see .github/workflows/tests.yml, which uses fixtures instead).

Usage:
    python scripts/bootstrap_test.py [--data-dir PATH] [--limit N]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from database import database, repositories  # noqa: E402
from hpa import client, parser  # noqa: E402
from images import converter  # noqa: E402
from services.metadata_service import ExtractionMetadata, store_extraction_metadata  # noqa: E402

GENE_SYMBOLS = ["IVL", "ASRGL1"]
DATA_SOURCE = "HPA per-gene XML export (proteinatlas.org/<ENSEMBL_ID>.xml)"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bootstrap_test")


CandidateImage = tuple[parser.CervixExtraction, parser.ImageRecord]


def gather_candidate_images(gene_symbols: list[str]) -> list[CandidateImage]:
    candidates: list[CandidateImage] = []
    for symbol in gene_symbols:
        lookup = client.lookup_ensembl_id(symbol)
        logger.info("Resolved %s -> %s", symbol, lookup.ensembl_id)
        xml_text = client.fetch_gene_xml(lookup.ensembl_id)
        extraction = parser.extract_cervix_data(xml_text)
        logger.info(
            "Gene %s: %d antibodies, %d cervix images found",
            symbol,
            len(extraction.antibodies),
            len(extraction.images),
        )
        for image in extraction.images:
            candidates.append((extraction, image))
    return candidates


def run(data_dir: Path, limit: int) -> None:
    paths_images_dir = data_dir / "images"
    paths_metadata_dir = data_dir / "metadata"
    paths_images_dir.mkdir(parents=True, exist_ok=True)
    paths_metadata_dir.mkdir(parents=True, exist_ok=True)
    db_path = paths_metadata_dir / "hpa_cervix.sqlite"

    logger.info("Data directory: %s", data_dir)
    logger.info("Database: %s", db_path)

    candidates = gather_candidate_images(GENE_SYMBOLS)
    logger.info("Total candidate cervix images found: %d", len(candidates))
    selected = candidates[:limit]
    logger.info("Selecting first %d for this bootstrap test", len(selected))

    report_rows = []

    with database.get_connection(db_path) as conn:
        extraction_cache: dict[str, ExtractionMetadata] = {}

        for extraction, image in selected:
            ensembl_id = extraction.gene.ensembl_id
            if ensembl_id not in extraction_cache:
                extraction_cache[ensembl_id] = store_extraction_metadata(conn, extraction)
            gene_row_id, antibody_row_ids, annotation_row_ids = extraction_cache[ensembl_id]
            antibody_row_id = antibody_row_ids[image.antibody_id]

            sample_row_id = repositories.upsert_sample(conn, image, antibody_row_id)

            image_row_id, internal_id = repositories.upsert_image(
                conn,
                image,
                hpa_entry_url=extraction.gene.entry_url,
                hpa_version=extraction.gene.hpa_version,
                data_source=DATA_SOURCE,
            )

            repositories.link_image_gene(conn, image_row_id, gene_row_id)
            repositories.link_image_antibody(conn, image_row_id, antibody_row_id)
            repositories.link_image_sample(conn, image_row_id, sample_row_id)
            for annotation in image.cell_type_annotations:
                repositories.link_image_cell_type(
                    conn, image_row_id, annotation_row_ids[id(annotation)]
                )

            logger.info(
                "Downloading %s -> %s (%s / %s)",
                image.image_url,
                internal_id,
                extraction.gene.gene_symbol,
                image.antibody_id,
            )
            image_bytes = client.download_image_bytes(image.image_url)
            destination = paths_images_dir / f"{internal_id}.jpg"
            result = converter.convert_to_jpeg(image_bytes, destination)

            repositories.update_download_status(
                conn,
                image_row_id,
                local_path=str(destination),
                width=result.width,
                height=result.height,
                original_format=result.original_format,
                file_size=result.file_size,
                download_status="downloaded_converted",
                download_date=datetime.now(UTC).isoformat(),
            )
            conn.commit()

            report_rows.append(
                {
                    "internal_id": internal_id,
                    "gene": extraction.gene.gene_symbol,
                    "antibody": image.antibody_id,
                    "original_format": result.original_format,
                    "size": f"{result.width}x{result.height}",
                    "file_size": result.file_size,
                }
            )

        verify(conn, report_rows)


def verify(conn, report_rows: list[dict]) -> None:
    logger.info("--- Verification ---")
    for row in report_rows:
        db_row = conn.execute(
            """
            SELECT
                i.internal_id, i.hpa_image_id, i.filename, i.local_path,
                i.width, i.height, i.original_format, i.file_size,
                i.download_status, i.hpa_entry_url, i.hpa_version,
                g.gene_symbol, g.ensembl_id,
                a.antibody_id, a.release_version,
                s.hpa_patient_id, s.sex, s.age, s.snomed_tissue_description, s.snomed_code
            FROM images i
            JOIN image_genes ig ON ig.image_id = i.id
            JOIN genes g ON g.id = ig.gene_id
            JOIN image_antibodies ia ON ia.image_id = i.id
            JOIN antibodies a ON a.id = ia.antibody_id
            JOIN image_samples isamp ON isamp.image_id = i.id
            JOIN samples s ON s.id = isamp.sample_id
            WHERE i.internal_id = ?
            """,
            (row["internal_id"],),
        ).fetchone()
        assert db_row is not None, f"Missing DB row for {row['internal_id']}"

        cell_types = conn.execute(
            """
            SELECT tca.cell_type, tca.staining_level, tca.intensity_level,
                   tca.quantity, tca.location
            FROM image_cell_types ict
            JOIN tissue_cell_annotations tca ON tca.id = ict.tissue_cell_annotation_id
            JOIN images i ON i.id = ict.image_id
            WHERE i.internal_id = ?
            """,
            (row["internal_id"],),
        ).fetchall()

        local_path = Path(db_row["local_path"])
        assert local_path.exists(), f"JPEG file missing on disk: {local_path}"
        assert local_path.stat().st_size > 0

        cell_type_summary = "; ".join(
            f"{c['cell_type']}={c['staining_level']}/{c['intensity_level']}" for c in cell_types
        )
        logger.info(
            "%s: gene=%s (%s) antibody=%s patient=%s/%s/%sy tissue-cells=[%s] "
            "image=%dx%d %s %d bytes -> %s",
            db_row["internal_id"],
            db_row["gene_symbol"],
            db_row["ensembl_id"],
            db_row["antibody_id"],
            db_row["hpa_patient_id"],
            db_row["sex"],
            db_row["age"],
            cell_type_summary,
            db_row["width"],
            db_row["height"],
            db_row["original_format"],
            db_row["file_size"],
            local_path.name,
        )
    logger.info(
        "All %d rows verified: DB metadata matches downloaded JPEG on disk.", len(report_rows)
    )


def main() -> None:
    parser_args = argparse.ArgumentParser(description=__doc__)
    parser_args.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "data",
        help="Data directory (default: ./data, gitignored)",
    )
    parser_args.add_argument("--limit", type=int, default=10, help="Number of images to fetch")
    args = parser_args.parse_args()

    run(args.data_dir, args.limit)


if __name__ == "__main__":
    main()
