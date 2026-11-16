"""Opt-in check of the reference subset against live sources (RDDC_REPORTS_LIVE=1).

Compares local genomic projections with hgvs on the public UTA database and NCBI sequences, and
windowed VRS identifiers with identifiers computed on full sequences (downloaded by
`rddc-reports refdata build-subset` into its cache). Run after rebuilding the subset or
upgrading hgvs or vrs-python. This test sends accession numbers and fixture variants, never
report content.
"""

import gzip

import pytest

from rddc_reports.refdata.build import DEFAULT_CACHE, PUBLIC_UTA

from test_normalize import RESOLVED

pytestmark = pytest.mark.live


def test_matches_live_uta_and_full_sequences(subset_path):
    import hgvs.assemblymapper
    import hgvs.dataproviders.uta as uta
    import hgvs.parser
    from ga4gh.vrs.dataproxy import _DataProxy

    live = uta.connect(PUBLIC_UTA)   # before Normalizer disables network reference access
    am_live = hgvs.assemblymapper.AssemblyMapper(live, assembly_name="GRCh38", alt_aln_method="splign",
                                                 replace_reference=False)
    parser = hgvs.parser.Parser()
    live_g = {d: str(am_live.c_to_g(parser.parse_hgvs_variant(d))) for d in RESOLVED}

    from rddc_reports.normalize import Normalizer
    from rddc_reports.refdata.sequences import StoreSequences
    from rddc_reports.refdata.store import Store
    from rddc_reports.refdata.vrs_proxy import LocalAlleleTranslator

    store = Store(subset_path)
    local = StoreSequences(store)
    full: dict[str, str] = {}

    class FullProxy(_DataProxy):
        def get_sequence(self, identifier, start=None, end=None):
            ac = next(a.split(":", 1)[1] for a in local.metadata(identifier)["aliases"] if a.startswith("refseq:"))
            if ac not in full:
                path = DEFAULT_CACHE / f"{ac}.fa.gz"
                if not path.exists():
                    pytest.skip(f"{path} missing; run refdata build-subset first")
                full[ac] = "".join(gzip.open(path, "rt").read().splitlines()[1:]).upper()
            return full[ac][start:end]

        def get_metadata(self, identifier):
            return local.metadata(identifier)

    n = Normalizer(store, local)
    t_full = LocalAlleleTranslator(FullProxy(), n.hdp)
    for desc in RESOLVED:
        r = n.resolve(desc)
        assert r.hgvs_genomic == live_g[desc], desc
        assert r.vrs_genomic["id"] == t_full.translate_from(r.hgvs_genomic, "hgvs").id, desc
