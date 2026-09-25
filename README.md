# HPA Cervix Manager

A macOS desktop application to fetch Human Protein Atlas (HPA) cervix tissue
image metadata, download the associated immunohistochemistry (IHC) images,
convert them to real JPEGs, store all scientific metadata in a local SQLite
database, and browse images alongside their HPA metadata. Image markup
happens externally (e.g. on an iPad); this app only detects and displays
`<id>_marked.jpg` files once they appear in the data folder.

**Status:** Phase 1–6 (data-source investigation, SQLite schema, downloader,
JPEG conversion, verification) and Phase 11 metadata pipeline (bulk export
download + streaming parse + two-phase multi-Mac sync) complete. GUI
(PySide6) not yet implemented — see `docs/HPA_DATA_SOURCE.md` and
`docs/MASS_DOWNLOAD.md`.

## Project structure

```
docs/
  HPA_DATA_SOURCE.md      Required reading: HPA data model investigation
  MASS_DOWNLOAD.md         Phase 11 architecture: bulk export, two-phase multi-Mac workflow
src/
  hpa/
    client.py              Per-gene HTTP client (search + single-gene .xml)
    parser.py               XML -> structured records (shared by single-gene and bulk parsing)
    bulk.py                  Resumable bulk .xml.gz download + streaming (iterparse) parser
  database/                SQLite schema + upsert repositories
  images/                  Pillow-based JPEG conversion
  services/
    metadata_service.py    Shared "store one gene's extraction into SQLite" logic
  config/                  User-configurable data-folder location
  ui/                      (not yet implemented) PySide6 GUI
scripts/
  bootstrap_test.py         Phase 2-6 manual verification (10 images, per-gene endpoint)
  sync_cervix_metadata.py   Phase 11a: bulk download + parse -> SQLite metadata (runs anywhere)
  download_pending_images.py  Phase 11b: download+convert pending images (run where the data folder lives)
tests/               Fixture-based unit tests (no network access, run in CI)
```

## Code vs. data separation

This repository contains **only code**. Downloaded images, the SQLite
database, logs and exports live in a separate, user-chosen data directory
(e.g. an iCloud Drive folder) — see `src/config/settings.py`. Nothing under
`data/` or matching `*.jpg`/`*.sqlite`/etc. is committed (see `.gitignore`).

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest              # fixture-based tests, no network
ruff check src tests scripts
```

## Manual end-to-end verification (real HPA data)

```bash
python scripts/bootstrap_test.py --data-dir ./data --limit 10
```

Downloads 10 real Cervix IHC images (genes IVL, ASRGL1), converts them to
JPEG, stores full metadata in `./data/metadata/hpa_cervix.sqlite`, and
verifies that every DB row matches a real file on disk. This script is not
run in CI (see `.github/workflows/tests.yml`) since it makes real network
requests to proteinatlas.org.

## Mass download (Phase 11, real production data)

```bash
# Anywhere: download the bulk export (resumable) and sync ALL Cervix metadata into SQLite
python scripts/sync_cervix_metadata.py --data-dir /path/to/HPA_Cervix

# On the machine that should hold the actual image files:
python scripts/download_pending_images.py --data-dir /path/to/HPA_Cervix --workers 2
```

See `docs/MASS_DOWNLOAD.md` for the architecture decision (bulk export vs.
per-gene fetching), real measured numbers, and the multi-Mac workflow.

**Setting up the second Mac that will actually download the images?**
Follow `docs/SECOND_MAC_SETUP.md` — a step-by-step runbook (clone, venv,
copy over the metadata DB, run the download script). Prefer to have an
assistant walk you through it on that machine? Copy the prompt in
`docs/CHATGPT_SETUP_PROMPT.md`.

## Data source

See `docs/HPA_DATA_SOURCE.md` for the full investigation of HPA's official
data access methods, the Cervix data model, image identification scheme,
available/unavailable metadata, and known limitations.
