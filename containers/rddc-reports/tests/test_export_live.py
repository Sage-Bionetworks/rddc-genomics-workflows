"""Opt-in check of a full UTA export against live UTA (RDDC_REPORTS_LIVE=1, plus
RDDC_REPORTS_REFDATA = the export and RDDC_REPORTS_SEQREPO = the matching SeqRepo).

Projects random positions on a random sample of exported transcripts with the local store
and with hgvs on the public UTA server, both reading sequences from the same SeqRepo, so a
difference can only come from the exported alignment rows. Sends transcript accessions and
synthetic positions only. Slow: about an hour per 50 transcripts on the public server
(300 transcripts took 5.5 hours on 2026-11-15; all projections agreed). Set
RDDC_REPORTS_SAMPLE for a smaller sample.
"""

import os
import random

import pytest

from rddc_reports import versions

pytestmark = pytest.mark.live
N_TRANSCRIPTS = int(os.environ.get("RDDC_REPORTS_SAMPLE", "300"))


def test_sample_projects_like_live_uta():
    refdata, seqrepo = os.environ.get("RDDC_REPORTS_REFDATA"), os.environ.get("RDDC_REPORTS_SEQREPO")
    if not (refdata and seqrepo):
        pytest.skip("needs RDDC_REPORTS_REFDATA and RDDC_REPORTS_SEQREPO")

    import hgvs.assemblymapper
    import hgvs.dataproviders.uta as uta
    import hgvs.parser
    from hgvs.dataproviders.seqfetcher import SeqFetcher

    os.environ["HGVS_SEQREPO_DIR"] = seqrepo
    live = uta.connect(versions.PUBLIC_UTA_URL)
    live.seqfetcher = SeqFetcher()             # reads HGVS_SEQREPO_DIR: same sequences as local
    am_live = hgvs.assemblymapper.AssemblyMapper(live, assembly_name="GRCh38", alt_aln_method="splign",
                                                 replace_reference=True)

    from rddc_reports.refdata.hgvs_provider import LocalDataProvider
    from rddc_reports.refdata.sequences import SeqRepoSequences
    from rddc_reports.refdata.store import Store

    store = Store(refdata)
    local = LocalDataProvider(store, SeqRepoSequences(seqrepo))
    am_local = hgvs.assemblymapper.AssemblyMapper(local, assembly_name="GRCh38", alt_aln_method="splign",
                                                  replace_reference=True)
    parser = hgvs.parser.Parser()

    rng = random.Random(20241220)
    txs = store.rows("SELECT tx_ac, cds_start_i, cds_end_i FROM tx_info "
                     "WHERE tx_ac LIKE 'NM_%' AND cds_start_i IS NOT NULL ORDER BY tx_ac")
    sample = rng.sample(txs, N_TRANSCRIPTS)
    checked, differ = 0, []
    for t in sample:
        cds_len = t["cds_end_i"] - t["cds_start_i"]
        for pos in sorted({1, cds_len, rng.randint(1, cds_len)}):
            var = parser.parse_hgvs_variant(f"{t['tx_ac']}:c.{pos}del")
            want = None
            for _attempt in range(2):   # the public server drops connections on long runs
                try:
                    want = str(am_live.c_to_g(var))
                    break
                except Exception as e:   # noqa: BLE001 - compare failures too
                    want = f"error:{type(e).__name__}"
            try:
                got = str(am_local.c_to_g(var))
            except Exception as e:   # noqa: BLE001
                got = f"error:{type(e).__name__}"
            checked += 1
            if got != want:
                differ.append((str(var), got, want))
    print(f"{checked} projections on {len(sample)} transcripts; {len(differ)} differ")
    assert not differ, differ[:20]
