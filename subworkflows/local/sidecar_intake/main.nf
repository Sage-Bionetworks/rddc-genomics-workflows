/*
 * SIDECAR_INTAKE: the files of a batch, described by its Croissant sidecar (rddc-model).
 *
 * Reads _sidecar.json, resolves each FileObject's contentUrl against the sidecar's location
 * (local path or s3://), stages the file and checks its checksums. Pipelines choose what to
 * process from meta.additionalType and the other fields; nothing here is pipeline-specific.
 *
 * emit:
 *   files     [meta, file] for every FileObject whose checksums match
 *   rejected  [meta, reason] for entries that cannot be processed (checksum mismatch, a
 *             contentUrl outside the batch, a file set without listed files)
 *   batch     the batch header (map), once
 *
 * meta: id (file UUID), urn, name, contentUrl, additionalType (without "rddc:"),
 *       encodingFormat, compression, documentType, subjectIds, subjects ([subjectId, idSystem]
 *       for each subjectId), reportDocuments (file UUIDs), md5, sha256, batch (header map)
 */

include { VERIFY_CHECKSUM } from '../../../modules/local/verify_checksum/main.nf'

def stripUrn(String s) {
    return s?.startsWith('urn:uuid:') ? s.substring(9) : s
}

def batchHeader(Map doc, String location) {
    return [
        urn          : doc['@id'],
        name         : doc.name,
        sourceId     : doc.sourceId,
        batchId      : doc.batchId,
        contributorId: doc.contributorId,
        conformsTo   : doc.conformsTo instanceof List ? doc.conformsTo : [doc.conformsTo],
        sensitivity  : doc.sensitivity ?: [:],
        location     : location,
    ]
}

// One entry per distribution item: [meta, contentPath or null, problem or null].
def parseSidecar(sidecarPath) {
    def doc = new groovy.json.JsonSlurper().parseText(sidecarPath.text)
    if (!(doc instanceof Map) || !doc.distribution) {
        error "${sidecarPath}: not a sidecar with a distribution"
    }
    def root = sidecarPath.parent
    def batch = batchHeader(doc, root.toUriString())
    def idSystems = (doc.subjects ?: []).collectEntries { s -> [(s.subjectId): s.idSystem] }

    return doc.distribution.collect { item ->
        def type = (item['@type'] instanceof List ? item['@type'] : [item['@type']])
        def meta = [
            id             : stripUrn(item['@id']),
            urn            : item['@id'],
            name           : item.name,
            contentUrl     : item.contentUrl,
            additionalType : (item.additionalType ?: '').replaceFirst(/^rddc:/, ''),
            encodingFormat : item.encodingFormat,
            compression    : item.compression,
            documentType   : item.documentType,
            subjectIds     : item.subjectIds ?: [],
            subjects       : (item.subjectIds ?: []).collect { sid -> [subjectId: sid, idSystem: idSystems[sid]] },
            reportDocuments: (item.reportDocuments ?: []).collect { ref -> stripUrn(ref['@id']) },
            md5            : item.md5,
            sha256         : item.sha256,
            batch          : batch,
        ]
        if (!('cr:FileObject' in type)) {
            return [meta, null, 'file_set_not_listed']
        }
        def url = item.contentUrl as String
        // contentUrl is an object key relative to the batch prefix: no scheme, no absolute
        // path, no "..". Anything else could reach outside the batch.
        if (!url || url.contains('://') || url.startsWith('/') || url.split('/').contains('..')) {
            return [meta, null, 'content_url_outside_batch']
        }
        if (!item.md5) {
            return [meta, null, 'missing_md5']
        }
        return [meta, root.resolve(url), null]
    }
}

workflow SIDECAR_INTAKE {
    take:
    sidecar   // path to _sidecar.json

    main:
    entries = channel.of(sidecar).flatMap { p -> parseSidecar(p) }

    usable = entries.filter { _meta, _path, problem -> problem == null }
        .map { meta, path, _problem -> [meta, file(path, checkIfExists: true)] }
    unusable = entries.filter { _meta, _path, problem -> problem != null }
        .map { meta, _path, problem -> [meta, problem] }

    VERIFY_CHECKSUM(usable)

    files = VERIFY_CHECKSUM.out.checked
        .filter { _meta, _data, status -> status.trim() == 'ok' }
        .map { meta, data, _status -> [meta, data] }
    mismatched = VERIFY_CHECKSUM.out.checked
        .filter { _meta, _data, status -> status.trim() != 'ok' }
        .map { meta, _data, status -> [meta, "checksum_${status.trim().replace(':', '_')}"] }

    emit:
    files    = files
    rejected = unusable.mix(mismatched)
    batch    = channel.of(sidecar).map { p -> batchHeader(new groovy.json.JsonSlurper().parseText(p.text), p.parent.toUriString()) }
}
