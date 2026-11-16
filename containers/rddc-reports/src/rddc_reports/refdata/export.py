"""Export a full UTA release to the local store (alignments only; sequences come from SeqRepo).

Copies, for every transcript aligned by splign to a primary-assembly chromosome of the
assembly (GRCh38 by default, including chrM), the rows hgvs's UTA provider would return:
exons, transcript info, identity info, protein accession, plus gene info and protein MD5
accessions. The queries follow hgvs.dataproviders.uta so rows are interchangeable; they read
the materialized versions of hgvs's views (tx_exon_aln_mv, tx_def_summary_mv), which UTA
releases build from the same definitions.

Reads a UTA database: the public biocommons server (default) or a local restore of the UTA
dump. Sends only these queries, no report content. Takes a few minutes and writes about
200 MB for uta_20241220.
"""

from __future__ import annotations

import datetime
import logging
import time
from pathlib import Path

from bioutils.assemblies import make_ac_name_map

from ..versions import PUBLIC_UTA_URL
from .store import GENE_INFO_COLS, TX_EXON_COLS, TX_IDENTITY_COLS, TX_INFO_COLS, Store

log = logging.getLogger(__name__)

# Transcripts exported: splign alignments to the assembly's primary chromosomes.
_EXPORTED = "SELECT DISTINCT tx_ac FROM exon_set WHERE alt_aln_method = 'splign' AND alt_ac = ANY(%(acs)s)"

QUERIES = {
    "tx_exons": (TX_EXON_COLS, f"""
        SELECT {', '.join(TX_EXON_COLS)} FROM tx_exon_aln_mv
        WHERE alt_aln_method = 'splign' AND alt_ac = ANY(%(acs)s) AND exon_aln_id IS NOT NULL"""),
    "tx_info": (TX_INFO_COLS, f"""
        SELECT DISTINCT {', '.join('T.' + c if c in ('hgnc', 'cds_start_i', 'cds_end_i') else 'ES.' + c
                                   for c in TX_INFO_COLS)}
        FROM transcript T JOIN exon_set ES ON T.ac = ES.tx_ac
        WHERE ES.alt_aln_method = 'splign' AND ES.alt_ac = ANY(%(acs)s)"""),
    "tx_identity_info": (TX_IDENTITY_COLS, f"""
        SELECT DISTINCT ON (tx_ac) {', '.join(TX_IDENTITY_COLS)} FROM tx_def_summary_mv
        WHERE tx_ac IN ({_EXPORTED}) ORDER BY tx_ac"""),
    # hgvs takes the first of "order by pro_ac desc"
    "tx_pro": (["tx_ac", "pro_ac"], f"""
        SELECT DISTINCT ON (tx_ac) tx_ac, pro_ac FROM associated_accessions
        WHERE tx_ac IN ({_EXPORTED}) ORDER BY tx_ac, pro_ac DESC"""),
    "gene_info": (GENE_INFO_COLS, f"SELECT {', '.join(GENE_INFO_COLS)} FROM gene"),
    "protein_md5": (["md5", "ac"], f"""
        SELECT DISTINCT SA.seq_id, SA.ac FROM seq_anno SA
        WHERE SA.ac IN (SELECT pro_ac FROM associated_accessions WHERE tx_ac IN ({_EXPORTED}))"""),
}


def primary_chromosomes(assembly: str) -> list[str]:
    return sorted(ac for ac in make_ac_name_map(assembly) if ac.startswith("NC_"))


def export_uta(out: Path, uta_url: str = PUBLIC_UTA_URL, assembly: str = "GRCh38",
               batch: int = 50_000) -> dict:
    import psycopg2

    schema = uta_url.rstrip("/").rsplit("/", 1)[-1]
    dsn = uta_url[: -len(schema) - 1]
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True)
    with conn.cursor() as c:
        c.execute("SET search_path = %s", (schema,))
        c.execute("SELECT value FROM meta WHERE key = 'schema_version'")
        schema_version = c.fetchone()[0]
    acs = primary_chromosomes(assembly)

    tmp = out.with_suffix(".partial")
    if tmp.exists():
        tmp.unlink()
    store = Store(tmp, writable=True)
    counts = {}
    for table, (cols, sql) in QUERIES.items():
        t0 = time.time()
        with conn.cursor(name=f"export_{table}") as cur:   # server-side cursor: streams rows
            cur.itersize = batch
            cur.execute(sql, {"acs": acs})   # search_path was set for this session above
            n = 0
            while rows := cur.fetchmany(batch):
                store.put_rows(table, cols, [dict(zip(cols, r)) for r in rows])
                n += len(rows)
        store.commit()
        counts[table] = n
        log.info("%s: %d rows in %.0fs", table, n, time.time() - t0)
    conn.close()

    summary = {
        "uta_version": schema,
        "uta_schema_version": schema_version,
        "uta_url": uta_url.split("@")[-1],
        "assembly": assembly,
        "contains_sequences": "false",
        "scope": "splign alignments to primary-assembly chromosomes",
        "built_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        **{f"rows_{k}": str(v) for k, v in counts.items()},
    }
    for k, v in summary.items():
        store.set_meta(k, v)
    store.commit()
    store.db.execute("VACUUM")
    store.close()
    tmp.rename(out)
    return summary
