# Content Forge --- Configuration & Execution Specification

Version: 1.0

This document defines the authoritative execution contract for Content
Forge.

------------------------------------------------------------------------

## 1. Philosophy

Balanced strict compiler:

-   Missing references → FAIL
-   Zero staged playbooks → FAIL
-   Platform/external references → WARN (configurable)
-   Diff explosion beyond threshold → FAIL

------------------------------------------------------------------------

## 2. Required Environment Variables

  Variable            Description
  ------------------- ---------------------------------
  INGEST_SUBMISSION   Submission ID (e.g., user)
  TARGET_PACK         Target pack in secops-framework
  STAGING_PACK        Staging pack name

Execution must fail if `INGEST_SUBMISSION` is missing.

------------------------------------------------------------------------

## 3. Optional Environment Variables

  Variable              Default   Description
  --------------------- --------- ------------------------------------------
  APPLY                 false     Apply changes instead of dry-run
  FORCE                 false     Override non-critical warnings
  MAX_DIFF_THRESHOLD    50        Maximum allowed changes before fail
  STRICT_GRAPH_MODE     false     Treat platform/external refs as failures
  ALLOW_PLATFORM_REFS   true      Allow platform references
  ALLOW_EXTERNAL_REFS   true      Allow external references

------------------------------------------------------------------------

## 4. Directory Contract

Ingest:

`/workspace/ingest/<submission_id>/`

Outputs:

`/workspace/output/submissions/<submission_id>/`

------------------------------------------------------------------------

## 5. Failure Conditions

Execution fails if:

-   INGEST_SUBMISSION missing
-   Zero staged playbooks
-   missing_refs \> 0
-   Integrity failure
-   diff_count \> MAX_DIFF_THRESHOLD
-   Strict mode violations

------------------------------------------------------------------------

## 6. Receipt Contract

`acceptance_receipt.json` must include:

-   submission id
-   apply boolean
-   doctor_counts including staged_playbooks, missing_refs,
    platform_refs, external_refs
