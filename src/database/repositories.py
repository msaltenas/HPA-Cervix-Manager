"""Upsert helpers that write parsed HPA records into SQLite without creating duplicates.

Re-running an import for the same gene/antibody/image updates the existing
row instead of inserting a second one, driven by the UNIQUE constraints
defined in database.py (ensembl_id, antibody_id, hpa_image_id, etc.).
"""

from __future__ import annotations

import sqlite3

from hpa.parser import AntibodyEntry, CellTypeAnnotation, GeneEntry, ImageRecord

INTERNAL_ID_PREFIX = "HPA_"
INTERNAL_ID_WIDTH = 6


def next_internal_id(conn: sqlite3.Connection) -> str:
    """Allocate the next sequential, stable internal image ID (HPA_000001, ...)."""
    row = conn.execute(
        "SELECT internal_id FROM images ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        next_number = 1
    else:
        next_number = int(row["internal_id"].removeprefix(INTERNAL_ID_PREFIX)) + 1
    return f"{INTERNAL_ID_PREFIX}{next_number:0{INTERNAL_ID_WIDTH}d}"


def upsert_gene(conn: sqlite3.Connection, gene: GeneEntry) -> int:
    conn.execute(
        """
        INSERT INTO genes (ensembl_id, gene_symbol, updated_at)
        VALUES (:ensembl_id, :gene_symbol, datetime('now'))
        ON CONFLICT(ensembl_id) DO UPDATE SET
            gene_symbol = excluded.gene_symbol,
            updated_at = datetime('now')
        """,
        {"ensembl_id": gene.ensembl_id, "gene_symbol": gene.gene_symbol},
    )
    row = conn.execute(
        "SELECT id FROM genes WHERE ensembl_id = ?", (gene.ensembl_id,)
    ).fetchone()
    return row["id"]


def upsert_antibody(conn: sqlite3.Connection, antibody: AntibodyEntry) -> int:
    conn.execute(
        """
        INSERT INTO antibodies
            (antibody_id, release_version, release_date, rrid, target_information, updated_at)
        VALUES
            (:antibody_id, :release_version, :release_date, :rrid,
             :target_information, datetime('now'))
        ON CONFLICT(antibody_id) DO UPDATE SET
            release_version = excluded.release_version,
            release_date = excluded.release_date,
            rrid = excluded.rrid,
            target_information = excluded.target_information,
            updated_at = datetime('now')
        """,
        {
            "antibody_id": antibody.antibody_id,
            "release_version": antibody.release_version,
            "release_date": antibody.release_date,
            "rrid": antibody.rrid,
            "target_information": antibody.antigen_sequence,
        },
    )
    row = conn.execute(
        "SELECT id FROM antibodies WHERE antibody_id = ?", (antibody.antibody_id,)
    ).fetchone()
    return row["id"]


def upsert_tissue_cell_annotation(
    conn: sqlite3.Connection, annotation: CellTypeAnnotation, antibody_row_id: int
) -> int:
    conn.execute(
        """
        INSERT INTO tissue_cell_annotations
            (antibody_id, tissue, tissue_organ, tissue_ontology_terms, cell_type,
             staining_level, intensity_level, quantity, location, updated_at)
        VALUES
            (:antibody_id, :tissue, :tissue_organ, :tissue_ontology_terms, :cell_type,
             :staining_level, :intensity_level, :quantity, :location, datetime('now'))
        ON CONFLICT(antibody_id, tissue, cell_type) DO UPDATE SET
            tissue_organ = excluded.tissue_organ,
            tissue_ontology_terms = excluded.tissue_ontology_terms,
            staining_level = excluded.staining_level,
            intensity_level = excluded.intensity_level,
            quantity = excluded.quantity,
            location = excluded.location,
            updated_at = datetime('now')
        """,
        {
            "antibody_id": antibody_row_id,
            "tissue": annotation.tissue,
            "tissue_organ": annotation.tissue_organ,
            "tissue_ontology_terms": annotation.tissue_ontology_terms,
            "cell_type": annotation.cell_type,
            "staining_level": annotation.staining_level,
            "intensity_level": annotation.intensity_level,
            "quantity": annotation.quantity,
            "location": annotation.location,
        },
    )
    row = conn.execute(
        """
        SELECT id FROM tissue_cell_annotations
        WHERE antibody_id = ? AND tissue = ? AND cell_type = ?
        """,
        (antibody_row_id, annotation.tissue, annotation.cell_type),
    ).fetchone()
    return row["id"]


def upsert_sample(
    conn: sqlite3.Connection, image: ImageRecord, antibody_row_id: int
) -> int:
    conn.execute(
        """
        INSERT INTO samples
            (antibody_id, tissue, hpa_patient_id, sex, age,
             snomed_tissue_description, snomed_code, updated_at)
        VALUES
            (:antibody_id, :tissue, :hpa_patient_id, :sex, :age,
             :snomed_tissue_description, :snomed_code, datetime('now'))
        ON CONFLICT(antibody_id, tissue, hpa_patient_id) DO UPDATE SET
            sex = excluded.sex,
            age = excluded.age,
            snomed_tissue_description = excluded.snomed_tissue_description,
            snomed_code = excluded.snomed_code,
            updated_at = datetime('now')
        """,
        {
            "antibody_id": antibody_row_id,
            "tissue": image.tissue,
            "hpa_patient_id": image.hpa_patient_id,
            "sex": image.sex,
            "age": image.age,
            "snomed_tissue_description": image.snomed_tissue_description,
            "snomed_code": image.snomed_code,
        },
    )
    row = conn.execute(
        """
        SELECT id FROM samples
        WHERE antibody_id = ? AND tissue = ? AND hpa_patient_id IS ?
        """,
        (antibody_row_id, image.tissue, image.hpa_patient_id),
    ).fetchone()
    return row["id"]


def upsert_image(
    conn: sqlite3.Connection,
    image: ImageRecord,
    *,
    hpa_entry_url: str,
    hpa_version: str,
    data_source: str,
) -> tuple[int, str]:
    """Insert or update the images row. Returns (row_id, internal_id).

    The internal_id is allocated once, on first insert, and never changes
    on subsequent re-imports of the same hpa_image_id.
    """
    existing = conn.execute(
        "SELECT id, internal_id FROM images WHERE hpa_image_id = ?",
        (image.hpa_image_id,),
    ).fetchone()
    internal_id = existing["internal_id"] if existing else next_internal_id(conn)
    filename = f"{internal_id}.jpg"

    conn.execute(
        """
        INSERT INTO images
            (internal_id, hpa_image_id, filename, original_url, original_url_tif,
             hpa_entry_url, image_type, hpa_version, data_source, updated_at)
        VALUES
            (:internal_id, :hpa_image_id, :filename, :original_url, :original_url_tif,
             :hpa_entry_url, :image_type, :hpa_version, :data_source, datetime('now'))
        ON CONFLICT(hpa_image_id) DO UPDATE SET
            original_url = excluded.original_url,
            original_url_tif = excluded.original_url_tif,
            hpa_entry_url = excluded.hpa_entry_url,
            image_type = excluded.image_type,
            hpa_version = excluded.hpa_version,
            data_source = excluded.data_source,
            updated_at = datetime('now')
        """,
        {
            "internal_id": internal_id,
            "hpa_image_id": image.hpa_image_id,
            "filename": filename,
            "original_url": image.image_url,
            "original_url_tif": image.image_url_tif,
            "hpa_entry_url": hpa_entry_url,
            "image_type": image.image_type,
            "hpa_version": hpa_version,
            "data_source": data_source,
        },
    )
    row = conn.execute(
        "SELECT id, internal_id FROM images WHERE hpa_image_id = ?",
        (image.hpa_image_id,),
    ).fetchone()
    return row["id"], row["internal_id"]


def link_image_gene(conn: sqlite3.Connection, image_id: int, gene_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO image_genes (image_id, gene_id) VALUES (?, ?)",
        (image_id, gene_id),
    )


def link_image_antibody(conn: sqlite3.Connection, image_id: int, antibody_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO image_antibodies (image_id, antibody_id) VALUES (?, ?)",
        (image_id, antibody_id),
    )


def link_image_sample(conn: sqlite3.Connection, image_id: int, sample_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO image_samples (image_id, sample_id) VALUES (?, ?)",
        (image_id, sample_id),
    )


def link_image_cell_type(conn: sqlite3.Connection, image_id: int, annotation_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO image_cell_types "
        "(image_id, tissue_cell_annotation_id) VALUES (?, ?)",
        (image_id, annotation_id),
    )


def update_download_status(
    conn: sqlite3.Connection,
    image_id: int,
    *,
    local_path: str,
    width: int,
    height: int,
    original_format: str,
    file_size: int,
    download_status: str,
    download_date: str,
) -> None:
    conn.execute(
        """
        UPDATE images SET
            local_path = ?,
            width = ?,
            height = ?,
            original_format = ?,
            file_size = ?,
            download_status = ?,
            download_date = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            local_path, width, height, original_format,
            file_size, download_status, download_date, image_id,
        ),
    )


def mark_download_failed(conn: sqlite3.Connection, image_id: int) -> None:
    conn.execute(
        """
        UPDATE images SET download_status = 'failed', updated_at = datetime('now')
        WHERE id = ?
        """,
        (image_id,),
    )


def list_pending_images(conn: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    """Images whose bytes have not been successfully downloaded+converted yet.

    Used by scripts/download_pending_images.py, the step meant to run on
    whichever machine holds the real data folder (see docs/MASS_DOWNLOAD.md).
    """
    query = """
        SELECT id, internal_id, filename, original_url
        FROM images
        WHERE download_status NOT IN ('downloaded_converted')
        ORDER BY id
    """
    if limit is not None:
        query += " LIMIT ?"
        return conn.execute(query, (limit,)).fetchall()
    return conn.execute(query).fetchall()


def count_images_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT download_status, COUNT(*) AS n FROM images GROUP BY download_status"
    ).fetchall()
    return {row["download_status"]: row["n"] for row in rows}
