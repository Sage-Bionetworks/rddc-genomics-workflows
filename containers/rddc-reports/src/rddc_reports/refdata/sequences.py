"""Sequence access for hgvs and vrs-python, from the local store or a SeqRepo directory.

Identifiers may be namespaced ("refseq:NC_000017.11", "ga4gh:SQ.…", "GRCh38:17") or bare
accessions ("NC_000017.11", "NM_007294.4"), which are taken as RefSeq. Nothing here falls back
to a network service: an unknown sequence raises KeyError, and a range the store does not hold
raises OutsideReference.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from .store import Store


class OutsideReference(KeyError):
    """The sequence is known but the requested range is not in the local reference data."""


def split_identifier(identifier: str) -> tuple[str, str]:
    if ":" in identifier:
        ns, alias = identifier.split(":", 1)
        if ns.lower() == "ga4gh":
            return "ga4gh", alias.removeprefix("SQ.")
        return ("refseq" if ns.lower() == "refseq" else ns), alias
    return "refseq", identifier


class Sequences(ABC):
    @abstractmethod
    def fetch(self, identifier: str, start: int | None = None, end: int | None = None) -> str: ...

    @abstractmethod
    def metadata(self, identifier: str) -> dict:
        """{"length", "alphabet", "aliases": ["namespace:alias", …]}, as SeqRepo returns."""

    @abstractmethod
    def describe(self) -> str: ...


class StoreSequences(Sequences):
    def __init__(self, store: Store):
        self.store = store

    def _seq_id(self, identifier: str) -> str:
        ns, alias = split_identifier(identifier)
        seq_id = alias if ns == "ga4gh" else self.store.seq_id_for(ns, alias)
        if seq_id is None or not self.store.rows("SELECT 1 FROM seqinfo WHERE seq_id = ?", (seq_id,)):
            raise KeyError(identifier)
        return seq_id

    @lru_cache(maxsize=4096)
    def fetch(self, identifier: str, start: int | None = None, end: int | None = None) -> str:
        seq_id = self._seq_id(identifier)
        length = self.store.rows("SELECT length FROM seqinfo WHERE seq_id = ?", (seq_id,))[0]["length"]
        start = 0 if start is None else start
        end = length if end is None else min(end, length)
        if start >= end:
            return ""
        seg = self.store.rows(
            "SELECT start_i, seq FROM seq_segment WHERE seq_id = ? AND start_i <= ? AND end_i >= ?",
            (seq_id, start, end),
        )
        if not seg:
            raise OutsideReference(f"{identifier}[{start}:{end}] is not in the local reference data")
        s = seg[0]
        return s["seq"][start - s["start_i"]:end - s["start_i"]]

    @lru_cache(maxsize=4096)
    def metadata(self, identifier: str) -> dict:
        seq_id = self._seq_id(identifier)
        info = self.store.rows("SELECT length, alphabet FROM seqinfo WHERE seq_id = ?", (seq_id,))[0]
        aliases = self.store.rows("SELECT namespace, alias FROM seq_alias WHERE seq_id = ?", (seq_id,))
        return {
            "length": info["length"],
            "alphabet": info["alphabet"],
            "aliases": [f"ga4gh:SQ.{seq_id}"]
            + [f"{a['namespace']}:{a['alias']}" for a in aliases if a["namespace"] != "ga4gh"],
        }

    def describe(self) -> str:
        return f"store:{self.store.path.name}"


class SeqRepoSequences(Sequences):
    """A local SeqRepo directory (production). Never the SeqRepo REST service."""

    def __init__(self, root: str):
        from biocommons.seqrepo import SeqRepo

        self.root = root
        self.sr = SeqRepo(root)

    def _uri(self, identifier: str) -> str:
        ns, alias = split_identifier(identifier)
        if ns == "ga4gh":
            return f"ga4gh:SQ.{alias}"
        return f"{'RefSeq' if ns == 'refseq' else ns}:{alias}"

    def fetch(self, identifier: str, start: int | None = None, end: int | None = None) -> str:
        return self.sr.fetch_uri(self._uri(identifier), start, end)

    def metadata(self, identifier: str) -> dict:
        ns, a = self._uri(identifier).split(":", 1)
        found = list(self.sr.aliases.find_aliases(namespace=ns, alias=a))
        if not found:
            raise KeyError(identifier)
        seq_id = found[0]["seq_id"]
        info = self.sr.sequences.fetch_seqinfo(seq_id)
        aliases = self.sr.aliases.find_aliases(seq_id=seq_id)
        return {
            "length": info["len"],
            "alphabet": info["alpha"],
            "aliases": [f"{x['namespace']}:{x['alias']}" for x in aliases],
        }

    def describe(self) -> str:
        return f"seqrepo:{self.root}"
