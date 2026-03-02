# Content Forge --- CLI Reference

Commands are executed via:

`python -m app.src.cli <command>`

------------------------------------------------------------------------

## accept

Runs the full pipeline.

Example:

``` bash
INGEST_SUBMISSION=user \
TARGET_PACK=soc-optimization-unified \
STAGING_PACK=soc-optimization-unified_ingest \
python -m app.src.cli accept
```

Flags:

-   `--apply`: perform real promotion into the repo
-   `--force`: override non-critical warnings (policy-dependent)

------------------------------------------------------------------------

## doctor

Runs analysis only.

``` bash
python -m app.src.cli doctor
```

------------------------------------------------------------------------

## fix

Runs safe rewrite engine + validation.

``` bash
python -m app.src.cli fix
```

------------------------------------------------------------------------

## promote

Generates diffs and (optionally) promotes into target pack.

``` bash
python -m app.src.cli promote
```
