"""Tests for hpa.parser against a real (trimmed) HPA XML fixture. No network access."""

from pathlib import Path

import pytest

from hpa import parser

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_gene.xml"


@pytest.fixture
def xml_text() -> str:
    return FIXTURE_PATH.read_text()


def test_parse_gene_entry(xml_text: str) -> None:
    gene = parser.parse_gene_entry(xml_text)
    assert gene.ensembl_id == "ENSG00000163207"
    assert gene.gene_symbol == "IVL"
    assert gene.hpa_version == "25"
    assert gene.entry_url == "https://v25.proteinatlas.org/ENSG00000163207"


def test_extract_cervix_data_only_returns_cervix(xml_text: str) -> None:
    extraction = parser.extract_cervix_data(xml_text)

    # The fixture also contains a Colon data block; it must be excluded.
    assert all(img.tissue == "Cervix" for img in extraction.images)
    assert all(ann.tissue == "Cervix" for ann in extraction.cell_type_annotations)


def test_extract_cervix_data_image_count_and_ids(xml_text: str) -> None:
    extraction = parser.extract_cervix_data(xml_text)

    assert len(extraction.images) == 2
    hpa_image_ids = {img.hpa_image_id for img in extraction.images}
    assert hpa_image_ids == {
        "CAB002243/6008_B_9_3",
        "CAB002243/6008_B_7_3",
    }


def test_extract_cervix_data_cell_type_annotations_shared_across_images(xml_text: str) -> None:
    extraction = parser.extract_cervix_data(xml_text)

    assert len(extraction.cell_type_annotations) == 2
    cell_types = {a.cell_type for a in extraction.cell_type_annotations}
    assert cell_types == {"Glandular cells", "Squamous epithelial cells"}

    squamous = next(
        a for a in extraction.cell_type_annotations if a.cell_type == "Squamous epithelial cells"
    )
    assert squamous.staining_level == "high"
    assert squamous.intensity_level == "strong"
    assert squamous.quantity == ">75%"

    # Both cervix images share the same two cell-type annotations
    # (HPA reports staining per antibody+tissue block, not per photo).
    for image in extraction.images:
        assert len(image.cell_type_annotations) == 2
        assert {a.cell_type for a in image.cell_type_annotations} == cell_types


def test_extract_cervix_data_patient_and_sample_metadata(xml_text: str) -> None:
    extraction = parser.extract_cervix_data(xml_text)

    image = next(img for img in extraction.images if img.hpa_patient_id == "1895")
    assert image.sex == "Female"
    assert image.age == 46
    assert image.snomed_tissue_description == "Cervix"
    assert image.snomed_code == "T-83000"
    assert image.image_url == "https://images.proteinatlas.org/2243/6008_B_9_3.jpg"
    assert image.image_url_tif == "https://images.proteinatlas.org/2243/6008_B_9_3.tif"
    assert image.image_type == "sampleImage"


def test_extract_cervix_data_antibodies_all_included(xml_text: str) -> None:
    extraction = parser.extract_cervix_data(xml_text)
    assert len(extraction.antibodies) == 1
    assert extraction.antibodies[0].antibody_id == "CAB002243"
    assert extraction.antibodies[0].release_version == "1.2"
