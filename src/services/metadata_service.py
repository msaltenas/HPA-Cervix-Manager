"""Write a parsed CervixExtraction into SQLite (metadata only, no image bytes).

Shared by scripts/bootstrap_test.py (Phase 2-6, per-gene fetch) and
scripts/sync_cervix_metadata.py (Phase 11, bulk export) so both paths use
identical upsert logic and never diverge.
"""

from __future__ import annotations

import sqlite3

from database import repositories
from hpa.parser import CervixExtraction

ExtractionMetadata = tuple[int, dict[str, int], dict[int, int]]


def store_extraction_metadata(
    conn: sqlite3.Connection, extraction: CervixExtraction
) -> ExtractionMetadata:
    """Upsert gene/antibodies/cell-type-annotations for one gene. Returns lookup maps."""
    gene_row_id = repositories.upsert_gene(conn, extraction.gene)

    antibody_row_ids: dict[str, int] = {}
    for antibody in extraction.antibodies:
        antibody_row_ids[antibody.antibody_id] = repositories.upsert_antibody(conn, antibody)

    annotation_row_ids: dict[int, int] = {}
    for annotation in extraction.cell_type_annotations:
        antibody_row_id = antibody_row_ids[annotation.antibody_id]
        annotation_row_ids[id(annotation)] = repositories.upsert_tissue_cell_annotation(
            conn, annotation, antibody_row_id
        )

    return gene_row_id, antibody_row_ids, annotation_row_ids


def store_extraction_images(
    conn: sqlite3.Connection,
    extraction: CervixExtraction,
    metadata: ExtractionMetadata,
    *,
    data_source: str,
) -> list[tuple[int, str]]:
    """Upsert every image of one gene's extraction as metadata-only rows.

    Rows are created with download_status='pending'.

    Does not touch the network or the filesystem -- see
    images.converter / scripts/download_pending_images.py for the separate
    download+convert step that is meant to run wherever the data folder
    actually lives (see docs/MASS_DOWNLOAD.md).
    """
    gene_row_id, antibody_row_ids, annotation_row_ids = metadata
    stored: list[tuple[int, str]] = []

    for image in extraction.images:
        antibody_row_id = antibody_row_ids[image.antibody_id]
        sample_row_id = repositories.upsert_sample(conn, image, antibody_row_id)

        image_row_id, internal_id = repositories.upsert_image(
            conn,
            image,
            hpa_entry_url=extraction.gene.entry_url,
            hpa_version=extraction.gene.hpa_version,
            data_source=data_source,
        )

        repositories.link_image_gene(conn, image_row_id, gene_row_id)
        repositories.link_image_antibody(conn, image_row_id, antibody_row_id)
        repositories.link_image_sample(conn, image_row_id, sample_row_id)
        for annotation in image.cell_type_annotations:
            repositories.link_image_cell_type(
                conn, image_row_id, annotation_row_ids[id(annotation)]
            )

        stored.append((image_row_id, internal_id))

    return stored


def store_extraction(
    conn: sqlite3.Connection, extraction: CervixExtraction, *, data_source: str
) -> list[tuple[int, str]]:
    """Convenience wrapper: store gene/antibody/annotation metadata, then all its images."""
    metadata = store_extraction_metadata(conn, extraction)
    return store_extraction_images(conn, extraction, metadata, data_source=data_source)
