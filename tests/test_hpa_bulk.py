"""Tests for hpa.bulk streaming parser. No network access -- uses a gzipped fixture."""

import gzip
from pathlib import Path

import pytest

from hpa import bulk

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_bulk.xml"


@pytest.fixture
def gz_fixture(tmp_path) -> Path:
    """Gzip-compress the multi-entry XML fixture, mimicking the real bulk export's format."""
    gz_path = tmp_path / "sample_bulk.xml.gz"
    xml_bytes = FIXTURE_PATH.read_bytes()
    with gzip.open(gz_path, "wb") as f:
        f.write(xml_bytes)
    return gz_path


def test_iter_cervix_entries_only_yields_genes_with_cervix_images(gz_fixture: Path) -> None:
    extractions = list(bulk.iter_cervix_entries(gz_fixture))

    # NOCERVIXGENE must be parsed and discarded, never yielded.
    gene_symbols = {e.gene.gene_symbol for e in extractions}
    assert gene_symbols == {"IVL", "ASRGL1"}


def test_iter_cervix_entries_preserves_per_gene_data(gz_fixture: Path) -> None:
    extractions = {e.gene.gene_symbol: e for e in bulk.iter_cervix_entries(gz_fixture)}

    ivl = extractions["IVL"]
    assert len(ivl.images) == 1
    assert ivl.images[0].hpa_image_id == "CAB002243/6008_B_9_3"
    assert ivl.gene.ensembl_id == "ENSG00000163207"

    asrgl1 = extractions["ASRGL1"]
    assert len(asrgl1.images) == 1
    assert asrgl1.images[0].hpa_image_id == "HPA029725/62802_B_9_3"
    glandular = next(
        a for a in asrgl1.cell_type_annotations if a.cell_type == "Glandular cells"
    )
    assert glandular.staining_level == "high"


def test_iter_cervix_entries_is_a_generator_not_a_list(gz_fixture: Path) -> None:
    result = bulk.iter_cervix_entries(gz_fixture)
    assert hasattr(result, "__next__"), "must be a lazy generator for memory-bounded parsing"
