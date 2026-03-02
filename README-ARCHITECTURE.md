# Content Forge --- Architecture & Internals

This document explains internal structure and flow.

------------------------------------------------------------------------

## Execution Model

All submission runs require:

`INGEST_SUBMISSION=<submission_id>`

------------------------------------------------------------------------

## Pipeline Flow

Stage → Doctor → Fix → Promote → Integrity → Receipt

------------------------------------------------------------------------

## Stage

Source:

`/workspace/ingest/<submission_id>/`

Destination (staging pack):

`Packs/<staging_pack>/Playbooks/`

Hard rule: `staged_playbooks == 0` must fail.

------------------------------------------------------------------------

## Doctor

Checks:

-   Missing references
-   Platform references
-   External references
-   Dependency graph integrity

Outputs: `doctor_report.json`

------------------------------------------------------------------------

## Fix

Deterministic mechanical rewrites only.

Outputs include:

-   `fix_validate_output.txt`
-   `dependent_rewrite_changes.json`

------------------------------------------------------------------------

## Promote

Diff staged artifacts against target pack.

Outputs:

-   `promotion_diff.json`
-   `semantic_diff.json`

------------------------------------------------------------------------

## Integrity

Validates graph and pack consistency.

Output: `integrity_report.json`
