"""SQLite schema and connection handling for the HPA Cervix Manager.

Schema design notes (see docs/HPA_DATA_SOURCE.md for the underlying HPA
data model this maps to):

- `tissue_cell_annotations` + `image_cell_types` exist because HPA reports
  cell-type staining (e.g. "Glandular cells: high") per (antibody, tissue)
  data block, not per individual photographed image. Flattening that into
  a single `cell_type` column on `images` would fabricate a precision the
  source data does not have. An image is linked to every cell-type
  annotation that applies to the data block it came from.
- Relation tables (image_genes, image_antibodies, image_samples) exist
  because HPA does not guarantee 1:1 relationships between an image and a
  gene/antibody/sample, even though that is the common case.
- UNIQUE constraints prevent duplicate rows on repeated imports; imports
  should UPSERT (see repositories.py) rather than blindly INSERT.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS genes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ensembl_id TEXT NOT NULL UNIQUE,
    gene_symbol TEXT NOT NULL,
    gene_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_genes_symbol ON genes(gene_symbol);

CREATE TABLE IF NOT EXISTS antibodies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    antibody_id TEXT NOT NULL UNIQUE,
    release_version TEXT,
    release_date TEXT,
    rrid TEXT,
    provider TEXT,
    target_information TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tissue_cell_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    antibody_id INTEGER NOT NULL REFERENCES antibodies(id) ON DELETE CASCADE,
    tissue TEXT NOT NULL,
    tissue_organ TEXT,
    tissue_ontology_terms TEXT,
    cell_type TEXT NOT NULL,
    staining_level TEXT,
    intensity_level TEXT,
    quantity TEXT,
    location TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(antibody_id, tissue, cell_type)
);

CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    antibody_id INTEGER NOT NULL REFERENCES antibodies(id) ON DELETE CASCADE,
    tissue TEXT NOT NULL,
    hpa_patient_id TEXT,
    sex TEXT,
    age INTEGER,
    snomed_tissue_description TEXT,
    snomed_code TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(antibody_id, tissue, hpa_patient_id)
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    internal_id TEXT NOT NULL UNIQUE,
    hpa_image_id TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    local_path TEXT,
    marked_filename TEXT,
    marked_path TEXT,
    original_url TEXT NOT NULL,
    original_url_tif TEXT,
    hpa_entry_url TEXT,
    image_type TEXT,
    width INTEGER,
    height INTEGER,
    original_format TEXT,
    file_size INTEGER,
    download_status TEXT NOT NULL DEFAULT 'pending',
    marked_exists INTEGER NOT NULL DEFAULT 0,
    download_date TEXT,
    hpa_version TEXT,
    data_source TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_images_internal_id ON images(internal_id);

CREATE TABLE IF NOT EXISTS image_genes (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    gene_id INTEGER NOT NULL REFERENCES genes(id) ON DELETE CASCADE,
    PRIMARY KEY (image_id, gene_id)
);

CREATE TABLE IF NOT EXISTS image_antibodies (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    antibody_id INTEGER NOT NULL REFERENCES antibodies(id) ON DELETE CASCADE,
    PRIMARY KEY (image_id, antibody_id)
);

CREATE TABLE IF NOT EXISTS image_samples (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    PRIMARY KEY (image_id, sample_id)
);

CREATE TABLE IF NOT EXISTS image_cell_types (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    tissue_cell_annotation_id INTEGER NOT NULL
        REFERENCES tissue_cell_annotations(id) ON DELETE CASCADE,
    PRIMARY KEY (image_id, tissue_cell_annotation_id)
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


@contextmanager
def get_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        create_schema(conn)
        yield conn
    finally:
        conn.close()
