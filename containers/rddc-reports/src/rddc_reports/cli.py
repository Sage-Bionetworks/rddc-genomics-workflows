"""rddc-reports command line. Each pipeline module calls one subcommand."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__


def _open_reference(args):
    from .refdata.sequences import SeqRepoSequences, StoreSequences
    from .refdata.store import Store

    store = Store(args.refdata)
    seqs = SeqRepoSequences(args.seqrepo) if args.seqrepo else StoreSequences(store)
    return store, seqs


def cmd_version(args) -> int:
    import importlib.metadata as md

    print(json.dumps({
        "rddc-reports": __version__,
        "hgvs": md.version("hgvs"),
        "ga4gh.vrs": md.version("ga4gh.vrs"),
        "biocommons.seqrepo": md.version("biocommons.seqrepo"),
    }))
    return 0


def cmd_refdata_build(args) -> int:
    from .refdata.build import PUBLIC_UTA, build_subset

    lines = (ln.split("#", 1)[0].strip() for ln in Path(args.transcripts).read_text().splitlines())
    txs = [ln for ln in lines if ln]
    summary = build_subset(txs, Path(args.out), assembly=args.assembly, pad=args.pad,
                           uta_url=args.uta_url or PUBLIC_UTA,
                           **({"cache": Path(args.cache)} if args.cache else {}))
    print(json.dumps(summary, indent=2))
    return 0


def cmd_refdata_export(args) -> int:
    from .refdata.export import export_uta
    from .versions import PUBLIC_UTA_URL

    summary = export_uta(Path(args.out), uta_url=args.uta_url or PUBLIC_UTA_URL, assembly=args.assembly)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_refdata_check(args) -> int:
    from .refdata.check import check_reference

    result = check_reference(args.refdata, args.seqrepo)
    text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0 if result["ok"] else 1


def cmd_normalize(args) -> int:
    from .normalize import Normalizer

    store, seqs = _open_reference(args)
    n = Normalizer(store, seqs, assembly=args.assembly)
    src = open(args.input) if args.input != "-" else sys.stdin
    out = open(args.output, "w") if args.output != "-" else sys.stdout
    for line in src:
        line = line.strip()
        if line and not line.startswith("#"):
            out.write(json.dumps(n.resolve(line).as_dict()) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rddc-reports")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version", help="print package and tool versions as JSON").set_defaults(fn=cmd_version)

    rd = sub.add_parser("refdata", help="reference data").add_subparsers(dest="refcmd", required=True)
    b = rd.add_parser("build-subset", help="build a store for a list of transcripts (test fixtures)")
    b.add_argument("--transcripts", required=True, help="file with one versioned transcript accession per line")
    b.add_argument("--out", required=True)
    b.add_argument("--assembly", default="GRCh38")
    b.add_argument("--pad", type=int, default=5000, help="bases kept either side of each transcript")
    b.add_argument("--uta-url", help="UTA database URL (default: public biocommons instance)")
    b.add_argument("--cache", help="download cache for NCBI sequences")
    b.set_defaults(fn=cmd_refdata_build)

    ex = rd.add_parser("export", help="export a full UTA release (alignments; sequences from SeqRepo)")
    ex.add_argument("--out", required=True)
    ex.add_argument("--assembly", default="GRCh38")
    ex.add_argument("--uta-url", help="UTA database URL including the schema (default: expected release, public server)")
    ex.set_defaults(fn=cmd_refdata_export)

    ck = rd.add_parser("check", help="check the reference data release and resolve known variants")
    ck.add_argument("--refdata", required=True)
    ck.add_argument("--seqrepo")
    ck.add_argument("--out", help="also write the result (JSON) here")
    ck.set_defaults(fn=cmd_refdata_check)

    nz = sub.add_parser("normalize", help="validate HGVS descriptions and derive VRS (one per line → JSONL)")
    nz.add_argument("--refdata", required=True, help="reference store (SQLite)")
    nz.add_argument("--seqrepo", help="SeqRepo directory; sequences come from here instead of the store")
    nz.add_argument("--assembly", default="GRCh38")
    nz.add_argument("--input", default="-")
    nz.add_argument("--output", default="-")
    nz.set_defaults(fn=cmd_normalize)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
