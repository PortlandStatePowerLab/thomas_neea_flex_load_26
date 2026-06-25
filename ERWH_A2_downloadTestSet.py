
"""
@Author: jdeline
@Modified on 4/14/2026


downloadTestSet.py takes a csv  and downloads the corresponding
HPXML files for each building in the csv. It filters for Portland buildings only. 
The downloaded files are saved in the "Input Files/bldg" folder, organized by building ID and upgrade level.

Modified by Thomas Metzler on 6/25/2026
"""


# -*- coding: utf-8 -*-

import os
from ochre import Analysis
import pandas as pd
from ochre.utils import default_input_path


# "ERWH_OR_50gal.csv","ERWH_OR_66gal.csv","ERWH_OR_80gal.csv","ERWH_OR_All.csv"
# "ERWH 50 Input Files","ERWH 66 Input Files","ERWH 80 Input Files","ERWH All Input Files"
input_file_50 = "ERWH_OR_50gal.csv"
Output_folder_50 = "ERWH 50 Input Files"

input_file_66 = "ERWH_OR_66gal.csv"
Output_folder_66 = "ERWH 66 Input Files"

input_file_80 = "ERWH_OR_80gal.csv"
Output_folder_80 = "ERWH 80 Input Files"

input_file_All = "ERWH_OR_All.csv"
Output_folder_All = "ERWH All Input Files"

def downloadTestSet(input_file, Output_folder):

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
    upgrade = 9
    release = "resstock_amy2018_release_1"
    yr = "2025"

    base_output = os.path.join(project_dir, Output_folder, "bldg")

    print(f"[INFO] Base output directory: {base_output}")

    # -----------------------------
    # LOOP
    # -----------------------------
    for bldg in bldg_list:

        building_id_str = f"bldg{int(bldg):07}"
        upgrade_str = f"up{upgrade:02}"


        outdir = os.path.join(base_output, f"{building_id_str}-{upgrade_str}")

        os.makedirs(outdir, exist_ok=True)

        #in.xml for 2022
        #expected_file = os.path.join(outdir, "in.xml")
        expected_file = os.path.join(outdir, "home.xml")

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
    downloadTestSet(input_file_50, Output_folder_50)
    downloadTestSet(input_file_66, Output_folder_66)
    downloadTestSet(input_file_80, Output_folder_80)
    downloadTestSet(input_file_All, Output_folder_All)