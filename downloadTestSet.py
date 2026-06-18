
"""
@Author: jdeline
@Modified on 4/14/2026


downloadTestSet.py takes a csv in the up06 folder (currently set to "Oregon80gal.csv") and downloads the corresponding
HPXML files for each building in the csv. It filters for Portland buildings only. 
The downloaded files are saved in the "Input Files/bldg" folder, organized by building ID and upgrade level.

Modified for 50gal by Thomas Metzler on 6/17/2026
"""


# -*- coding: utf-8 -*-

import os
from ochre import Analysis
import pandas as pd
from ochre.utils import default_input_path

input_file = "Oregon50gal.csv"



def downloadTestSet():

    # -----------------------------
    # PATH SETUP (FIXED)
    # -----------------------------
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)

    csvFilePath = os.path.join(
        project_dir,
        "Flex_Load",
        input_file
    )

    print(f"[INFO] CSV Path: {csvFilePath}")

    # -----------------------------
    # LOAD CSV
    # -----------------------------
    df = pd.read_csv(csvFilePath, low_memory=False)
    bldg_list = df['bldg_id'].tolist()

    # -----------------------------
    # CONSTANTS
    # -----------------------------
    upgrade = 6
    release = "resstock_tmy3_release_1"
    yr = "2022"

    base_output = os.path.join(project_dir, "Input Files", "bldg")

    print(f"[INFO] Base output directory: {base_output}")

    # -----------------------------
    # LOOP
    # -----------------------------
    for bldg in bldg_list:

        building_id_str = f"bldg{int(bldg):07}"
        upgrade_str = f"up{upgrade:02}"

        outdir = os.path.join(base_output, f"{building_id_str}-{upgrade_str}")

        os.makedirs(outdir, exist_ok=True)

        expected_file = os.path.join(outdir, "in.xml")

        # skip if already exists
        if os.path.exists(expected_file):
            print(f"📁 Exists: {building_id_str}-{upgrade_str} — skipping")
            continue

        try:
            Analysis.download_resstock_model(
                building_id=int(bldg),
                upgrade_id=upgrade,
                local_folder=outdir,
                release=release,
                year=yr
            )

            print(f"✅ Downloaded: {building_id_str}-{upgrade_str}")

        except Exception as e:
            print(f"❌ Failed: {building_id_str}-{upgrade_str} — {e}")


if __name__ == "__main__":
    downloadTestSet()