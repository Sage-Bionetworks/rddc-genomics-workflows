"""Write the samplesheet for fastq-qc from the input dataset, before Nextflow starts.

Cirro has already matched the dataset's files to samples using the data type's file
mapping rules (in rddc-cirro-config). `ds.files` has one row per file with `sample`,
`file`, and the named groups from those rules, such as `read` (1 or 2) and `lane`.
"""

from cirro.helpers.preprocess_dataset import PreprocessDataset


def samplesheet(files):
    """One row per sample (and lane, if present) with columns sample, fastq_1, fastq_2."""
    files = files.copy()
    if "read" not in files.columns:
        files["read"] = 1
    files["read"] = files["read"].fillna(1).astype(int)
    keys = ["sample"] + (["lane"] if "lane" in files.columns else [])

    dupes = files[files.duplicated(keys + ["read"], keep=False)]
    if not dupes.empty:
        raise ValueError(f"more than one file per sample and read:\n{dupes.to_string(index=False)}")

    wide = files.pivot(index=keys, columns="read", values="file").reset_index()
    wide = wide.rename(columns={1: "fastq_1", 2: "fastq_2"})
    if "fastq_2" not in wide.columns:
        wide["fastq_2"] = ""
    if wide["fastq_1"].isna().any():
        raise ValueError("some samples have a read 2 file but no read 1 file")
    if "lane" in wide.columns:
        # FastQC names reports after the file, so per-lane rows only need distinct ids
        wide["sample"] = wide["sample"] + "_L" + wide["lane"].astype(str)
    return wide[["sample", "fastq_1", "fastq_2"]].fillna("")


def main():
    ds = PreprocessDataset.from_running()
    sheet = samplesheet(ds.files)
    ds.logger.info(f"samplesheet with {len(sheet)} rows:\n{sheet.to_csv(index=False)}")
    sheet.to_csv("samplesheet.csv", index=False)
    ds.add_param("input", "samplesheet.csv")


if __name__ == "__main__":
    main()
