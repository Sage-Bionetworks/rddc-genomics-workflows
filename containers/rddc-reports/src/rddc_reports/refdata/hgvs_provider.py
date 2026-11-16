"""hgvs data provider backed by the local store, in place of hgvs's UTA/Postgres provider.

Rows have the same keys as the UTA provider's, so hgvs's mappers, normalizer and validator work
unchanged. Sequences come from a Sequences object, never from hgvs's SeqFetcher (which would
fall back to NCBI over the network).
"""

from __future__ import annotations

import hashlib
import json

from bioutils.assemblies import make_ac_name_map
from hgvs.dataproviders.interface import Interface

from .sequences import Sequences
from .store import GENE_INFO_COLS, TX_EXON_COLS, TX_IDENTITY_COLS, TX_INFO_COLS, Store


class LocalDataProvider(Interface):
    required_version = "1.1"   # UTA schema version the exported rows follow

    def __init__(self, store: Store, sequences: Sequences):
        self.store = store
        self.sequences = sequences
        self.url = f"local:{store.path}"
        super().__init__()

    def data_version(self):
        return self.store.meta("uta_version") or "unknown"

    def schema_version(self):
        return "1.1"

    def sequence_source(self):
        return self.sequences.describe()

    def get_seq(self, ac, start_i=None, end_i=None):
        return self.sequences.fetch(ac, start_i, end_i)

    def get_acs_for_protein_seq(self, seq):
        md5 = hashlib.md5(seq.encode()).hexdigest()
        acs = [r["ac"] for r in self.store.rows(
            "SELECT ac FROM protein_md5 WHERE md5 = ? "
            "UNION SELECT a.alias FROM seqinfo i JOIN seq_alias a USING (seq_id) "
            "WHERE i.md5 = ? AND a.namespace = 'refseq' ORDER BY 1", (md5, md5))]
        return acs + ["MD5_" + md5]

    def get_assembly_map(self, assembly_name):
        return make_ac_name_map(assembly_name)

    def get_gene_info(self, gene):
        r = self.store.rows(f"SELECT {','.join(GENE_INFO_COLS)} FROM gene_info WHERE hgnc = ?", (gene,))
        return r[0] if r else None

    def get_pro_ac_for_tx_ac(self, tx_ac):
        r = self.store.rows("SELECT pro_ac FROM tx_pro WHERE tx_ac = ?", (tx_ac,))
        return r[0]["pro_ac"] if r else None

    def get_similar_transcripts(self, tx_ac):
        return []   # not exported; hgvs's mapping and validation do not use it

    def get_tx_exons(self, tx_ac, alt_ac, alt_aln_method):
        return self.store.rows(
            f"SELECT {','.join(TX_EXON_COLS)} FROM tx_exons "
            # UTA orders by genomic start, not exon number (they differ on the minus strand)
            "WHERE tx_ac = ? AND alt_ac = ? AND alt_aln_method = ? ORDER BY alt_start_i",
            (tx_ac, alt_ac, alt_aln_method))

    def get_tx_for_gene(self, gene):
        # UTA returns hgnc, cds_start_i, cds_end_i, tx_ac, alt_ac, alt_aln_method
        return self.store.rows(
            f"SELECT {','.join(TX_INFO_COLS)} FROM tx_info WHERE hgnc = ? ORDER BY tx_ac", (gene,))

    def get_tx_for_region(self, alt_ac, alt_aln_method, start_i, end_i):
        return self.store.rows(
            "SELECT tx_ac, alt_ac, alt_strand, alt_aln_method, "
            "MIN(alt_start_i) AS start_i, MAX(alt_end_i) AS end_i FROM tx_exons "
            "WHERE alt_ac = ? AND alt_aln_method = ? GROUP BY tx_ac, alt_ac, alt_strand, alt_aln_method "
            "HAVING MIN(alt_start_i) < ? AND ? <= MAX(alt_end_i)",
            (alt_ac, alt_aln_method, end_i, start_i))

    def get_tx_identity_info(self, tx_ac):
        r = self.store.rows(
            f"SELECT {','.join(TX_IDENTITY_COLS)} FROM tx_identity_info WHERE tx_ac = ?", (tx_ac,))
        if not r:
            from hgvs.exceptions import HGVSDataNotAvailableError
            raise HGVSDataNotAvailableError(f"No transcript definition for (tx_ac={tx_ac})")
        r[0]["lengths"] = json.loads(r[0]["lengths"])
        return r[0]

    def get_tx_info(self, tx_ac, alt_ac, alt_aln_method):
        r = self.store.rows(
            f"SELECT {','.join(TX_INFO_COLS)} FROM tx_info "
            "WHERE tx_ac = ? AND alt_ac = ? AND alt_aln_method = ?", (tx_ac, alt_ac, alt_aln_method))
        if not r:
            from hgvs.exceptions import HGVSDataNotAvailableError
            raise HGVSDataNotAvailableError(
                f"No tx_info for (tx_ac={tx_ac}, alt_ac={alt_ac}, alt_aln_method={alt_aln_method})")
        return r[0]

    def get_tx_mapping_options(self, tx_ac):
        # Only alignments that were exported, so a missing assembly fails as "no mapping".
        return self.store.rows(
            "SELECT tx_ac, alt_ac, alt_aln_method FROM tx_info WHERE tx_ac = ? "
            "ORDER BY alt_ac, alt_aln_method", (tx_ac,))
