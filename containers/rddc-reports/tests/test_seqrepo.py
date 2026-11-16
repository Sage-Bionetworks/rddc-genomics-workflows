"""The production sequence path: alignments from the store, sequences from a SeqRepo directory.

Opt-in: set RDDC_REPORTS_SEQREPO to a SeqRepo snapshot directory of versions.EXPECTED_SEQREPO
(13.5 GB; see the pipeline README, "Expected versions"), and optionally RDDC_REPORTS_REFDATA to a
full export (`rddc-reports refdata export`) instead of the subset. Runs without network like the
other tests. Expectations are the same as with the subset, so the windowed store and the full
SeqRepo must agree.
"""

import os
from pathlib import Path

import pytest

from rddc_reports import versions
from rddc_reports.normalize import Normalizer
from rddc_reports.refdata.sequences import SeqRepoSequences
from rddc_reports.refdata.store import Store

from test_normalize import NOT_RESOLVED, RESOLVED

SEQREPO = os.environ.get("RDDC_REPORTS_SEQREPO")
pytestmark = pytest.mark.skipif(not SEQREPO, reason="set RDDC_REPORTS_SEQREPO to a SeqRepo directory")

# With full chromosomes nothing is outside the reference data; that case is subset-specific.
NOT_RESOLVED_FULL = {k: v for k, v in NOT_RESOLVED.items() if v[1] != "outside_reference_data"}


@pytest.fixture(scope="module")
def normalizer(alignments_path):
    assert Path(SEQREPO).resolve().name == versions.EXPECTED_SEQREPO, \
        f"{SEQREPO} is not SeqRepo {versions.EXPECTED_SEQREPO}"
    store = Store(alignments_path)
    assert store.meta("uta_version") == versions.EXPECTED_UTA
    return Normalizer(store, SeqRepoSequences(SEQREPO))


@pytest.mark.parametrize("desc", sorted(RESOLVED))
def test_resolved(normalizer, desc):
    g, digest, has_tx = RESOLVED[desc]
    r = normalizer.resolve(desc)
    assert (r.status, r.reason) == ("resolved", None), r.detail
    assert r.hgvs_genomic == g
    assert r.vrs_genomic["id"] == f"ga4gh:VA.{digest}"
    assert (r.vrs_transcript is not None) == has_tx
    assert r.reference["sequences"].startswith("seqrepo:")


def test_protein(normalizer):
    r = normalizer.resolve("NP_009225.1:p.Cys61Gly")
    assert r.vrs_protein["id"] == "ga4gh:VA.x_z3jmpHTlBJ8QVPGrKYd7_B9eGDVqdj"


@pytest.mark.parametrize("desc", sorted(NOT_RESOLVED_FULL))
def test_not_resolved(normalizer, desc):
    r = normalizer.resolve(desc)
    assert (r.status, r.reason) == NOT_RESOLVED_FULL[desc], r.detail


def test_transcript_alleles_match_subset(normalizer, subset_path):
    from rddc_reports.refdata.sequences import StoreSequences

    store = Store(subset_path)
    subset = Normalizer(store, StoreSequences(store))
    for desc, (_g, _d, has_tx) in RESOLVED.items():
        if has_tx:
            assert normalizer.resolve(desc).vrs_transcript["id"] == subset.resolve(desc).vrs_transcript["id"], desc
