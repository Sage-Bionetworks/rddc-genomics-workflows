# Changelog: report-findings

One entry per release tag (`report-findings-v<MAJOR>.<MINOR>.<PATCH>`).

## Unreleased

- Sidecar intake (shared `SIDECAR_INTAKE` subworkflow): files, subjects and checksums from the
  batch's `_sidecar.json`; routing to extract / structured / evidence / skipped / rejected;
  `intake/intake.tsv`.
- `rddc-reports` image 0.1.0.dev0: local reference-data store, full UTA export, HGVS validation
  and VRS normalization.
- `--refdata` / `--seqrepo` and `REFDATA_CHECK` (`refdata/refdata_check.json`).
- Cirro run configuration (`.cirro/`): batch input via `_sidecar.json`, reference data selected
  from an `rddc-variation-reference` dataset.
