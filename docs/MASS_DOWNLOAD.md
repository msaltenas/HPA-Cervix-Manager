# Mass Download (Phase 11) — Strategy A, two-phase, multi-Mac workflow

This documents the architecture decision from the Phase 11 planning discussion
and how to actually run it. See `docs/HPA_DATA_SOURCE.md` for the underlying
HPA data model.

## Decision: Strategy A (bulk export), not per-gene fetching

We compared downloading `proteinatlas.xml.gz` (the official genome-wide bulk
export) against fetching each gene's `.xml` individually. Verified with real
HPA data:

- **Coverage**: Cervix is part of HPA's standard normal-tissue IHC panel —
  essentially every antibody-profiled gene has Cervix images, *not* just the
  genes highlighted on the Cervix tissue overview page. Confirmed by fetching
  unrelated genes (GAPDH, ACTB, TP53, EGFR, INS) and finding 9–40 real Cervix
  images each. A gene-list scraped from the tissue page would have missed
  all of them. The relevant population is ~13,603 genes (HPA homepage:
  *"protein data covers 15312 genes"*, and more specifically *"13603 genes
  (67%)"* for the tissue/IHC atlas).
- **Requests**: bulk = 1 request (resumable via HTTP Range, verified
  `Accept-Ranges: bytes`). Per-gene = ~13,600 requests.
- **Size**: bulk = 730 MB compressed (verified via `curl -I`), ~15–30 GB
  decompressed (extrapolated from real per-gene file sizes).
- **Reproducibility**: the bulk file is a single atomic, dated snapshot
  (`Last-Modified` header). Per-gene fetching across ~13,600 requests risks
  spanning a version boundary mid-scrape.
- **Server load**: 1 long connection vs. ~13,600 short ones — bulk is the
  official, HPA-sanctioned way to consume data at this scale.

Full comparison, request/size estimates and risks are in the conversation
history; this file documents the resulting implementation.

## Two phases, deliberately decoupled

Because the actual image files (potentially **100,000+ images**, extrapolated
at several hundred GB) are meant to be downloaded on a different Mac than the
one used for development, the pipeline is split into two independent steps
that only share the SQLite database:

### Phase A — metadata sync (`scripts/sync_cervix_metadata.py`)

Runs anywhere. Downloads/resumes the bulk XML, streams it through
`xml.etree.ElementTree.iterparse` (each `<entry>` is cleared after
processing, so memory stays bounded regardless of file size — no need for
lxml), and upserts every Cervix image's full metadata (gene, antibody,
tissue-cell annotations, sample/patient, image URL) into
`metadata/hpa_cervix.sqlite` with `download_status='pending'`. **No image
bytes are downloaded in this step.**

```bash
python scripts/sync_cervix_metadata.py --data-dir /path/to/HPA_Cervix
# for a bounded test run instead of the full genome:
python scripts/sync_cervix_metadata.py --data-dir /path/to/HPA_Cervix --limit-genes 300
```

Safe to re-run: the bulk file is cached (`cache/proteinatlas.xml.gz` +
`.meta.json` sidecar with ETag/size) and only re-downloaded if HPA published
a new version; SQLite upserts never create duplicates (see
`docs/HPA_DATA_SOURCE.md` and the `UNIQUE` constraints in
`src/database/database.py`).

### Phase B — image build (`scripts/download_pending_images.py`)

Meant to run on **the machine that actually holds the data folder** (the
"anderer PC" from the original request — e.g. a Mac with an iCloud
Drive-synced `HPA_Cervix/images/` folder and enough disk space). Reads
`images` rows with `download_status != 'downloaded_converted'`, downloads
each `original_url`, converts to a real JPEG via Pillow (`src/images/converter.py`,
quality 95, alpha flattened to white), and updates the row.

```bash
python scripts/download_pending_images.py --data-dir /path/to/HPA_Cervix --workers 2
# for a bounded test:
python scripts/download_pending_images.py --data-dir /path/to/HPA_Cervix --limit 50
```

Safe to interrupt and re-run — already-converted images are skipped;
failures are marked `download_status='failed'` and retried on the next run
(`repositories.list_pending_images` treats anything other than
`'downloaded_converted'` as pending). Default concurrency is intentionally
low (`--workers 2`) to stay polite to HPA's server.

## Running this on a second Mac

1. `git clone`/`git pull` this repository.
2. `python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
3. Point `--data-dir` at the shared data folder (e.g. the iCloud Drive path),
   or set `HPA_CERVIX_DATA_DIR` / use `src/config/settings.py`'s persisted
   config once the GUI folder picker exists (Phase 7+).
4. If `metadata/hpa_cervix.sqlite` isn't already there (e.g. via iCloud
   sync), copy it over from the machine that ran Phase A, or run Phase A
   again on this machine — either way, Phase A is idempotent.
5. Run `scripts/download_pending_images.py` here.

Per the original master-prompt guidance (section 30): don't rely on the same
SQLite file being opened concurrently from two devices at once. Run Phase A
on one machine at a time; Phase B can run on whichever machine is currently
downloading images.

## Real numbers from a completed full run (2026-09-25, HPA version 25.1)

A full, untruncated `sync_cervix_metadata.py` run (no `--limit-genes`) was
actually executed against the live HPA server to validate this architecture
end-to-end, not just estimated:

- Bulk download: 730 MB (729,899,935 bytes) in ~56 s.
- Streaming parse of the full ~15,291-gene file: ~3.5 minutes total
  (download + parse), sustained ~75 genes/s.
- **15,291 genes** with real Cervix IHC data found (vs. the ~13,603
  extrapolated from the homepage statistic beforehand — the real number,
  measured directly, is what matters).
- **55,139 unique Cervix images**, referenced via **59,137** image↔gene
  associations — the ~4,000-row gap is not a bug: **1,993 images are
  legitimately shared by more than one gene** (multi-target antibodies),
  a real-world confirmation of the `image_genes` junction-table design
  (see docs/HPA_DATA_SOURCE.md, section 7 "Mehrfachbeziehungen").
- **25,622 antibodies**, **39,106 tissue-cell annotations**, **55,139
  samples**.
- Resulting `metadata/hpa_cervix.sqlite`: **51 MB** (metadata only, no image
  bytes -- confirms this step is cheap enough to run and re-run anywhere).
- This is meaningfully lower than the earlier n=7-sample extrapolation
  (100,000–190,000 images) — the real figure, now measured, is ~55,000
  images. At the ~1.5 MB/JPEG observed in Phase 1–6, that is roughly
  **80 GB** of JPEGs for the complete dataset, not several hundred GB.
