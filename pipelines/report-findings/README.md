# report-findings

Genetic test reports of a deposited batch → structured findings, HL7 FHIR Genomics Reporting
records and GA4GH VRS representations, with field-level provenance and a review queue.
**In development:** intake, routing and the reference-data check are implemented; extraction
and FHIR output are not.
See [PLAN.md](PLAN.md) for the design and milestones.

## Input

The batch's Croissant sidecar (`--sidecar`, `_sidecar.json`, rddc-model). There is no
samplesheet: files, formats, subjects and checksums come from the sidecar's `distribution`, and
each `contentUrl` is resolved against the sidecar's location.

| Route | Files |
| --- | --- |
| `extract` | `ClinicalDocumentFile` with `documentType: genetic_report` |
| `structured` | `GeneticTestResultFile` |
| `evidence` | a `ClinicalDocumentFile` named in a verified `GeneticTestResultFile`'s `reportDocuments`: linked, not extracted |
| `skipped` | other classes and document types; `ClinicalDocumentFile`s without `documentType` unless `--include_untyped_documents` |
| `rejected` | checksum mismatch, a `contentUrl` outside the batch, a file set without listed files |

Rejected and skipped files are listed with a reason; the run continues with the rest.

## Parameters

| Parameter | Default | Description |
| --- | --- | --- |
| `--sidecar` | | `_sidecar.json` of the batch |
| `--outdir` | | results directory; Cirro sets it to the new dataset |
| `--include_untyped_documents` | `false` | also extract `ClinicalDocumentFile`s without `documentType` |
| `--refdata` | none | reference store (SQLite): `uta_20241220.sqlite` from `rddc-reports refdata export`, or a test subset with sequences |
| `--seqrepo` | none | SeqRepo snapshot directory (`2024-12-20`); required with a full export, which holds no sequences |

## Output (M0)

```
intake/intake.tsv          one row per distribution item: route and reason
intake/batch.json          batch header (sourceId, batchId, contributorId, sensitivity, …)
refdata/refdata_check.json reference releases found, and known variants resolved (with --refdata)
pipeline_info/software_versions.yml
```

## Expected versions

Reference data and tools this version is built and tested against. UTA and SeqRepo are released
together by biocommons; use the pair with the same date. The reference data releases are set in
`containers/rddc-reports/src/rddc_reports/versions.py`, and a test checks that the committed
subset was built from them.

| Component | Version | Notes |
| --- | --- | --- |
| UTA (transcript alignments) | `uta_20241220` | test subset built from it on the public biocommons server; production needs a local export of the same release |
| SeqRepo (sequences) | `2024-12-20` | `rsync dl.biocommons.org::seqrepo/2024-12-20/` (13.5 GB); production reference data; `make py-test-seqrepo` checks it gives the same results as the subset |
| Genome assembly | GRCh38 | genomic projections and VRS Alleles; splign alignments |
| hgvs | 1.5.7 | biocommons; validation and projection |
| vrs-python (`ga4gh.vrs`) | 2.3.3 | VRS 2.x Allele identifiers (`ga4gh:VA.…`) |
| biocommons.seqrepo | 0.6.11 | reads the SeqRepo directory |
| rddc-reports image | 0.1.0.dev0 | `ghcr.io/sage-bionetworks/rddc-reports`; not yet published, `make image` builds it locally |
| Nextflow | 26.10.5 | pinned in the Makefile; Cirro's supported version still to be confirmed |
| rddc-model | `sidecar` branch, sidecar 0.1.0 | fixture sidecar validated against its generated JSON Schema |

Upgrading UTA/SeqRepo, hgvs or vrs-python: change `versions.py` (or the pins in
`pyproject.toml`), rebuild the subset (`make refdata-test`), run `make py-test-live` to compare
with live sources, and update this table and the expected values in
`containers/rddc-reports/tests/test_normalize.py`. A VRS identifier change is an output change
(MAJOR version bump).

## Reference data

`--refdata` and `--seqrepo` are checked before anything else (`REFDATA_CHECK`): the store must
be from the expected UTA release, the SeqRepo directory the expected snapshot, and three known
variants must resolve to their known VRS identifiers. The run fails otherwise.

- **Full store:** `rddc-reports refdata export --out uta_20241220.sqlite` copies every GRCh38
  splign alignment from UTA (148,465 transcripts, 1.6 million exon rows; 341 MB; about 3 minutes
  from the public server). It holds no sequences; pass `--seqrepo` too.
- **Test subset:** `tests/report-findings/refdata/subset.sqlite` (BRCA1, CFTR) holds sequence
  windows and needs no SeqRepo.

## Cirro

`.cirro/` holds the run configuration. The input dataset is a batch (`rddc-report-batch` data
type: the batch files with `_sidecar.json` at the root); `preprocess.py` passes the sidecar's
path. The run form selects the store file and the SeqRepo folder from a dataset of the
`rddc-variation-reference` data type, laid out as `uta_20241220.sqlite` +
`seqrepo/2024-12-20/…`. Cirro's own reference types are fixed (FASTA, BED, GTF, …) and flatten
uploads into one folder, so reference data travels as a dataset. Registrations are in
rddc-cirro-config (`processes/sage-test/` while testing on app.cirro.bio).

## Tests

`tests/report-findings/` holds a small synthetic batch (`batch/_sidecar.json`, validated against
rddc-model's JSON Schema by `make fixtures`), a copy with intake rejection cases
(`_sidecar.errors.json`), expected intake reports, and a reference-data subset for HGVS/VRS
(`refdata/`, BRCA1 NM_007294.4 and CFTR NM_000492.4 on GRCh38). `make rf-stub`, `make rf-test`
and `make py-test` run them; `make py-test-seqrepo` adds a SeqRepo snapshot (and, with
`REFDATA=<store>`, a full export).
