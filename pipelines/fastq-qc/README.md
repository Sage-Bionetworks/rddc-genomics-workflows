# fastq-qc

FastQC on every FASTQ file, and one MultiQC report for the dataset. It is the example
pipeline for this repo's layout and a basic QC step for deposited sequencing reads.

## Input

A samplesheet (`--input`, CSV):

| Column | Required | Description |
| --- | --- | --- |
| `sample` | yes | sample ID |
| `fastq_1` | yes | read 1 (or single-end) FASTQ, `.fastq.gz` |
| `fastq_2` | no | read 2 FASTQ; leave empty for single-end |

In Cirro, `.cirro/preprocess.py` writes the samplesheet from the input dataset, so the run
form has no input field. The dataset must be of a data type linked to this pipeline
(`rddc-fastq` in rddc-cirro-config).

## Parameters

| Parameter | Default | Description |
| --- | --- | --- |
| `--input` | | samplesheet (CSV) |
| `--outdir` | | results directory; Cirro sets it to the new dataset |
| `--multiqc_title` | none | title of the MultiQC report |

## Output

```
fastqc/<sample>/<file>_fastqc.{html,zip}
multiqc/multiqc_report.html
multiqc/multiqc_data/
pipeline_info/software_versions.yml
```
