"""Build a reference-data subset for a list of transcripts.

Alignments come from a UTA database (default: the expected release, versions.EXPECTED_UTA, on the
public biocommons instance); sequences from
NCBI E-utilities. Both are reference data: the build sends accession numbers only, never report
content. Full chromosomes are downloaded once (cached) to compute their length and digests, and
only windows around the transcripts are stored.

This is for test fixtures. A production store would be exported in bulk from a UTA dump, with
sequences from a SeqRepo directory.
"""

from __future__ import annotations

import datetime
import gzip
import hashlib
import logging
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from bioutils.assemblies import make_ac_name_map
from ga4gh.core import sha512t24u

from ..versions import PUBLIC_UTA_URL as PUBLIC_UTA
from .store import GENE_INFO_COLS, TX_EXON_COLS, TX_IDENTITY_COLS, TX_INFO_COLS, Store

log = logging.getLogger(__name__)

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
DEFAULT_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "rddc-reports" / "ncbi"


def fetch_fasta(ac: str, db: str, cache: Path) -> str:
    """Sequence of a RefSeq accession, from the cache or NCBI (gzip-cached)."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{ac}.fa.gz"
    if not path.exists():
        q = urllib.parse.urlencode({"db": db, "id": ac, "rettype": "fasta", "retmode": "text",
                                    "tool": "rddc-reports"})
        log.info("fetching %s from NCBI", ac)
        with urllib.request.urlopen(f"{EUTILS}?{q}", timeout=600) as r:
            data = r.read()
        if not data.startswith(b">"):
            raise RuntimeError(f"NCBI returned no FASTA for {ac}: {data[:200]!r}")
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wb") as f:
            f.write(data)
        tmp.rename(path)
        time.sleep(0.4)   # stay under NCBI's 3 requests/second without an API key
    with gzip.open(path, "rt") as f:
        lines = f.read().splitlines()
    header = lines[0][1:].split()[0]
    if header != ac:
        raise RuntimeError(f"FASTA for {ac} has header {header}")
    return "".join(lines[1:]).upper()


def _put_seq(store: Store, ac: str, seq: str, windows=None, extra_aliases=()):
    alphabet = "".join(sorted(set(seq)))
    seq_id = sha512t24u(seq.encode())
    md5 = hashlib.md5(seq.encode()).hexdigest()
    aliases = [("refseq", ac), ("ga4gh", f"SQ.{seq_id}"), ("MD5", md5), *extra_aliases]
    segments = [(0, seq)] if windows is None else [(s, seq[s:e]) for s, e in windows]
    store.put_sequence(seq_id, len(seq), alphabet, md5, aliases, segments)
    return seq_id


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def build_subset(transcripts: list[str], out: Path, assembly: str = "GRCh38", pad: int = 5000,
                 uta_url: str = PUBLIC_UTA, cache: Path = DEFAULT_CACHE) -> dict:
    import hgvs.dataproviders.uta as uta

    hdp = uta.connect(uta_url)
    chrom_names = make_ac_name_map(assembly)          # NC_000017.11 -> "17"
    if out.exists():
        out.unlink()
    store = Store(out, writable=True)

    windows: dict[str, list[tuple[int, int]]] = {}
    genes = set()
    for tx in transcripts:
        opts = [o for o in hdp.get_tx_mapping_options(tx)
                if o["alt_ac"] in chrom_names and o["alt_aln_method"] == "splign"]
        if not opts:
            raise RuntimeError(f"{tx}: no splign alignment to {assembly} in {hdp.data_version()}")
        for o in opts:
            alt_ac = o["alt_ac"]
            exons = [dict(r) for r in hdp.get_tx_exons(tx, alt_ac, "splign")]
            store.put_rows("tx_exons", TX_EXON_COLS, exons)
            store.put_rows("tx_info", TX_INFO_COLS, [dict(hdp.get_tx_info(tx, alt_ac, "splign"))])
            lo = min(e["alt_start_i"] for e in exons)
            hi = max(e["alt_end_i"] for e in exons)
            windows.setdefault(alt_ac, []).append((max(0, lo - pad), hi + pad))
        store.put_rows("tx_identity_info", TX_IDENTITY_COLS, [dict(hdp.get_tx_identity_info(tx))])
        _put_seq(store, tx, fetch_fasta(tx, "nuccore", cache))
        pro = hdp.get_pro_ac_for_tx_ac(tx)
        if pro:
            store.put_rows("tx_pro", ["tx_ac", "pro_ac"], [{"tx_ac": tx, "pro_ac": pro}])
            _put_seq(store, pro, fetch_fasta(pro, "protein", cache))
        info = hdp.get_tx_info(tx, opts[0]["alt_ac"], "splign")
        genes.add(info["hgnc"])

    for g in sorted(genes):
        gi = hdp.get_gene_info(g)
        if gi:
            store.put_rows("gene_info", GENE_INFO_COLS, [dict(gi)])

    for alt_ac, ivs in windows.items():
        seq = fetch_fasta(alt_ac, "nuccore", cache)
        merged = [(s, min(e, len(seq))) for s, e in _merge(ivs)]
        name = chrom_names[alt_ac]
        _put_seq(store, alt_ac, seq, windows=merged,
                 extra_aliases=[(assembly, name), (assembly, f"chr{name}")])

    summary = {
        "uta_version": hdp.data_version(),
        "uta_url": uta_url.split("@")[-1],          # drop credentials
        "assembly": assembly,
        "pad": str(pad),
        "transcripts": ",".join(transcripts),
        "built_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "sequence_source": "NCBI E-utilities efetch",
    }
    for k, v in summary.items():
        store.set_meta(k, v)
    store.commit()
    store.close()
    return summary
