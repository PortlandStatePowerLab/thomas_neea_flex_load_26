# -*- coding: utf-8 -*-
"""
Recreate HPWH_OR_50gal.csv, HPWH_OR_66gal.csv, HPWH_OR_80gal.csv, and HPWH_OR_All.csv from
OR_upgrade06_metadata_and_annual_results.csv.

Recovered filter logic:
  - upgrade == 6
  - in.state == "OR"
  - in.city == "OR, Portland"
  - in.geometry_building_type_recs == "Single-Family Detached"
  - split by in.bedrooms:
      1,2,3 -> HPWH_OR_50gal.csv
      4     -> HPWH_OR_66gal.csv
      5     -> HPWH_OR_80gal.csv
  - all three files combined (without bedroom filter) -> HPWH_OR_All.csv
  - Water heaters are sized by number of bedrooms, it is easier to filter by bedrooms than by actual size listed in the file
  - exclude three building IDs that were not present in the original saved files:
      247825, 475397, 264806, 424753

This script preserves the original master-file row order and columns.

Authors Jeff Dinsmore & Thomas Metzler 6/17/2026
"""

from pathlib import Path
import pandas as pd

SOURCE_FILE = Path("OR_upgrade06_metadata_and_annual_results.csv")
OUTPUT_DIR = Path(".")

EXCLUDE_BLDG_IDS = {247825, 475397, 264806, 424753}

EXPECTED_COUNTS = {
    "HPWH_OR_50gal.csv": 434,
    "HPWH_OR_66gal.csv": 145,
    "HPWH_OR_80gal.csv": 39,
    "HPWH_OR_All.csv": 618,
}


def recreate_files(source_file: Path = SOURCE_FILE, output_dir: Path = OUTPUT_DIR) -> None:
    if not source_file.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")

    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(source_file, low_memory=False)

    required_columns = [
        "bldg_id",
        "upgrade",
        "in.state",
        "in.city",
        "in.geometry_building_type_recs",
        "in.bedrooms",
    ]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    base_filter = (
        (df["upgrade"] == 6)
        & (df["in.state"] == "OR")
        & (df["in.city"] == "OR, Portland")
        & (df["in.geometry_building_type_recs"] == "Single-Family Detached")
        & (~df["bldg_id"].isin(EXCLUDE_BLDG_IDS))
    )

    outputs = {
        "HPWH_OR_50gal.csv": df[base_filter & df["in.bedrooms"].isin([1, 2, 3])],
        "HPWH_OR_66gal.csv": df[base_filter & (df["in.bedrooms"] == 4)],
        "HPWH_OR_80gal.csv": df[base_filter & (df["in.bedrooms"] == 5)],
        "HPWH_OR_All.csv": df[base_filter],
    }

    for filename, out_df in outputs.items():
        output_path = output_dir / filename
        out_df.to_csv(output_path, index=False)

        expected = EXPECTED_COUNTS[filename]
        actual = len(out_df)
        status = "OK" if actual == expected else "CHECK"
        print(f"[{status}] {filename}: wrote {actual} rows to {output_path}")
        if actual != expected:
            print(f"       Expected {expected} rows")


if __name__ == "__main__":
    recreate_files()
