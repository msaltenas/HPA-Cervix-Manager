"""Tests for database schema + repositories. No network access -- uses the XML fixture."""

from pathlib import Path

import pytest

from database import database, repositories
from hpa import parser

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_gene.xml"


@pytest.fixture
def extraction():
    xml_text = FIXTURE_PATH.read_text()
    return parser.extract_cervix_data(xml_text)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.sqlite"
    with database.get_connection(db_path) as connection:
        yield connection


def _store(conn, extraction):
    gene_row_id = repositories.upsert_gene(conn, extraction.gene)
    antibody_row_ids = {
        ab.antibody_id: repositories.upsert_antibody(conn, ab) for ab in extraction.antibodies
    }
    annotation_row_ids = {
        id(ann): repositories.upsert_tissue_cell_annotation(
            conn, ann, antibody_row_ids[ann.antibody_id]
        )
        for ann in extraction.cell_type_annotations
    }

    image_row_ids = []
    for image in extraction.images:
        antibody_row_id = antibody_row_ids[image.antibody_id]
        sample_row_id = repositories.upsert_sample(conn, image, antibody_row_id)
        image_row_id, internal_id = repositories.upsert_image(
            conn,
            image,
            hpa_entry_url=extraction.gene.entry_url,
            hpa_version=extraction.gene.hpa_version,
            data_source="test-fixture",
        )
        repositories.link_image_gene(conn, image_row_id, gene_row_id)
        repositories.link_image_antibody(conn, image_row_id, antibody_row_id)
        repositories.link_image_sample(conn, image_row_id, sample_row_id)
        for ann in image.cell_type_annotations:
            repositories.link_image_cell_type(conn, image_row_id, annotation_row_ids[id(ann)])
        image_row_ids.append((image_row_id, internal_id))
    conn.commit()
    return image_row_ids


def test_internal_ids_are_sequential_and_stable(conn, extraction) -> None:
    image_row_ids = _store(conn, extraction)
    internal_ids = sorted(internal_id for _, internal_id in image_row_ids)
    assert internal_ids == ["HPA_000001", "HPA_000002"]


def test_reimport_does_not_duplicate_rows(conn, extraction) -> None:
    _store(conn, extraction)
    _store(conn, extraction)  # simulate re-running the import

    image_count = conn.execute("SELECT COUNT(*) AS n FROM images").fetchone()["n"]
    gene_count = conn.execute("SELECT COUNT(*) AS n FROM genes").fetchone()["n"]
    antibody_count = conn.execute("SELECT COUNT(*) AS n FROM antibodies").fetchone()["n"]

    assert image_count == 2
    assert gene_count == 1
    assert antibody_count == 1


def test_image_joins_back_to_full_metadata(conn, extraction) -> None:
    _store(conn, extraction)

    row = conn.execute(
        """
        SELECT i.internal_id, g.gene_symbol, a.antibody_id, s.sex, s.age
        FROM images i
        JOIN image_genes ig ON ig.image_id = i.id
        JOIN genes g ON g.id = ig.gene_id
        JOIN image_antibodies ia ON ia.image_id = i.id
        JOIN antibodies a ON a.id = ia.antibody_id
        JOIN image_samples isamp ON isamp.image_id = i.id
        JOIN samples s ON s.id = isamp.sample_id
        WHERE i.internal_id = 'HPA_000001'
        """
    ).fetchone()

    assert row["gene_symbol"] == "IVL"
    assert row["antibody_id"] == "CAB002243"
    assert row["sex"] == "Female"

    cell_types = conn.execute(
        """
        SELECT tca.cell_type FROM image_cell_types ict
        JOIN tissue_cell_annotations tca ON tca.id = ict.tissue_cell_annotation_id
        JOIN images i ON i.id = ict.image_id
        WHERE i.internal_id = 'HPA_000001'
        """
    ).fetchall()
    assert {r["cell_type"] for r in cell_types} == {"Glandular cells", "Squamous epithelial cells"}


def test_list_pending_images_and_status_counts(conn, extraction) -> None:
    image_row_ids = _store(conn, extraction)

    pending = repositories.list_pending_images(conn)
    assert {row["internal_id"] for row in pending} == {"HPA_000001", "HPA_000002"}

    counts = repositories.count_images_by_status(conn)
    assert counts == {"pending": 2}

    first_id, _ = image_row_ids[0]
    repositories.update_download_status(
        conn,
        first_id,
        local_path="/tmp/HPA_000001.jpg",
        width=100,
        height=100,
        original_format="JPEG",
        file_size=1234,
        download_status="downloaded_converted",
        download_date="2026-09-25T00:00:00+00:00",
    )
    conn.commit()

    pending_after = repositories.list_pending_images(conn)
    assert {row["internal_id"] for row in pending_after} == {"HPA_000002"}
    assert repositories.count_images_by_status(conn) == {
        "pending": 1,
        "downloaded_converted": 1,
    }


def test_mark_download_failed(conn, extraction) -> None:
    image_row_ids = _store(conn, extraction)
    first_id, internal_id = image_row_ids[0]

    repositories.mark_download_failed(conn, first_id)
    conn.commit()

    row = conn.execute(
        "SELECT download_status FROM images WHERE internal_id = ?", (internal_id,)
    ).fetchone()
    assert row["download_status"] == "failed"

    pending = repositories.list_pending_images(conn)
    assert internal_id in {r["internal_id"] for r in pending}
