import os
import socket
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SUBSET = REPO / "tests" / "report-findings" / "refdata" / "subset.sqlite"


def _no_network(*_a, **_k):
    raise OSError("network access is disabled in tests")


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    """Every test runs without network unless marked `live`. Normalization must be local."""
    if request.node.get_closest_marker("live"):
        if not os.environ.get("RDDC_REPORTS_LIVE"):
            pytest.skip("set RDDC_REPORTS_LIVE=1 to compare with live UTA/NCBI")
        return
    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    monkeypatch.setattr(socket, "getaddrinfo", _no_network)


def pytest_configure(config):
    config.addinivalue_line("markers", "live: compares with live UTA/NCBI (opt-in, RDDC_REPORTS_LIVE=1)")


@pytest.fixture(scope="session")
def alignments_path(subset_path):
    """Store for the SeqRepo tests: RDDC_REPORTS_REFDATA (e.g. a full export) or the subset."""
    p = os.environ.get("RDDC_REPORTS_REFDATA")
    return Path(p) if p else subset_path


@pytest.fixture(scope="session")
def subset_path():
    if not SUBSET.exists():
        pytest.skip(f"reference subset missing: {SUBSET} (make refdata-test)")
    return SUBSET
