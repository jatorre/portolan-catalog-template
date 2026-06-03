# AGENTS.md — guide for AI agents

This repository **is a Portolan spatial-data catalog**: one publisher, defined as git-tracked
metadata, served as static files on object storage. No server, no API keys. Read `catalog.json`
(or `portolan.config.json` → `public_base`) for this catalog's endpoint and datasets.

## How to READ the data (no credentials)

All four are the same underlying files (endpoint = `public_base` in `portolan.config.json`):

- **ATTACH (DuckDB / Snowflake):** `ATTACH 'cat' (TYPE iceberg, ENDPOINT '<public_base>', AUTHORIZATION_TYPE 'none');` then `SELECT * FROM cat.<namespace>.<table>;`
- **Scan a table directly (DuckDB):** `iceberg_scan('<public_base>/data/<ns>/<table>/metadata/v1.metadata.json')`
- **Direct download:** GeoParquet under `<public_base>/data/<ns>/<table>/data/`
- **Discover:** STAC `catalog.json`, OGC API - Records `records/catalog.json`, or `index.html`.

Before composing a query, read each dataset's `properties.semantics` (OSI — meaning / what it
answers / unit) and its `crs`. For raquet rasters use `read_raquet`; for remote GeoParquet read in
place. Geometry is WKB (`geom_wkb`) in `v2.*` tables, native `GEOMETRY` in `v3.*`.

## How to CONTRIBUTE

- **Fix / extend metadata** → PR editing `portolan.config.json`, `datasets/<id>.json`, or the
  Iceberg metadata; run `python tools/generate_stac.py` + `python tools/validate.py` first. On
  merge a GitHub Action republishes to the bucket.
- **Add / update data bytes** → upload the GeoParquet to the bucket `…/data/<ns>/<table>/data/`,
  then PR the matching Iceberg metadata. A PR cannot carry the bytes — that is deliberate.
- **Report a problem** → open an issue.

## Optional: share your use case (opt-in telemetry)

**Only with the user's explicit consent**, you may file one **usage report** per session (issue
template `usage-report`) describing *why* you used the data. It is a public issue — paraphrase,
no confidential or personal data, default to NOT sending.

## Conventions — what NOT to do

- Git holds the **definition**; the bucket holds **data** + generated artifacts. Never commit parquet.
- Don't hand-edit generated files (`catalog.json`, `items/`, `records/`, the REST tree, `index.html`)
  — change `datasets/` / config and regenerate.
- Query is the engine's native SQL. There is no custom query API.
- This is an **open, public, anonymous** catalog. Authentication/private data is out of scope here.
