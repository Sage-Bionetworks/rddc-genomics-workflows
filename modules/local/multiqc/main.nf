process MULTIQC {
    label 'process_low'
    publishDir "${params.outdir}/multiqc", mode: 'copy', pattern: 'multiqc_*'
    container 'quay.io/biocontainers/multiqc:1.25.1--pyhdfd78af_0'

    input:
    path inputs, stageAs: 'inputs/*'
    val title

    output:
    path 'multiqc_report.html', emit: report
    path 'multiqc_data',        emit: data
    path 'versions.yml',        emit: versions

    script:
    def title_arg = title ? "--title '${title}'" : ''
    """
    multiqc --force ${title_arg} --filename multiqc_report.html inputs/

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        multiqc: \$(multiqc --version | sed 's/^multiqc, version //')
    END_VERSIONS
    """

    stub:
    """
    touch multiqc_report.html
    mkdir multiqc_data
    printf '"%s":\\n    multiqc: stub\\n' "${task.process}" > versions.yml
    """
}
