# rddc-reports

Python code of the report-findings pipeline, packaged as the image the modules pin
(`ghcr.io/sage-bionetworks/rddc-reports:<version>`, version from `pyproject.toml`). Each module
calls one `rddc-reports` subcommand.

| Command | Does |
| --- | --- |
| `rddc-reports version` | package and library versions (JSON) |
| `rddc-reports normalize --refdata store.sqlite [--seqrepo DIR]` | HGVS descriptions (one per line) → validation result, genomic projection and VRS Alleles (JSONL) |
| `rddc-reports refdata build-subset --transcripts list --out store.sqlite` | reference subset for test fixtures, from public UTA and NCBI |
| `rddc-reports refdata export --out uta_20241220.sqlite` | full UTA export: every GRCh38 splign alignment, no sequences (use with SeqRepo) |
| `rddc-reports refdata check --refdata store [--seqrepo DIR]` | expected releases present, known variants resolve to known VRS IDs; exit 1 otherwise |

Expected reference-data releases (UTA, SeqRepo) and library versions are listed in the
pipeline README, [Expected versions](../../pipelines/report-findings/README.md#expected-versions),
and set in `src/rddc_reports/versions.py`.

## Reference data, locally

Validation and normalization never use a network service. `refdata/` provides:

- `Store`: one SQLite file with transcript alignments in the shape of hgvs's UTA rows, and
  sequences, stored whole or as windows. A windowed chromosome keeps its full length and GA4GH
  digest, so VRS identifiers are the real ones.
- `LocalDataProvider`: hgvs data provider over the store (replaces UTA/Postgres).
- `LocalDataProxy`, `LocalAlleleTranslator`: vrs-python over the same sequences. vrs-python's
  own `HgvsTools` connects to the public UTA when created, and hgvs falls back to NCBI for
  sequences; `forbid_network_reference()` disables both in the process.
- `SeqRepoSequences`: sequences from a local SeqRepo directory, for production. SeqRepo stores
  RefSeq accessions under its `NCBI` namespace; the seqrepo library translates `refseq:` and adds
  the `ga4gh:SQ.` alias, so no mapping is needed here.

`tests/test_normalize.py` runs with sockets disabled (and `make py-test` runs it in the image with
`--network none`). Its expected genomic descriptions and VRS IDs were checked against hgvs on
live UTA with NCBI sequences, and against VRS on full chromosomes; `make py-test-live` repeats
that comparison (`tests/test_live.py`, network). `make py-test-seqrepo SEQREPO=<dir>` runs the
same expectations with sequences from a full SeqRepo snapshot, without network
(`tests/test_seqrepo.py`); add `REFDATA=<store>` to use a full export.
`tests/test_export_live.py` (network, opt-in) projects random positions on a sample of
exported transcripts locally and with hgvs on live UTA, both reading the same SeqRepo.

## Development without Docker

hgvs depends on `psycopg2`, which builds from source. In a local venv:

```
uv venv .venv && . .venv/bin/activate
uv pip install psycopg2-binary "ga4gh.vrs==2.3.3" "biocommons.seqrepo==0.6.11" bioutils parsley attrs configparser ipython pytest
uv pip install --no-deps "hgvs==1.5.7" -e .
python -m pytest
```
