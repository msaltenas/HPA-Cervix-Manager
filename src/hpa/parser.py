"""Parse HPA per-gene XML entries into structured cervix records.

Only the `tissueExpression[technology="IHC"][assayType="tissue"]` branch is
read for image data. The cancer branch (`cancerExpression`) is intentionally
ignored -- per the official XSD, cancer data blocks carry no per-image
patient/sample information (see docs/HPA_DATA_SOURCE.md, section 3).

Field-by-field mapping is documented in docs/HPA_DATA_SOURCE.md. Nothing
here invents values that are absent from the XML: missing optional fields
(e.g. patient age) become None / NULL, never a guessed default.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GeneEntry:
    ensembl_id: str
    gene_symbol: str
    entry_url: str
    hpa_version: str


@dataclass(frozen=True)
class AntibodyEntry:
    antibody_id: str
    release_version: str | None
    release_date: str | None
    rrid: str | None
    antigen_sequence: str | None


@dataclass(frozen=True)
class CellTypeAnnotation:
    antibody_id: str
    tissue: str
    tissue_organ: str | None
    tissue_ontology_terms: str | None
    cell_type: str
    staining_level: str | None
    intensity_level: str | None
    quantity: str | None
    location: str | None


@dataclass(frozen=True)
class ImageRecord:
    hpa_image_id: str
    antibody_id: str
    tissue: str
    image_type: str
    image_url: str
    image_url_tif: str | None
    hpa_patient_id: str | None
    sex: str | None
    age: int | None
    snomed_tissue_description: str | None
    snomed_code: str | None
    cell_type_annotations: list[CellTypeAnnotation] = field(default_factory=list)


@dataclass(frozen=True)
class CervixExtraction:
    gene: GeneEntry
    antibodies: list[AntibodyEntry]
    cell_type_annotations: list[CellTypeAnnotation]
    images: list[ImageRecord]


TARGET_TISSUE = "cervix"
TARGET_TECHNOLOGY = "IHC"
TARGET_ASSAY_TYPE = "tissue"
NORMAL_MORPHOLOGY_DESCRIPTION = "Normal tissue, NOS"


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    stripped = el.text.strip()
    return stripped or None


def _parse_levels(tissue_cell: ET.Element) -> tuple[str | None, str | None]:
    staining, intensity = None, None
    for level in tissue_cell.findall("level"):
        level_type = level.get("type")
        if level_type == "staining":
            staining = _text(level)
        elif level_type == "intensity":
            intensity = _text(level)
    return staining, intensity


def _parse_snomed(sample: ET.Element) -> tuple[str | None, str | None]:
    snomed_params = sample.find("snomedParameters")
    if snomed_params is None:
        return None, None
    entries = snomed_params.findall("snomed")
    if not entries:
        return None, None
    # Prefer the tissue-specific SNOMED entry over the generic
    # "Normal tissue, NOS" morphology code that accompanies every sample.
    for entry in entries:
        description = entry.get("tissueDescription")
        if description != NORMAL_MORPHOLOGY_DESCRIPTION:
            return description, entry.get("snomedCode")
    first = entries[0]
    return first.get("tissueDescription"), first.get("snomedCode")


def _gene_entry_from_element(entry: ET.Element) -> GeneEntry:
    identifier = entry.find("identifier")
    if identifier is None:
        raise ValueError("XML <entry> is missing its <identifier> element")
    return GeneEntry(
        ensembl_id=identifier.get("id"),
        gene_symbol=_text(entry.find("name")) or "",
        entry_url=entry.get("url"),
        hpa_version=entry.get("version"),
    )


def parse_gene_entry(xml_text: str) -> GeneEntry:
    """Parse gene identity from a single-gene XML document (the `<ENSEMBL_ID>.xml` endpoint)."""
    root = ET.fromstring(xml_text)
    entry = root.find("entry")
    if entry is None:
        raise ValueError("XML does not contain an <entry> element")
    return _gene_entry_from_element(entry)


def extract_cervix_data_from_entry(entry: ET.Element) -> CervixExtraction:
    """Extract Cervix IHC data from one already-parsed `<entry>` element.

    Shared by `extract_cervix_data` (single-gene document) and the bulk
    streaming parser (`hpa.bulk`, iterating `<entry>` elements out of the
    genome-wide `proteinatlas.xml.gz` export) so both paths apply identical
    extraction rules -- see docs/HPA_DATA_SOURCE.md.
    """
    gene = _gene_entry_from_element(entry)

    antibodies: list[AntibodyEntry] = []
    all_cell_annotations: list[CellTypeAnnotation] = []
    all_images: list[ImageRecord] = []

    for ab in entry.findall("antibody"):
        antibody_id = ab.get("id")
        antibodies.append(
            AntibodyEntry(
                antibody_id=antibody_id,
                release_version=ab.get("releaseVersion"),
                release_date=ab.get("releaseDate"),
                rrid=ab.get("RRID"),
                antigen_sequence=_text(ab.find("antigenSequence")),
            )
        )

        for tissue_expr in ab.findall("tissueExpression"):
            if tissue_expr.get("technology") != TARGET_TECHNOLOGY:
                continue
            if tissue_expr.get("assayType") != TARGET_ASSAY_TYPE:
                continue

            for data_block in tissue_expr.findall("data"):
                tissue_el = data_block.find("tissue")
                tissue_name = _text(tissue_el)
                if tissue_name is None or tissue_name.lower() != TARGET_TISSUE:
                    continue

                block_annotations: list[CellTypeAnnotation] = []
                for tissue_cell in data_block.findall("tissueCell"):
                    staining, intensity = _parse_levels(tissue_cell)
                    annotation = CellTypeAnnotation(
                        antibody_id=antibody_id,
                        tissue=tissue_name,
                        tissue_organ=tissue_el.get("organ"),
                        tissue_ontology_terms=tissue_el.get("ontologyTerms"),
                        cell_type=_text(tissue_cell.find("cellType")) or "",
                        staining_level=staining,
                        intensity_level=intensity,
                        quantity=_text(tissue_cell.find("quantity")),
                        location=_text(tissue_cell.find("location")),
                    )
                    block_annotations.append(annotation)
                all_cell_annotations.extend(block_annotations)

                for patient in data_block.findall("patient"):
                    sex = _text(patient.find("sex"))
                    age_text = _text(patient.find("age"))
                    age = int(age_text) if age_text is not None else None
                    patient_id = _text(patient.find("patientId"))

                    for sample in patient.findall("sample"):
                        snomed_desc, snomed_code = _parse_snomed(sample)
                        for assay_image in sample.findall("assayImage"):
                            for image in assay_image.findall("image"):
                                image_urls = [u.text for u in image.findall("imageUrl") if u.text]
                                if not image_urls:
                                    continue
                                tif_urls = [
                                    u.text for u in image.findall("imageUrlTif") if u.text
                                ]
                                image_url = image_urls[0]
                                filename_stem = image_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                                all_images.append(
                                    ImageRecord(
                                        hpa_image_id=f"{antibody_id}/{filename_stem}",
                                        antibody_id=antibody_id,
                                        tissue=tissue_name,
                                        image_type=image.get("imageType"),
                                        image_url=image_url,
                                        image_url_tif=tif_urls[0] if tif_urls else None,
                                        hpa_patient_id=patient_id,
                                        sex=sex,
                                        age=age,
                                        snomed_tissue_description=snomed_desc,
                                        snomed_code=snomed_code,
                                        cell_type_annotations=block_annotations,
                                    )
                                )

    return CervixExtraction(
        gene=gene,
        antibodies=antibodies,
        cell_type_annotations=all_cell_annotations,
        images=all_images,
    )


def extract_cervix_data(xml_text: str) -> CervixExtraction:
    """Extract all Cervix IHC tissue-expression data (images + annotations) from one gene's XML."""
    root = ET.fromstring(xml_text)
    entry = root.find("entry")
    if entry is None:
        raise ValueError("XML does not contain an <entry> element")
    return extract_cervix_data_from_entry(entry)
