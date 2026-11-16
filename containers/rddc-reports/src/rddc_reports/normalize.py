"""Validate an HGVS description against local reference data and derive VRS Alleles.

Policy (PLAN.md, "Normalization policy"):
- Only descriptions with a versioned RefSeq accession are considered. An unversioned or missing
  accession is `unresolved`, never completed with a default (MANE, latest version, assembly).
- Validation is hgvs's: syntax, reference bases, and bounds against the stored sequences.
- c./n. descriptions get a VRS Allele on the transcript (when exonic) and, through the stored
  splign alignment, a GRCh38 genomic description and VRS Allele. g. descriptions get a genomic
  Allele. p. descriptions get a protein-level Allele on their protein accession only; they are
  never projected to a genomic allele. A parenthesized p.(…) is resolved with predicted=True.
- Anything that fails is returned with a reason code; nothing is dropped.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

import hgvs.assemblymapper
import hgvs.exceptions
import hgvs.parser
import hgvs.validator

from .refdata.hgvs_provider import LocalDataProvider
from .refdata.sequences import OutsideReference, Sequences
from .refdata.store import Store
from .refdata.vrs_proxy import LocalAlleleTranslator, LocalDataProxy, forbid_network_reference

VERSIONED_AC = re.compile(r"^(NM|NR|NC|NG|NP|XM|XR|XP)_\d+\.\d+$")
UNVERSIONED_AC = re.compile(r"^(NM|NR|NC|NG|NP|XM|XR|XP)_\d+$")
SUPPORTED_TYPES = {"c", "n", "g", "p"}


@dataclass
class Resolution:
    input: str
    status: str                       # resolved | unresolved | invalid
    reason: str | None = None         # reason code when not resolved
    detail: str | None = None
    predicted: bool = False           # p.(…): the laboratory's predicted protein consequence
    hgvs_normalized: str | None = None
    hgvs_genomic: str | None = None
    vrs_transcript: dict | None = None
    vrs_genomic: dict | None = None
    vrs_protein: dict | None = None
    reference: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


class Normalizer:
    def __init__(self, store: Store, sequences: Sequences, assembly: str = "GRCh38"):
        forbid_network_reference()
        self.store = store
        self.hdp = LocalDataProvider(store, sequences)
        self.parser = hgvs.parser.Parser()
        self.validator = hgvs.validator.Validator(self.hdp)
        self.am = hgvs.assemblymapper.AssemblyMapper(
            self.hdp, assembly_name=assembly, alt_aln_method="splign",
            replace_reference=False, prevalidation_level="EXTRINSIC")
        self.translator = LocalAlleleTranslator(LocalDataProxy(sequences), self.hdp, default_assembly_name=assembly)
        self.reference = {
            "uta_version": store.meta("uta_version"),
            "sequences": sequences.describe(),
            "assembly": assembly,
        }

    def resolve(self, description: str) -> Resolution:
        r = Resolution(input=description, status="unresolved", reference=self.reference)
        text = description.strip()
        ac = text.split(":", 1)[0] if ":" in text else ""
        if not ac:
            return self._fail(r, "unresolved", "missing_accession")
        if UNVERSIONED_AC.match(ac):
            return self._fail(r, "unresolved", "missing_accession_version")
        if not VERSIONED_AC.match(ac):
            return self._fail(r, "unresolved", "unsupported_accession", ac)

        try:
            var = self.parser.parse_hgvs_variant(text)
        except hgvs.exceptions.HGVSParseError as e:
            return self._fail(r, "invalid", "unparseable", str(e))
        if var.type not in SUPPORTED_TYPES:
            return self._fail(r, "unresolved", "unsupported_variant_type", var.type)
        if var.posedit is None or var.posedit.edit is None:
            return self._fail(r, "unresolved", "no_change_described", text)
        if var.type != "p" and _has_uncertain_position(var):
            return self._fail(r, "unresolved", "uncertain_description", str(var.posedit))
        if getattr(var.posedit, "uncertain", False):
            if var.type != "p":
                return self._fail(r, "unresolved", "uncertain_description", str(var.posedit))
            # p.(Cys61Gly) is a prediction, not an observation; keep the flag.
            r.predicted = True
            var.posedit.uncertain = False

        try:
            if var.type in ("c", "n") and _is_intronic(var):
                # hgvs cannot check intronic bases on the transcript: check syntax here and the
                # reference base on the genomic projection below.
                self.validator.validate(var, strict=False)
            else:
                self.validator.validate(var)
        except OutsideReference as e:
            return self._fail(r, "unresolved", "outside_reference_data", str(e))
        except hgvs.exceptions.HGVSDataNotAvailableError as e:
            return self._fail(r, "unresolved", "reference_not_available", str(e))
        except hgvs.exceptions.HGVSInvalidVariantError as e:
            return self._fail(r, "invalid", "failed_validation", str(e))
        except KeyError as e:
            return self._fail(r, "unresolved", "reference_not_available", str(e))

        try:
            if var.type == "p":
                r.hgvs_normalized = str(var)
                r.vrs_protein = self._vrs(str(var))
            elif var.type in ("c", "n"):
                g = self.am.c_to_g(var) if var.type == "c" else self.am.n_to_g(var)
                if _is_intronic(var):
                    try:
                        self.validator.validate(g)
                    except hgvs.exceptions.HGVSInvalidVariantError as e:
                        return self._fail(r, "invalid", "failed_validation", f"{g}: {e}")
                r.hgvs_genomic = str(g)
                r.hgvs_normalized = str(self.am.g_to_c(g, var.ac) if var.type == "c" else self.am.g_to_n(g, var.ac))
                if not _is_intronic(var):
                    r.vrs_transcript = self._vrs(str(var))
                r.vrs_genomic = self._vrs(str(g))
            else:
                r.hgvs_genomic = r.hgvs_normalized = str(var)
                r.vrs_genomic = self._vrs(str(var))
        except OutsideReference as e:
            return self._fail(r, "unresolved", "outside_reference_data", str(e))
        except hgvs.exceptions.HGVSError as e:
            return self._fail(r, "unresolved", "projection_failed", str(e))
        except ValueError as e:
            return self._fail(r, "unresolved", "vrs_unsupported", str(e))

        r.status = "resolved"
        return r

    def _vrs(self, expr: str) -> dict:
        allele = self.translator.translate_from(expr, "hgvs")
        if allele is None:
            raise ValueError(f"vrs-python could not translate {expr}")
        return allele.model_dump(exclude_none=True)

    @staticmethod
    def _fail(r: Resolution, status: str, reason: str, detail: str | None = None) -> Resolution:
        r.status, r.reason, r.detail = status, reason, detail
        return r


def _has_uncertain_position(var) -> bool:
    pos = var.posedit.pos
    return bool(getattr(pos, "uncertain", False)) or any(
        getattr(p, "uncertain", False) for p in (getattr(pos, "start", None), getattr(pos, "end", None)) if p)


def _is_intronic(var) -> bool:
    pos = var.posedit.pos
    return any(getattr(p, "offset", 0) for p in (pos.start, pos.end) if p is not None)
