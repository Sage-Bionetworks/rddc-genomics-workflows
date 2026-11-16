"""Reference-data releases this version of rddc-reports expects.

The test subset is built from EXPECTED_UTA, and production should stage the same UTA release
with the SeqRepo snapshot of the same date. Change these together with the subset
(`make refdata-test`), the expected values in tests/test_normalize.py, and the README table.
"""

EXPECTED_UTA = "uta_20241220"
EXPECTED_SEQREPO = "2024-12-20"
EXPECTED_ASSEMBLY = "GRCh38"

PUBLIC_UTA_URL = f"postgresql://anonymous:anonymous@uta.biocommons.org/uta/{EXPECTED_UTA}"
SEQREPO_RSYNC = f"dl.biocommons.org::seqrepo/{EXPECTED_SEQREPO}/"
