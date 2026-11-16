process FASTQC {
    tag "${meta.id}"
    label 'process_low'
    publishDir path: { "${params.outdir}/fastqc/${meta.id}" }, mode: 'copy', pattern: '*_fastqc.*'
    container 'quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0'

    input:
    tuple val(meta), path(reads)

    output:
    tuple val(meta), path('*_fastqc.html'), emit: html
    tuple val(meta), path('*_fastqc.zip'),  emit: zip
    path 'versions.yml',                    emit: versions

    script:
    """
    fastqc --threads ${task.cpus} --quiet ${reads}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        fastqc: \$(fastqc --version | sed 's/^FastQC v//')
    END_VERSIONS
    """

    stub:
    """
    for f in ${reads}; do
        name=\$(basename "\$f" | sed -E 's/\\.(fastq|fq)(\\.gz)?\$//')
        touch "\${name}_fastqc.html" "\${name}_fastqc.zip"
    done
    printf '"%s":\\n    fastqc: stub\\n' "${task.process}" > versions.yml
    """
}
