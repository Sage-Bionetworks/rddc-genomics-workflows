"""Local reference-data store: transcript alignments (a UTA export) and sequences, in SQLite.

One file holds what hgvs and vrs-python need, so validation and normalization run without a
Postgres server or network access. Tests use a subset (fixture transcripts, genomic windows);
production can use a full export, or keep alignments here and read sequences from a SeqRepo
directory (see sequences.py).

Sequences are stored as segments. A whole transcript or protein is one segment from 0 to its
length. A chromosome may be stored as windows; its length and digests are those of the full
sequence, so identifiers do not depend on what was stored.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1"

DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS tx_exons (
    tx_ac TEXT NOT NULL, alt_ac TEXT NOT NULL, alt_aln_method TEXT NOT NULL, hgnc TEXT,
    alt_strand INTEGER NOT NULL, ord INTEGER NOT NULL,
    tx_start_i INTEGER NOT NULL, tx_end_i INTEGER NOT NULL,
    alt_start_i INTEGER NOT NULL, alt_end_i INTEGER NOT NULL,
    cigar TEXT NOT NULL, tx_aseq TEXT, alt_aseq TEXT,
    tx_exon_set_id INTEGER, alt_exon_set_id INTEGER, tx_exon_id INTEGER, alt_exon_id INTEGER,
    exon_aln_id INTEGER,
    PRIMARY KEY (tx_ac, alt_ac, alt_aln_method, ord)
);
CREATE INDEX IF NOT EXISTS tx_exons_region ON tx_exons (alt_ac, alt_aln_method, alt_start_i, alt_end_i);

CREATE TABLE IF NOT EXISTS tx_info (
    tx_ac TEXT NOT NULL, alt_ac TEXT NOT NULL, alt_aln_method TEXT NOT NULL, hgnc TEXT,
    cds_start_i INTEGER, cds_end_i INTEGER,
    PRIMARY KEY (tx_ac, alt_ac, alt_aln_method)
);
CREATE INDEX IF NOT EXISTS tx_info_hgnc ON tx_info (hgnc);

CREATE TABLE IF NOT EXISTS tx_identity_info (
    tx_ac TEXT PRIMARY KEY, alt_ac TEXT NOT NULL, alt_aln_method TEXT NOT NULL,
    cds_start_i INTEGER, cds_end_i INTEGER, lengths TEXT NOT NULL, hgnc TEXT
);

-- tx_mapping_options is not stored: hgvs gets the options from tx_info (exported alignments).

CREATE TABLE IF NOT EXISTS tx_pro (tx_ac TEXT PRIMARY KEY, pro_ac TEXT NOT NULL);

-- protein accessions by sequence MD5 (UTA seq_anno), so protein lookups work without sequences
CREATE TABLE IF NOT EXISTS protein_md5 (md5 TEXT NOT NULL, ac TEXT NOT NULL, PRIMARY KEY (md5, ac));

CREATE TABLE IF NOT EXISTS gene_info (
    hgnc TEXT PRIMARY KEY, maploc TEXT, descr TEXT, summary TEXT, aliases TEXT, added TEXT
);

-- seq_id is the GA4GH sha512t24u digest of the full sequence (without the "SQ." prefix)
CREATE TABLE IF NOT EXISTS seqinfo (
    seq_id TEXT PRIMARY KEY, length INTEGER NOT NULL, alphabet TEXT NOT NULL, md5 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS seq_alias (
    namespace TEXT NOT NULL, alias TEXT NOT NULL, seq_id TEXT NOT NULL REFERENCES seqinfo,
    PRIMARY KEY (namespace, alias)
);
CREATE INDEX IF NOT EXISTS seq_alias_seq ON seq_alias (seq_id);
CREATE TABLE IF NOT EXISTS seq_segment (
    seq_id TEXT NOT NULL REFERENCES seqinfo, start_i INTEGER NOT NULL, end_i INTEGER NOT NULL,
    seq TEXT NOT NULL,
    PRIMARY KEY (seq_id, start_i)
);
"""

# Columns returned by hgvs's UTA provider, in its order, so rows are interchangeable.
TX_EXON_COLS = [
    "hgnc", "tx_ac", "alt_ac", "alt_aln_method", "alt_strand", "ord", "tx_start_i", "tx_end_i",
    "alt_start_i", "alt_end_i", "cigar", "tx_aseq", "alt_aseq", "tx_exon_set_id",
    "alt_exon_set_id", "tx_exon_id", "alt_exon_id", "exon_aln_id",
]
TX_INFO_COLS = ["hgnc", "cds_start_i", "cds_end_i", "tx_ac", "alt_ac", "alt_aln_method"]
TX_IDENTITY_COLS = ["tx_ac", "alt_ac", "alt_aln_method", "cds_start_i", "cds_end_i", "lengths", "hgnc"]
GENE_INFO_COLS = ["hgnc", "maploc", "descr", "summary", "aliases", "added"]


class Store:
    """Thin wrapper over the SQLite file. Read-only unless opened with writable=True."""

    def __init__(self, path: str | Path, writable: bool = False):
        self.path = Path(path)
        if writable:
            self.db = sqlite3.connect(self.path)
            self.db.executescript(DDL)
            self.set_meta("schema_version", SCHEMA_VERSION)
        else:
            if not self.path.exists():
                raise FileNotFoundError(self.path)
            self.db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row

    def close(self) -> None:
        self.db.close()

    # --- meta -----------------------------------------------------------------
    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def meta(self, key: str) -> str | None:
        r = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else None

    # --- writers (builder) --------------------------------------------------------
    def put_rows(self, table: str, cols: list[str], rows: list[dict]) -> None:
        sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
        self.db.executemany(sql, [[_encode(r.get(c)) for c in cols] for r in rows])

    def put_sequence(self, seq_id: str, length: int, alphabet: str, md5: str,
                     aliases: list[tuple[str, str]], segments: list[tuple[int, str]]) -> None:
        self.db.execute("INSERT OR REPLACE INTO seqinfo VALUES (?, ?, ?, ?)", (seq_id, length, alphabet, md5))
        self.db.executemany("INSERT OR REPLACE INTO seq_alias VALUES (?, ?, ?)",
                            [(ns, a, seq_id) for ns, a in aliases])
        self.db.executemany("INSERT OR REPLACE INTO seq_segment VALUES (?, ?, ?, ?)",
                            [(seq_id, s, s + len(seq), seq) for s, seq in segments])

    def commit(self) -> None:
        self.db.commit()

    # --- readers ------------------------------------------------------------------
    def rows(self, sql: str, args: tuple = ()) -> list[dict]:
        return [dict(r) for r in self.db.execute(sql, args)]

    def seq_id_for(self, namespace: str, alias: str) -> str | None:
        r = self.db.execute("SELECT seq_id FROM seq_alias WHERE namespace = ? AND alias = ?",
                            (namespace, alias)).fetchone()
        return r["seq_id"] if r else None


def _encode(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v
