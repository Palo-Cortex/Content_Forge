# Content Forge

Content Forge is a portable, Docker-based content engineering pipeline
for safely accepting, validating, fixing, and promoting XSIAM / XSOAR
content (playbooks, scripts, etc.) into the `secops-framework`
repository.

It takes content built in customer tenants and moves it into GitHub in a
controlled, deterministic, reproducible way.

------------------------------------------------------------------------

## Core Principles

1.  Submission-scoped execution (`INGEST_SUBMISSION` required)
2.  Deterministic staging (only submitted artifacts are staged/promoted)
3.  Dry-run by default
4.  Fully Docker portable

------------------------------------------------------------------------

## Directory Model

Host repository layout:

    workspace/
      ingest/<submission_id>/
      output/submissions/<submission_id>/
      secops-framework/

Inside the container these appear under `/workspace/...`.

------------------------------------------------------------------------

## Common Commands

All commands run inside the container.

### Full pipeline (recommended)

``` bash
INGEST_SUBMISSION=user \
TARGET_PACK=soc-optimization-unified \
STAGING_PACK=soc-optimization-unified_ingest \
python -m app.src.cli accept
```

### Individual steps

``` bash
python -m app.src.cli doctor
python -m app.src.cli fix
python -m app.src.cli promote
```

------------------------------------------------------------------------

## Outputs

Outputs are written to:

`/workspace/output/submissions/<submission_id>/`

Key artifacts:

-   `doctor_report.json`
-   `promotion_diff.json`
-   `semantic_diff.json`
-   `integrity_report.json`
-   `acceptance_receipt.json`
