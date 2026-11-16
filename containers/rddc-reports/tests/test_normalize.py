"""Normalization against the committed reference subset (BRCA1 NM_007294.4, CFTR NM_000492.4).

Expected genomic descriptions and VRS identifiers were checked on 2026-11-14 against hgvs on
live UTA (versions.EXPECTED_UTA) with NCBI sequences, and against VRS computed on the full GRCh38
chromosomes (see test_live.py). The chromosome digests are the published GA4GH identifiers.
"""

import pytest

from rddc_reports import versions
from rddc_reports.normalize import Normalizer
from rddc_reports.refdata.sequences import OutsideReference, StoreSequences
from rddc_reports.refdata.store import Store

RESOLVED = {
    # input: (genomic HGVS, genomic VRS digest, has transcript-level allele)
    "NM_007294.4:c.68_69del": ("NC_000017.11:g.43124030_43124031del", "EE08XW4IpzeWhJAwComKOSmsPHTcP-1R", True),
    "NM_007294.4:c.5266dup": ("NC_000017.11:g.43057065dup", "lf9dZXRpgI2t0kFimdLdLF2c-x7M_MzB", True),
    "NM_007294.4:c.181T>G": ("NC_000017.11:g.43106487A>C", "2zia0Z0RRscgggOMSncGvwqV1JNk0EpR", True),
    "NM_007294.4:c.4096+1G>A": ("NC_000017.11:g.43091434C>T", "4d6Xbcr_rNGbBpATyN1J9mZdjs5If2n9", False),
    "NM_000492.4:c.1521_1523del": ("NC_000007.14:g.117559592_117559594del", "1XMYiWeH-zAzuRLwPcJGQaQ1MHV5Sf0n", True),
    "NM_000492.4:c.1624G>T": ("NC_000007.14:g.117587778G>T", "nNgxGCsrxUFqWIs_j-W-42ZsZSl_fSnR", True),
}

NOT_RESOLVED = {
    "NM_007294:c.181T>G": ("unresolved", "missing_accession_version"),
    "c.181T>G": ("unresolved", "missing_accession"),
    "BRCA1:c.181T>G": ("unresolved", "unsupported_accession"),
    "NM_007294.4:c.181A>G": ("invalid", "failed_validation"),          # reference is T
    "NM_007294.4:c.4096+1A>G": ("invalid", "failed_validation"),       # intronic; reference is G
    "NM_007294.4:c.(100_200)del": ("unresolved", "uncertain_description"),
    "NM_999999.1:c.1A>G": ("unresolved", "reference_not_available"),    # no such transcript in UTA
    "NC_000017.11:g.100000A>G": ("unresolved", "outside_reference_data"),
    "NM_007294.4:c.181T>": ("invalid", "unparseable"),
}


@pytest.fixture(scope="module")
def normalizer(subset_path):
    store = Store(subset_path)
    return Normalizer(store, StoreSequences(store))


@pytest.mark.parametrize("desc", sorted(RESOLVED))
def test_resolved(normalizer, desc):
    g, digest, has_tx = RESOLVED[desc]
    r = normalizer.resolve(desc)
    assert (r.status, r.reason) == ("resolved", None), r.detail
    assert r.hgvs_genomic == g
    assert r.vrs_genomic["id"] == f"ga4gh:VA.{digest}"
    assert (r.vrs_transcript is not None) == has_tx
    assert r.vrs_protein is None
    assert r.reference["uta_version"] == versions.EXPECTED_UTA


def test_genomic_input_gives_same_allele_as_projection(normalizer):
    r = normalizer.resolve("NC_000007.14:g.117559592_117559594del")
    assert r.vrs_genomic["id"] == "ga4gh:VA.1XMYiWeH-zAzuRLwPcJGQaQ1MHV5Sf0n"


def test_different_dna_alleles_stay_distinct(normalizer):
    # Deleting TTT instead of CTT (c.1521_1523del) also removes Phe508 but is another allele.
    r = normalizer.resolve("NC_000007.14:g.117559593_117559595del")
    assert r.status == "resolved"
    assert r.vrs_genomic["id"] != "ga4gh:VA.1XMYiWeH-zAzuRLwPcJGQaQ1MHV5Sf0n"


def test_protein_is_protein_level_only(normalizer):
    observed = normalizer.resolve("NP_009225.1:p.Cys61Gly")
    predicted = normalizer.resolve("NP_009225.1:p.(Cys61Gly)")
    for r in (observed, predicted):
        assert r.status == "resolved"
        assert r.vrs_protein["id"] == "ga4gh:VA.x_z3jmpHTlBJ8QVPGrKYd7_B9eGDVqdj"
        assert r.vrs_genomic is None and r.hgvs_genomic is None
    assert (observed.predicted, predicted.predicted) == (False, True)


@pytest.mark.parametrize("desc", sorted(NOT_RESOLVED))
def test_not_resolved(normalizer, desc):
    r = normalizer.resolve(desc)
    assert (r.status, r.reason) == NOT_RESOLVED[desc], r.detail
    assert r.vrs_genomic is r.vrs_transcript is r.vrs_protein is None


def test_subset_is_built_from_expected_releases(subset_path):
    store = Store(subset_path)
    assert store.meta("uta_version") == versions.EXPECTED_UTA
    assert store.meta("assembly") == versions.EXPECTED_ASSEMBLY


def test_chromosome_digests_are_published_values(subset_path):
    seqs = StoreSequences(Store(subset_path))
    assert "ga4gh:SQ.dLZ15tNO1Ur0IcGjwc3Sdi_0A6Yf4zm7" in seqs.metadata("NC_000017.11")["aliases"]
    assert "ga4gh:SQ.F-LrLMe1SRpfUZHkQmvkVKFEGaoDeHul" in seqs.metadata("NC_000007.14")["aliases"]
    assert seqs.metadata("GRCh38:chr17")["length"] == 83257441


def test_windows_refuse_ranges_they_do_not_hold(subset_path):
    seqs = StoreSequences(Store(subset_path))
    with pytest.raises(OutsideReference):
        seqs.fetch("NC_000017.11")          # whole chromosome is not stored
    with pytest.raises(KeyError):
        seqs.fetch("NM_000059.4")
