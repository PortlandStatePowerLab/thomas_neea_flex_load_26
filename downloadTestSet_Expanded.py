# -*- coding: utf-8 -*-

import os, sys, traceback
from ochre import Analysis
import pandas as pd
from ochre.utils import default_input_path
import datetime
import shutil

def _file_exists_case_insensitive(folder, names):
    """Return True if any of the candidate filenames exists (handles Linux case)."""
    for n in names:
        if os.path.isfile(os.path.join(folder, n)):
            return True
    return False

def downloadTestSet(limit=None):
    # Set constants
    upgrade = 6
    release = "resstock_tmy3_release_1"
    year = '2022'
    xmlName = 'in'
    csvFile = "Oregon50gal.csv"
    csvFilePath = '~/DataFile/Oregon50gal.csv'
    FolderPath = "Input Files"
    subFolder = "Test"
    col = 'bldg_id'
    fail_log = "zfailed_downloads.txt"
    warn_log = "zwarning_log.txt"
    remove_log = 'zremove_log.txt'
    cityId = "in.city"
    city = "Portland"

    # 1) Resolve CSV and verify
    csv_path = os.path.join(default_input_path, FolderPath, csvFile)
    print(f"[INFO] default_input_path = {default_input_path}")
    print(f"[INFO] CSV Path = {csv_path}")
    if not os.path.isfile(csv_path):
        print(f"[ERROR] CSV not found: {csv_path}")
        sys.exit(1)
    else:
        print(f"[INFO] CSV found")
    # 2) Load building list
    df = pd.read_csv(csvFilePath, low_memory=False)
    if col not in df.columns:
        print(f"[ERROR] Column '{col}' not found in CSV. Columns available: {list(df.columns)}")
        sys.exit(1)
    else:
        print(f"[INFO] Column '{col}' found in CSV")
    
    # 2️⃣ Filter only rows where in.city == "Portland"
    if "in.city" in df.columns:
        df_portland = df[df["in.city"].astype(str).str.contains("Portland", case=False, na=False)]
        print(f"[INFO] Found {len(df_portland)} buildings in Portland.")
    else:
        print("[ERROR] Column 'in.city' not found in CSV.")
        sys.exit(1)
        
    # 3) Extract the list of building IDs from the CSV. If a limit is provided,
    # use only the first 'limit' entries for testing or partial runs.
    bldg_list = df['bldg_id'].tolist()
    if limit is not None:
        bldg_list = bldg_list[:int(limit)]

    print(f"[INFO] Buildings to fetch: {len(bldg_list)} (upgrade={upgrade}, release={release}, year={year})")    
    
    # 4) Loop and download
    successes = 0
    failures = 0
    warnings = 0
    downloads = 0
    removes = 0

    # Create fail log if file doesn't exist and write date/time
    if not os.path.exists(fail_log):
        with open(fail_log, "w") as f:
            f.write("[FAILURE LOG]\n")
            f.write("==============================\n")
    with open(fail_log, "a") as f:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"\n\n{timestamp} —----------------------------------------\n")

    # Create warning log if file doesn't download all components and write date/time
    if not os.path.exists(warn_log):
        with open(warn_log, "w") as w:
            w.write("[WARNING LOG]\n")
            w.write("==============================\n")
    with open(warn_log, "a") as w:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        w.write(f"\n\n{timestamp} —----------------------------------------\n")

    # Create remove log if file failed to download or doesn't exist and write date/time
    if not os.path.exists(remove_log):
        with open(remove_log, "w") as r:
            r.write("[REMOVE LOG]\n")
            r.write("==============================\n")
    with open(remove_log, "a") as r:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        r.write(f"\n\n{timestamp} —----------------------------------------\n")

    # 5) Loop over building IDs
    #for _, row in df_portland.iterrows():
        #bldg = row[col]
        #upgrade = row["upgrade"]
        #city = row[cityId]
    for idx, bldg in enumerate(bldg_list, start=1):
        building_id_str = f"bldg{bldg:07}"
        upgrade_str = f"up{upgrade:02}"

        # Define the output directory path for this building and upgrade.
        # Combines the default OCHRE input path, a subfolder name, and a folder
        # specific to the building/upgrade (e.g., bldg0112631-up06).
        outdir = os.path.join(default_input_path, FolderPath, subFolder, f"{building_id_str}-{upgrade_str}")
        
        # Create the directory if it doesn’t already exist; 'exist_ok=True' flag
        # prevents errors if the folder already exists.
        os.makedirs(outdir, exist_ok=True)

        # Checks if files already exists
        expected_file = os.path.join(outdir, xmlName+".xml")
        
        if os.path.exists(expected_file):
            print(f"📁 Already exists: {building_id_str}-{upgrade_str} — Skipping download")
            continue
        
        # Check both cases because Linux is case-sensitive and sources differ
        done = _file_exists_case_insensitive(outdir, [xmlName+".XML", xmlName+".xml"])
        if done:
            print(f"[{idx}/{len(bldg_list)}] 📁 Exists: {building_id_str}-{upgrade_str} — skipping")
            continue
        downloads +=1
        if downloads % 50 == 0:
            print(f"[{idx}/{len(bldg_list)}] ⇣ Downloading: {building_id_str}-{upgrade_str} → {outdir}")

        try:
            #downloads files and unzips them
            Analysis.download_resstock_model(
                building_id=bldg,
                upgrade_id=upgrade,
                local_folder=outdir,
                release=release,
                year=year
            )
            # Post-check
            done = _file_exists_case_insensitive(outdir, [xmlName+".XML", xmlName+".xml"])
            if not done:
                warnings +=1
                # Append to log file
                with open(warn_log, "a") as w:
                    w.write(f"[WARN] Download finished but no ({xmlName}.XML, {xmlName}.xml) found in {outdir}\n")
                    #print(f"[WARN] Download finished but no ({xmlName}.XML, {xmlName}.xml) found in {outdir}")
            else:
                successes += 1
                if successes % 50 == 0:
                    print(f"✅ Downloaded: {building_id_str}-{upgrade_str}")
        except Exception as e:
            failures += 1
            if failures % 50 == 0:
                print(f"❌ Failed: {building_id_str}-{upgrade_str} — {e.__class__.__name__}: {e}")
            
            # Append to log file
            with open(fail_log, "a") as f:
                f.write(f"❌ Failed: {building_id_str}-{upgrade_str} — {e.__class__.__name__}: {e}\n")
                #f.write("=== ERROR TRACEBACK ===\n")
                #traceback.print_exc(file=f)
                #f.write("\n")
                trace = traceback.format_exc()
            if os.path.exists(outdir):
                removes -= 1
                try:
                    shutil.rmtree(outdir)
                    with open(remove_log, "a") as r:
                        r.write(f"🧹 Removed incomplete folder: {outdir}: {e}\n")
                    #print(f"🧹 Removed incomplete folder: {outdir}")
                except Exception as cleanup_error:
                    removes += 1
                    print(f"⚠️ Could not remove folder {outdir}: {cleanup_error}")
            fail = f"❌ Failed: {building_id_str}-{upgrade_str} — {e.__class__.__name__}: {e}\n"
    if removes > 0:
        print(f"[INFO] Removed {removes} files from {default_input_path}/{FolderPath}/{subFolder} (zremove_log.txt)")

    if warnings > 0:
        print(f"[WARN] Download finished with {warnings} warnings but no ({xmlName}.XML, {xmlName}.xml) found in {outdir}")

    if failures > 0:
        with open(fail_log, "a") as f:
            #f.write(f"❌ Failed: {building_id_str}-{upgrade_str} — {e.__class__.__name__}: {e}\n")
            f.write(f"\n=== ERROR TRACEBACK ===\n{trace}")
            #traceback.print_exc(file=f)
            f.write("\n")
        print(f"[INFO] Failure Log amended (zfailed_downloads.txt)")
        print(f"{fail}:\n[INFO] Check zfailed_downloads.txt for more details\n")
    
    if successes > 0:
        print(f"✅ Downloaded {successes} successfully: {building_id_str}-{upgrade_str}")
    print(f"\n[SUMMARY] Success: {successes}  Failures: {failures}  Warnings: {warnings}  Total: {len(bldg_list)}")

    """
    # Delete failure log if there are no failures
    if failures == 0 and os.path.exists(fail_log):
        if os.path.exists(fail_log):
            os.remove(fail_log)
            print("[INFO] All downloads succeeded — deleting fail log.")
        else:
            print(f"[INFO] There are {failures} failures recorded in {fail_log}.")"""
# Ensures that the script only runs when executed directly,
# not when it is imported as a module from another script.
# In that case, Python sets __name__ to "__main__".
if __name__ == "__main__":
    downloadTestSet(limit=5)