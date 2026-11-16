"""vrs-python wiring over the local reference data.

vrs-python's HgvsTools connects to the public UTA database when created and uses hgvs's
network sequence fetcher for c.→n. mapping and normalization. LocalAlleleTranslator gives it
the local hgvs provider instead, and forbid_network_reference() makes any remaining path that
would reach UTA or NCBI fail rather than send data out.
"""

from __future__ import annotations

import hgvs.normalizer
import hgvs.parser
import hgvs.variantmapper
from ga4gh.vrs.dataproxy import _DataProxy
from ga4gh.vrs.extras.translator import AlleleTranslator
from ga4gh.vrs.utils.hgvs_tools import HgvsTools

from .sequences import Sequences


class NetworkReferenceForbidden(RuntimeError):
    pass


def _forbidden(*_a, **_k):
    raise NetworkReferenceForbidden(
        "network reference access is disabled; reference data must come from the local store")


def forbid_network_reference() -> None:
    """Disable hgvs's UTA connection and bioutils' NCBI sequence fetching in this process."""
    import bioutils.seqfetcher
    import hgvs.dataproviders.seqfetcher
    import hgvs.dataproviders.uta

    hgvs.dataproviders.uta.connect = _forbidden
    bioutils.seqfetcher.fetch_seq = _forbidden
    hgvs.dataproviders.seqfetcher.SeqFetcher.fetch_seq = _forbidden


class LocalDataProxy(_DataProxy):
    def __init__(self, sequences: Sequences):
        super().__init__()
        self.sequences = sequences

    def get_sequence(self, identifier: str, start: int | None = None, end: int | None = None) -> str:
        return self.sequences.fetch(identifier, start, end)

    def get_metadata(self, identifier: str) -> dict:
        return self.sequences.metadata(identifier)


class LocalHgvsTools(HgvsTools):
    def __init__(self, data_proxy: _DataProxy, hdp) -> None:   # noqa: D107 (no super().__init__: it connects to UTA)
        self.parser = hgvs.parser.Parser()
        self.uta_conn = hdp
        self.normalizer = hgvs.normalizer.Normalizer(hdp, validate=True)
        self.variant_mapper = hgvs.variantmapper.VariantMapper(hdp)
        self.data_proxy = data_proxy

    def close(self) -> None:
        self.normalizer = self.variant_mapper = self.data_proxy = None   # the provider is not ours to close


class LocalAlleleTranslator(AlleleTranslator):
    def __init__(self, data_proxy: _DataProxy, hdp, default_assembly_name: str = "GRCh38"):
        super().__init__(data_proxy, default_assembly_name=default_assembly_name)
        self._local_hgvs_tools = LocalHgvsTools(data_proxy, hdp)

    @property
    def hgvs_tools(self) -> HgvsTools:
        return self._local_hgvs_tools
