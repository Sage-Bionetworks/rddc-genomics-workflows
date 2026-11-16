"""Write tests/report-findings/batch/_sidecar.json from the files in batch/, and
_sidecar.errors.json, a copy with intake rejection cases.

The fixture follows rddc-model (branch `sidecar`). rddc-sidecar 0.1.0 vendors an older model
without GeneticTestResultFile, documentType and reportDocuments, so it cannot generate this
fixture yet; once it can, replace this script with `rddc-sidecar from-table`.

Usage (from the repo root):
    python -I tests/report-findings/make_sidecar.py \
        --context ../rddc-model/examples/ccda_document_set.json \
        --schema ../rddc-model/schema/generated/rddc_sidecar.schema.json

--context: an rddc-model example sidecar whose @context is copied (sidecars embed it).
--schema:  if given, the result is validated against it (needs `jsonschema`).
File IDs are fixed so outputs keyed by them stay stable; a changed file must get a new ID.
"""

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = HERE / "batch"

SUBJECTS = ["P001", "P002", "P003"]
ID_SYSTEM = "contributor"


def uuid(n: int) -> str:
    return f"urn:uuid:7f1c2a9e-0000-4000-8000-{n:012d}"


# (file id, key, class, encodingFormat, subjects, extra fields)
FILES = [
    (11, "reports/R001.txt", "ClinicalDocumentFile", "text/plain", ["P001"],
     {"documentType": "genetic_report"}),
    # Trio report: two subjects; findings must be attributed to one of them.
    (12, "reports/R002.txt", "ClinicalDocumentFile", "text/plain", ["P002", "P003"],
     {"documentType": "genetic_report"}),
    # No documentType: skipped unless --include_untyped_documents.
    (13, "notes/N001.txt", "ClinicalDocumentFile", "text/plain", ["P001"], {}),
    # Structured results for R001: primary source for that report; R001 is linked as evidence.
    (14, "results/results.json", "GeneticTestResultFile", "application/json", ["P001"],
     {"referenceGenome": "GRCh38", "reportDocuments": [{"@id": uuid(11)}],
      "sensitivity": {"containsFreeText": True}}),
]


def file_object(n, key, cls, fmt, subjects, extra):
    data = (BATCH / key).read_bytes()
    obj = {
        "@id": uuid(n),
        "@type": "cr:FileObject",
        "additionalType": f"rddc:{cls}",
        "name": key,
        "contentUrl": key,
        "contentSize": f"{len(data)} B",
        "encodingFormat": fmt,
        "sha256": hashlib.sha256(data).hexdigest(),
        "md5": hashlib.md5(data).hexdigest(),
        "subjectIds": subjects,
    }
    obj.update(extra)
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--context", required=True)
    ap.add_argument("--schema")
    args = ap.parse_args()

    sidecar = {
        "@context": json.load(open(args.context))["@context"],
        "@id": uuid(1),
        "@type": "sc:Dataset",
        "conformsTo": ["http://mlcommons.org/croissant/1.1", "https://w3id.org/rddc/sidecar/0.1.0"],
        "name": "src-test-01/2026-11-rf-test",
        "url": "s3://rddc-deposit-test/src-test-01/2026-11-rf-test/",
        "dateCreated": "2026-11-14T00:00:00Z",
        "wasAttributedTo": {"@type": "sc:SoftwareApplication", "name": "make_sidecar.py",
                            "softwareVersion": "0.1.0"},
        "contributorId": "test-site",
        "sourceId": "src-test-01",
        "batchId": "2026-11-rf-test",
        "interaction": "add",
        "sensitivity": {
            "directIdentifiersRemoved": True,
            "synthetic": True,
            "containsDates": False,
            "containsZipCodes": False,
            "containsFreeText": True,
            "containsBiometricIdentifiers": False,
        },
        "description": "Synthetic genetic test reports for the report-findings pipeline tests.",
        "subjects": [{"subjectId": s, "idSystem": ID_SYSTEM} for s in SUBJECTS],
        "distribution": [file_object(*f) for f in FILES],
    }
    if args.schema:
        import jsonschema

        schema = json.load(open(args.schema))
        errors = sorted(jsonschema.validators.validator_for(schema)(schema).iter_errors(sidecar),
                        key=lambda e: list(e.absolute_path))
        for e in errors:
            print(f"{'/'.join(map(str, e.absolute_path))}: {e.message[:300]}")
        if errors:
            raise SystemExit(f"{len(errors)} schema errors")
    out = BATCH / "_sidecar.json"
    out.write_text(json.dumps(sidecar, indent=2) + "\n")
    print(f"wrote {out}")

    # Rejection cases for intake (not a valid sidecar, so not schema-checked): a checksum
    # mismatch, a contentUrl that leaves the batch, and a file set without listed files.
    errors = json.loads(json.dumps(sidecar))
    errors["@id"] = uuid(2)
    dist = errors["distribution"]
    dist[1]["md5"] = "0" * 32
    dist[2]["contentUrl"] = "../make_sidecar.py"
    dist.append({"@id": "reports-set", "@type": "cr:FileSet", "additionalType": "rddc:ClinicalDocumentFile",
                 "name": "more reports", "encodingFormat": "application/pdf", "includes": ["more/*.pdf"]})
    out = BATCH / "_sidecar.errors.json"
    out.write_text(json.dumps(errors, indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
