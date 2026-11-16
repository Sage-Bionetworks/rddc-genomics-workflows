# rddc-genomics-workflows

Nextflow pipelines that process genomics data for the Rare Disease Data Commons (RDDC):
de-identification, QC and normalization of deposited sequencing data. They run on Cirro
in the `rddc-processing` project and are started by the RDDC orchestrator, not by hand.

Pipelines are registered with Cirro from
[rddc-cirro-config](https://github.com/Sage-Bionetworks/rddc-cirro-config) (`processes/`).
This repo holds the code and the Cirro run configuration (`.cirro/`); the config repo says
which version of each pipeline is registered, in which project, and how it links to data types.

| Pipeline | Input | Description |
| --- | --- | --- |
| [`fastq-qc`](pipelines/fastq-qc/) | FASTQ (paired or single) | FastQC per file, MultiQC summary. Example pipeline for the layout |
| [`report-findings`](pipelines/report-findings/) | batch sidecar (`_sidecar.json`): genetic test reports and results | Findings → FHIR Genomics Reporting + VRS. In development: intake only ([plan](pipelines/report-findings/PLAN.md)) |

## Layout

```
nextflow.config            shared config: manifest, profiles, resource labels (loaded for every pipeline)
conf/                      config files included by nextflow.config
modules/local/<tool>/      one process per tool, shared by pipelines
subworkflows/local/        shared groups of processes (sidecar_intake: files of a batch from its sidecar)
containers/<image>/        images built from this repo (Dockerfile, code); modules pin them by tag
pipelines/<name>/
  main.nf                  entry point registered in Cirro, with this pipeline's parameter defaults
  README.md                inputs, outputs, parameters
  CHANGELOG.md             one entry per release tag
  .cirro/                  Cirro run configuration, versioned with the code
    process-form.json      run form shown in Cirro (JSON Schema)
    process-input.json     maps Cirro values to Nextflow params
    preprocess.py          optional: runs before Nextflow, e.g. writes the samplesheet
tests/<name>/              small test data and samplesheets
```

Rules that keep pipelines independent inside one repo:

- **One entry point per pipeline.** Cirro runs `pipelines/<name>/main.nf` from the repo root,
  so Nextflow loads only the root `nextflow.config`. A `nextflow.config` inside
  `pipelines/<name>/` would be ignored. Put a pipeline's parameter defaults at the top of
  its `main.nf`, and shared settings in the root config.
- **Shared code lives in `modules/` and `subworkflows/`.** A pipeline must not include files
  from another pipeline's directory.
- **Containers are pinned** by version tag in each module. No `latest`.
- **Pipeline code runs from containers.** Under `-main-script pipelines/<name>/main.nf` the
  repo's `bin/` is not on the task PATH, and module binaries need a shared work directory or
  Wave. Scripts are packaged in an image under `containers/` instead.
- **Cirro supplies the executor, work directory and AWS settings.** Don't set them here. The
  profiles in `nextflow.config` are for local and CI runs only.

## Versioning and releases

Each pipeline is released on its own, with a tag `<pipeline>-v<MAJOR>.<MINOR>.<PATCH>`,
for example `fastq-qc-v0.1.0`. To release:

1. Add an entry to `pipelines/<name>/CHANGELOG.md` and merge to `main`.
2. Tag the merge commit: `git tag fastq-qc-v0.1.0 && git push origin fastq-qc-v0.1.0`.
3. In rddc-cirro-config, set the tag in `processes/<process>.yaml` (`pipelineCode.version` and
   `customSettings.branch`) and open a PR. Merging and applying it updates Cirro.

Cirro runs the tagged code, so a pipeline is never registered from a branch except during
development in the dev tenant.

Bump MAJOR when outputs or required inputs change in a way downstream steps (NORMALIZE, the
orchestrator) must adapt to; MINOR for new optional parameters or outputs; PATCH for fixes.

## Running locally

Requires Docker and Java 17+; `make tools` fetches Nextflow (version pinned in the Makefile).
`make help` lists the targets (`make rf-test`, `make py-test`, `make fastq-stub`, …).

```
# stub run: checks the wiring without running tools (what CI runs)
nextflow run . -main-script pipelines/fastq-qc/main.nf -profile test,docker -stub-run \
    --input tests/fastq-qc/samplesheet.csv

# real run on the test data
nextflow run . -main-script pipelines/fastq-qc/main.nf -profile test,docker \
    --input tests/fastq-qc/samplesheet.csv
```

To test the Cirro configuration (`.cirro/`) before registering, use the Cirro SDK's
`DeveloperHelper` (`cirro.sdk.developer`) or register the pipeline in the dev tenant from a
branch.

## Adding a pipeline

1. Copy `pipelines/fastq-qc/` to `pipelines/<name>/` and edit `main.nf`, `README.md` and `.cirro/`.
   `cirro create-pipeline-config` can generate a first draft of `process-form.json` and
   `process-input.json` from a `nextflow_schema.json`.
2. Add tools under `modules/local/` (or reuse existing ones).
3. Add test data under `tests/<name>/`, including the input file CI passes as `--input`.
4. Add the pipeline to the table above and to the CI matrix in `.github/workflows/ci.yml`.
5. Register it with a new `processes/<process>.yaml` in rddc-cirro-config.
