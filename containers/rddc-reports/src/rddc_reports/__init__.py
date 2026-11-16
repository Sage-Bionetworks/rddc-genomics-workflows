"""Genetic test reports to normalized findings (RDDC report-findings pipeline)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("rddc-reports")
except PackageNotFoundError:  # running from a source tree
    __version__ = "0+unknown"
