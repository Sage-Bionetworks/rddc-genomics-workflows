// Check the run's reference data: expected UTA/SeqRepo releases, and known variants resolve to
// known VRS identifiers. Fails the run if not, since every later result would depend on it.
process REFDATA_CHECK {
    label 'process_single'
    container 'ghcr.io/sage-bionetworks/rddc-reports:0.1.0.dev0'
    publishDir "${params.outdir}/refdata", mode: 'copy'

    input:
    path refdata              // store (SQLite): alignments, and sequences for a test subset
    path seqrepo              // SeqRepo snapshot directory, or [] when the store has sequences

    output:
    path 'refdata_check.json', emit: report

    script:
    def sr = seqrepo ? "--seqrepo ${seqrepo}" : ''
    """
    rddc-reports refdata check --refdata ${refdata} ${sr} --out refdata_check.json
    """

    stub:
    """
    echo '{"ok": true, "stub": true}' > refdata_check.json
    """
}
