#!/usr/bin/env nextflow
/*
 * fastq-qc: FastQC on every FASTQ file, then one MultiQC report.
 *
 * Input: a samplesheet (CSV) with columns sample, fastq_1, fastq_2 (fastq_2 empty for
 * single-end reads). In Cirro, .cirro/preprocess.py writes it from the input dataset.
 */

include { FASTQC  } from '../../modules/local/fastqc/main.nf'
include { MULTIQC } from '../../modules/local/multiqc/main.nf'

// Parameter defaults for this pipeline. Shared params (input, outdir) are in nextflow.config.
params.multiqc_title = null

workflow {
    if (!params.input)  error "--input (samplesheet CSV) is required"
    if (!params.outdir) error "--outdir is required"

    reads = channel.fromPath(params.input, checkIfExists: true)
        .splitCsv(header: true, strip: true)
        .map { row ->
            if (!row.sample)  error "samplesheet row has no 'sample': ${row}"
            if (!row.fastq_1) error "sample ${row.sample} has no 'fastq_1'"
            def files = [file(row.fastq_1, checkIfExists: true)]
            if (row.fastq_2) files << file(row.fastq_2, checkIfExists: true)
            [[id: row.sample, single_end: files.size() == 1], files]
        }

    FASTQC(reads)

    MULTIQC(
        FASTQC.out.zip.map { _meta, zips -> zips }.flatten().collect(),
        params.multiqc_title ?: ''
    )

    FASTQC.out.versions.mix(MULTIQC.out.versions)
        .map { f -> f.text }
        .unique()
        .collectFile(name: 'software_versions.yml', storeDir: "${params.outdir}/pipeline_info")
}
