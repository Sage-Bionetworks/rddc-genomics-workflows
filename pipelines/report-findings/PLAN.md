# report-findings: plan

Working plan for the genetic-test-report pipeline described in the RDDC harmonization
whitepaper ("Genomic data: genetic test reports to normalized findings"). It turns the report
documents and structured results of a deposited batch into HL7 FHIR Genomics Reporting records,
GA4GH VRS representations where a variant can be resolved, field-level provenance, and a review
queue. Status: M0 done (2026-11-14); M1 next.

## Approach

No existing tool is a drop-in. GENETEX needs per-report interaction; GR-PROMPT is a prompt and a
study-specific JSON format tested on synthetic cancer reports; GIF's code availability and
portability across laboratories are unverified; Ask2Me VarHarmonizer covers normalization only.
The pipeline takes the useful idea from each and makes them check each other:

1. **Rules detector** (GIF's rules, GENETEX's patterns as seeds, subject to license): candidate
   HGVS strings, accessions, HGNC symbols, zygosity and classification terms with character spans;
   section labels (results, family history, methodology/examples, limitations).
2. **Model extractor** (GR-PROMPT's document extraction): fills `ReportRecord`, and every value
   must cite `{page, verbatim quote}`. It may read page images as well as text.
3. **Deterministic verifier**: quotes must occur in the extracted text; values must be derivable
   from their quote; every results-section HGVS candidate must be accounted for; nothing may come
   from family-history or example sections. Fields are `verified`, `unverified` or `conflict`;
   anything not verified goes to review.

`--extractor rules` runs the rules alone. It is the baseline for the comparison in the whitepaper
and lets the pipeline run end to end before the model-hosting decision.

## Input: the batch's Croissant sidecar

The pipeline reads the batch's `_sidecar.json` (rddc-model), not a samplesheet.

| Needed | From the sidecar |
| --- | --- |
| Report key | `distribution[].@id` (`urn:uuid:<file_id>`); changed content gets a new ID |
| What to process | `additionalType`: `rddc:ClinicalDocumentFile` with `documentType: genetic_report` (extraction path); `rddc:GeneticTestResultFile` (structured path) |
| Format | `encodingFormat`, `compression` |
| Location, integrity | `contentUrl` resolved against the sidecar's location; `md5` (required), `sha256` (optional) |
| Subjects | file `subjectIds`; `idSystem` from the header's `subjects[]` |
| Results file → PDF | `GeneticTestResultFile.reportDocuments` |
| Batch context | `sourceId`, `batchId`, `contributorId`, `sensitivity`, `conformsTo` |

Rules:

- `ClinicalDocumentFile`s without `documentType` are skipped and listed in the intake report;
  `--include_untyped_documents` sends them to extraction. A batch with nothing to process ends
  with an empty summary.
- A `GeneticTestResultFile` is the primary source for its reports; the PDFs it names in
  `reportDocuments` are linked as evidence, not extracted again.
- One `subjectId` on a file: findings belong to that subject. Several: the extractor must
  attribute each finding to one of the listed IDs, or the finding goes to review as
  `unattributed_subject`. Subject IDs are never invented.
- The laboratory is not in the sidecar. It is an optional field extracted from the report text.
- The `synthetic` flag is not read. Synthetic and real batches take the same path, including
  local validation; there are no external-service shortcuts for test data.

## Stages

| Stage | Does |
| --- | --- |
| `SIDECAR_INTAKE` (subworkflow, shared) | parse sidecar, resolve and stage files, check checksums, emit `[meta, file]` |
| `LAYOUT_EXTRACT` | document JSON: pages, blocks, tables, character offsets (Docling / PyMuPDF; Tesseract for scans) |
| `DETECT_RULES` | candidate spans and section labels |
| `EXTRACT_FINDINGS` | `--extractor rules\|llm` → `ReportRecord` with evidence per value |
| `MAP_STRUCTURED` | `GeneticTestResultFile` → `ReportRecord` (LinkML-Map) |
| `VERIFY` | grounding, attribution, LinkML validation |
| `VALIDATE_HGVS` | biocommons `hgvs` against local reference data |
| `NORMALIZE_VRS` | vrs-python, validated descriptions only |
| `BUILD_FHIR` | Genomics Reporting resources (below) |
| `VALIDATE_FHIR` | optional HL7 validator jar with the Genomics Reporting package |
| `REVIEW_QC` | `exceptions.jsonl` with reason codes, per-report HTML, coverage with unresolved counts |
| `EVALUATE` | optional field-level precision/recall and attribution accuracy against truth |

**`ReportRecord`** (LinkML, local to this pipeline, like `RegistryRecord` in the registry
prototype): report context (laboratory (optional), date, version/amendment, test scope and genes
studied, specimen, method, limitations); result status (positive, negative, inconclusive, failed,
not reported); findings (gene, original description, accession, zygosity, the laboratory's
classification and its date, supporting text, subject); evidence on every value; parser, model and
reference-data versions.

**FHIR**: `DiagnosticReport` (genomics report) with `subject` from the sidecar subject and
`idSystem`; `DocumentReference` to the original file (`@id`, `contentUrl`, md5/sha256);
overall-interpretation Observation (negative/inconclusive/failed results); region-studied
Observations (test scope); variant Observations; diagnostic-implication Observations (the
laboratory's classification); `Provenance` with text spans, the sidecar `@id` and `batchId`.
Outputs are published under `<file_id>/`.

**Normalization policy**: only descriptions with a versioned accession that validates are
normalized. Missing transcript version, or gene + `c.` without an accession, becomes
`unresolved:<reason>`; no MANE or default-assembly guess. A `p.`-only description becomes a
protein-level VRS Allele only when a protein accession is given, and is never treated as a genomic
allele.

**Review loop**: versioned `review_decisions.yaml`, keyed by file `@id` + field path, applied on
reruns; each decision records reviewer and reason.

## Reference data

All validation and normalization uses local reference data, in tests as in production.

- Transcript alignments (what UTA holds) are exported to a file-based store, so no Postgres server
  runs in CI or Cirro. Tests use a subset covering the fixture transcripts; production uses the
  full export, staged as a Cirro reference dataset.
- Sequences: production uses a SeqRepo directory, staged the same way. Tests use transcript and
  protein sequences plus genomic windows around fixture variants, with the full-sequence GA4GH
  digests precomputed so VRS identifiers are the real ones.
- Releases: UTA `uta_20241220` with SeqRepo `2024-12-20` (README, "Expected versions").
- The same `hgvs` data provider and VRS data proxy classes serve both; only the files differ.
  Build-time access to public UTA and NCBI fetches reference data only, never report content.

## Code layout

`-main-script pipelines/<name>/main.nf` does not put the repo's `bin/` on the task PATH, and
module binaries need a shared work directory or Wave (Cirro uses AWS Batch with S3). The Python
code is therefore a package, `rddc_reports`, in its own pinned container image:

```
containers/rddc-reports/      Dockerfile, pyproject.toml, src/rddc_reports/, tests/ (pytest)
modules/local/<stage>/        one process per stage, calling `rddc-reports <command>`
subworkflows/local/sidecar_intake/
pipelines/report-findings/    main.nf, README.md, CHANGELOG.md, PLAN.md, schema/, .cirro/
tests/report-findings/        synthetic batch: _sidecar.json, reports, truth, reference subset
```

## Milestones

- **M0, plumbing (done).** `rddc-reports` package and image; local reference store with hgvs
  provider and VRS proxy, and `normalize` applying the policy above; `SIDECAR_INTAKE` and a
  `main.nf` that routes a batch and writes `intake/intake.tsv`; Makefile and CI. Findings:
  - The subset store reproduces hgvs-on-live-UTA projections and full-sequence VRS IDs for
    BRCA1 (minus strand) and CFTR (plus strand): SNVs, del, dup, intronic, protein.
  - vrs-python's `HgvsTools` silently connects to public UTA and fetches NCBI sequences;
    `LocalAlleleTranslator` and `forbid_network_reference()` close that, and the tests run
    with `--network none`.
  - The `p.(…)` form resolves with `predicted=True`; uncertain `c.`/`g.` positions do not.
  - rddc-sidecar 0.1.0 vendors a model without `GeneticTestResultFile`/`documentType`, so the
    fixture sidecar is written by `make_sidecar.py` and checked against rddc-model's schema.
  - SeqRepo `2024-12-20` (full snapshot) gives the same projections and VRS IDs as the subset
    (`make py-test-seqrepo`, no network).
  - Full UTA export (`refdata export`, 148,465 transcripts, 341 MB, ~3 min) gives the same
    results with SeqRepo as the subset; reference data reaches Cirro runs as a dataset of the
    `rddc-variation-reference` type (Cirro reference types cannot hold it); `REFDATA_CHECK`
    verifies it at the start of every run.
  - Still open: first Cirro run (Sage Bionetworks project on app.cirro.bio while rddc-dev is not
    ready); publishing the image to GHCR; Nextflow version supported by Cirro.
- **M1, target first.** `ReportRecord` schema; synthetic report generator (templates → PDF, with
  truth): 3–4 layouts, results in tables and prose, negative/VUS/failed/amended reports,
  family-history and methodology-example distractors, protein-only and unversioned descriptions,
  a multi-subject report, rasterized and degraded copies; real ClinVar variants; a sidecar that
  passes rddc-sidecar validation; `EVALUATE`. Check licenses and availability of the GR-FORMAT
  (100) and benchmark-preprint (200) synthetic sets.
- **M2, deterministic end to end, no model.** Born-digital layout, rules detector and extractor,
  verify, HGVS, VRS, FHIR, review queue, structured path. CI stub and full runs.
- **M3, model extractor and comparison.** Model extractor with grounding checks; OCR path;
  rules vs model on throughput, cost per report and share needing review; held-out layouts.
- **M4, integration.** FHIR validator, `.cirro/`, `processes/rddc-genomics-report-findings.yaml`
  in rddc-cirro-config, tag `report-findings-v0.1.0`.
- **M5, real reports.** Governed, expert-annotated reports, outside this repo.

## Open decisions

1. Where model calls run (same policy for every batch): a hosted model inside the Cirro AWS
   account, a self-hosted open-weights model, or rules only until governance is settled.
2. Staging of full reference data (UTA export, SeqRepo) as Cirro reference datasets.
3. FHIR ↔ VRS link: a coding with a VRS system URI on the variant Observation, or an extension.
4. Cirro data types for the input batch and the FHIR output dataset.
5. Generalizing the root `params.input` (a samplesheet) now that this pipeline takes `--sidecar`.
