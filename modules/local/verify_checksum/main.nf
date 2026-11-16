// Check a staged file against the md5 (required) and sha256 (optional) in its sidecar entry.
// Prints "ok" or "mismatch:<algorithm>"; the caller routes mismatches to the exception list
// instead of failing the run.
process VERIFY_CHECKSUM {
    tag "${meta.id}"
    label 'process_single'
    container 'ghcr.io/sage-bionetworks/rddc-reports:0.1.0.dev0'

    input:
    tuple val(meta), path(data)

    output:
    tuple val(meta), path(data), stdout, emit: checked

    script:
    def sha = meta.sha256 ?: ''
    """
    status=ok
    [ "\$(md5sum '${data}' | cut -d' ' -f1)" = "${meta.md5}" ] || status=mismatch:md5
    if [ "\$status" = ok ] && [ -n "${sha}" ]; then
        [ "\$(sha256sum '${data}' | cut -d' ' -f1)" = "${sha}" ] || status=mismatch:sha256
    fi
    printf '%s' "\$status"
    """

    stub:
    """
    printf ok
    """
}
