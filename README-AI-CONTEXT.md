# Content Forge --- AI Context Primer

This file is designed to quickly restore context for an AI assistant.

------------------------------------------------------------------------

## What This Is

Content Forge is a Dockerized SOC content compiler pipeline for
XSIAM/XSOAR packs.

It accepts playbooks, stages them, validates dependencies, normalizes
IDs, generates diffs, and prepares content for PR.

------------------------------------------------------------------------

## Required Contract

Submission runs require:

`INGEST_SUBMISSION=<submission_id>`

------------------------------------------------------------------------

## Command Set

-   `doctor`: analyze
-   `fix`: safe rewrites
-   `promote`: diff/promotion
-   `accept`: full pipeline

------------------------------------------------------------------------

## Debug Checklist

1.  Verify INGEST_SUBMISSION is set
2.  Verify ingest dir exists: `/workspace/ingest/<id>/`
3.  Check `staged_playbooks` in `acceptance_receipt.json`
4.  Inspect `doctor_report.json` and `promotion_diff.json`
