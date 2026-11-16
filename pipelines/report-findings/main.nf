#!/usr/bin/env nextflow
/*
 * report-findings: genetic test reports → structured findings, HL7 FHIR Genomics Reporting
 * records and GA4GH VRS. See PLAN.md. M0: intake, routing and the reference-data check.
 *
 * Input: the batch's Croissant sidecar (--sidecar, _sidecar.json; rddc-model). Files are found
 * from it, not from a samplesheet:
 *   ClinicalDocumentFile, documentType genetic_report   → extract (text/layout, findings)
 *   GeneticTestResultFile                                 → structured (mapped directly)
 *   ClinicalDocumentFile named in reportDocuments         → evidence (linked, not extracted)
 *   anything else                                         → skipped, with a reason
 */

include { SIDECAR_INTAKE       } from '../../subworkflows/local/sidecar_intake/main.nf'
include { RDDC_REPORTS_VERSION } from '../../modules/local/rddc_reports_version/main.nf'
include { REFDATA_CHECK        } from '../../modules/local/refdata_check/main.nf'

// Parameter defaults for this pipeline. Shared params (outdir) are in nextflow.config.
params.sidecar                   = null    // _sidecar.json of the batch
params.include_untyped_documents = false   // also extract ClinicalDocumentFiles without documentType
params.refdata                   = null    // reference store (SQLite; rddc-reports refdata export)
params.seqrepo                   = null    // SeqRepo snapshot directory; not needed if the store has sequences

def route(Map meta, Set evidenceIds, boolean includeUntyped) {
    if (meta.additionalType == 'GeneticTestResultFile') {
        return ['structured', '']
    }
    if (meta.additionalType == 'ClinicalDocumentFile') {
        if (meta.id in evidenceIds) {
            return ['evidence', 'report_document_of_structured_results']
        }
        if (meta.documentType == 'genetic_report') {
            return ['extract', '']
        }
        if (meta.documentType == null) {
            return includeUntyped ? ['extract', 'untyped_document_included'] : ['skipped', 'no_document_type']
        }
        return ['skipped', "document_type_${meta.documentType}"]
    }
    return ['skipped', 'not_applicable_class']
}

def intakeRow(Map meta, String route, String reason) {
    return [meta.id, meta.name, meta.additionalType, meta.documentType ?: '', meta.encodingFormat ?: '',
            meta.subjectIds.join(';'), route, reason].join('\t') + '\n'
}

workflow {
    if (!params.sidecar) error "--sidecar (the batch's _sidecar.json) is required"
    if (!params.outdir)  error "--outdir is required"

    SIDECAR_INTAKE(file(params.sidecar, checkIfExists: true))

    // Reports named by verified structured results are evidence, not extraction inputs. If the
    // results file is rejected, its reports are extracted instead.
    evidence_ids = SIDECAR_INTAKE.out.files
        .filter { meta, _f -> meta.additionalType == 'GeneticTestResultFile' }
        .flatMap { meta, _f -> meta.reportDocuments }
        .toList()
        .map { ids -> ids as Set }

    routed = SIDECAR_INTAKE.out.files
        .combine(evidence_ids)
        .map { meta, f, ids ->
            def (r, reason) = route(meta, ids, params.include_untyped_documents as boolean)
            [meta + [route: r, route_reason: reason], f]
        }

    to_extract    = routed.filter { meta, _f -> meta.route == 'extract' }
    to_structured = routed.filter { meta, _f -> meta.route == 'structured' }
    to_extract.view    { meta, f -> "extract    ${meta.id} ${f.name} subjects=${meta.subjectIds}" }
    to_structured.view { meta, f -> "structured ${meta.id} ${f.name} evidence=${meta.reportDocuments}" }

    routed.map { meta, _f -> intakeRow(meta, meta.route, meta.route_reason) }
        .mix(SIDECAR_INTAKE.out.rejected.map { meta, reason -> intakeRow(meta, 'rejected', reason) })
        .collectFile(name: 'intake.tsv', storeDir: "${params.outdir}/intake", sort: true,
                     seed: "file_id\tname\tclass\tdocument_type\tencoding_format\tsubjects\troute\treason\n")

    SIDECAR_INTAKE.out.batch
        .map { b -> groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(b)) + '\n' }
        .collectFile(name: 'batch.json', storeDir: "${params.outdir}/intake")

    // Reference data for HGVS validation and VRS (README, "Expected versions"). Checked up
    // front; normalization (M2) will use the same inputs.
    if (params.refdata) {
        REFDATA_CHECK(
            file(params.refdata, checkIfExists: true),
            params.seqrepo ? file(params.seqrepo, checkIfExists: true, type: 'dir') : [],
        )
    }

    RDDC_REPORTS_VERSION()
    RDDC_REPORTS_VERSION.out.versions
        .map { f -> f.text }
        .collectFile(name: 'software_versions.yml', storeDir: "${params.outdir}/pipeline_info")
}
