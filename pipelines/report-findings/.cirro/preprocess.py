"""Point report-findings at the batch's sidecar, before Nextflow starts.

The input dataset is a deposited batch: its files plus `_sidecar.json` at the batch root. The
pipeline finds every other file from the sidecar, so the only parameter set here is
`sidecar`, the full S3 path of that file. A dataset without exactly one root-level
`_sidecar.json` is refused before any compute starts.
"""

from cirro.helpers.preprocess_dataset import PreprocessDataset


def find_sidecar(paths):
    """The `_sidecar.json` with the shortest path (the batch root), if exactly one is there."""
    sidecars = sorted((p for p in paths if p.rsplit("/", 1)[-1] == "_sidecar.json"), key=len)
    if not sidecars:
        raise ValueError("the input dataset has no _sidecar.json")
    root_depth = sidecars[0].count("/")
    at_root = [p for p in sidecars if p.count("/") == root_depth]
    if len(at_root) > 1:
        raise ValueError(f"more than one _sidecar.json at the batch root: {at_root}")
    return at_root[0]


def main():
    ds = PreprocessDataset.from_running()
    sidecar = find_sidecar(list(ds.files["file"]))
    ds.add_param("sidecar", sidecar)
    if not ds.params.get("include_untyped_documents"):
        ds.add_param("include_untyped_documents", False, overwrite=True)


if __name__ == "__main__":
    main()
