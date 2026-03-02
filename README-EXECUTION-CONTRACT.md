# Content Forge --- Execution Contract

This document describes the runtime contract between:

-   contributor inputs (ingest)
-   generated artifacts (output)
-   pipeline steps

------------------------------------------------------------------------

## Inputs

A submission is identified by:

`INGEST_SUBMISSION=<submission_id>`

Expected input directory:

`/workspace/ingest/<submission_id>/`

Accepted file types for MVP:

-   `*.yml`
-   `*.yaml`

------------------------------------------------------------------------

## Outputs

A run produces artifacts under:

`/workspace/output/submissions/<submission_id>/`

Minimum expected artifacts:

-   `doctor_report.json`
-   `promotion_diff.json`
-   `integrity_report.json`
-   `acceptance_receipt.json`

------------------------------------------------------------------------

## Step Semantics

### doctor

Analyzes staged content against target pack and emits
`doctor_report.json`.

### fix

Applies safe mechanical rewrites and emits validate output / rewrite
change reports.

### promote

Generates diffs and (when apply=true) copies artifacts into the real
pack.

### accept

Runs doctor → fix → promote + integrity checks and writes an acceptance
receipt.
