// Versions of the rddc-reports image and the libraries it pins, for pipeline_info.
process RDDC_REPORTS_VERSION {
    label 'process_single'
    container 'ghcr.io/sage-bionetworks/rddc-reports:0.1.0.dev0'

    output:
    path 'versions.yml', emit: versions

    script:
    """
    rddc-reports version | python3 -c '
import json, sys
v = json.load(sys.stdin)
print("\\"${task.process}\\":")
for k, x in v.items():
    print(f"    {k}: {x}")
' > versions.yml
    """

    stub:
    """
    printf '"%s":\\n    rddc-reports: stub\\n' "${task.process}" > versions.yml
    """
}
