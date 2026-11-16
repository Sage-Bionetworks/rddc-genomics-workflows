"""Check that the reference data a run was given is the expected release and works.

Run once per pipeline run, before normalization. Confirms the store's UTA release and the
sequence source, then resolves known variants and compares them with known VRS identifiers
(checked against live UTA and full sequences; see tests/test_normalize.py). A store without
sequences needs a SeqRepo directory.
"""

from __future__ import annotations

from pathlib import Path

from .. import versions

# description → (genomic HGVS, VRS id of the genomic or protein allele)
CANARIES = {
    "NM_007294.4:c.68_69del": ("NC_000017.11:g.43124030_43124031del", "ga4gh:VA.EE08XW4IpzeWhJAwComKOSmsPHTcP-1R"),
    "NM_000492.4:c.1521_1523del": ("NC_000007.14:g.117559592_117559594del", "ga4gh:VA.1XMYiWeH-zAzuRLwPcJGQaQ1MHV5Sf0n"),
    "NP_009225.1:p.Cys61Gly": (None, "ga4gh:VA.x_z3jmpHTlBJ8QVPGrKYd7_B9eGDVqdj"),
}


def check_reference(refdata: str, seqrepo: str | None = None) -> dict:
    from ..normalize import Normalizer
    from .sequences import SeqRepoSequences, StoreSequences
    from .store import Store

    store = Store(refdata)
    problems: list[str] = []
    meta = {r["key"]: r["value"] for r in store.rows("SELECT key, value FROM meta")}
    if meta.get("uta_version") != versions.EXPECTED_UTA:
        problems.append(f"store has UTA {meta.get('uta_version')}, expected {versions.EXPECTED_UTA}")

    if seqrepo:
        sequences = SeqRepoSequences(seqrepo)
        name = Path(seqrepo).resolve().name
        if name != versions.EXPECTED_SEQREPO:
            problems.append(f"SeqRepo directory is {name!r}, expected {versions.EXPECTED_SEQREPO!r}")
    elif meta.get("contains_sequences") == "false":
        problems.append("the store holds no sequences and no SeqRepo directory was given")
        sequences = None
    else:
        sequences = StoreSequences(store)

    canaries = {}
    if sequences is not None:
        n = Normalizer(store, sequences)
        for desc, (want_g, want_id) in CANARIES.items():
            r = n.resolve(desc)
            got_id = (r.vrs_protein or r.vrs_genomic or {}).get("id")
            ok = r.status == "resolved" and r.hgvs_genomic == want_g and got_id == want_id
            canaries[desc] = {"ok": ok, "status": r.status, "reason": r.reason, "hgvs_genomic": r.hgvs_genomic,
                              "vrs_id": got_id, "expected_vrs_id": want_id}
            if not ok:
                problems.append(f"canary {desc}: {r.status} {r.reason or ''} {got_id}".strip())

    return {
        "ok": not problems,
        "problems": problems,
        "expected": {"uta": versions.EXPECTED_UTA, "seqrepo": versions.EXPECTED_SEQREPO,
                     "assembly": versions.EXPECTED_ASSEMBLY},
        "store": {"path": str(refdata), **meta},
        "sequences": sequences.describe() if sequences else None,
        "canaries": canaries,
    }
