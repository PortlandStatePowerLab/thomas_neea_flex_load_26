'''
Author: Midrar Adham
Date: 11/01/2025

Edited: Thomas Metzler
Date 6/16/2026

This script processes and downloads the ResStock 2022 upgrade 6 dataset.

REQUIREMENTS:

- Download the OR_upgrade06_metadata_and_annual_results.csv file and make sure it is in the same
path as this script.

- Make necessary changes to the Analysis.py file as indicated in the tutorial documentation from Dana Paresa

- This will save the files for each building in a folder called datasets one folder up from this script
so that it does not save datasets in the github respository.
'''

import os
import pandas as pd
from pathlib import Path
from ochre import Analysis


def process_metdata (original_data):
    # Read the file
    df = pd.read_csv(original_data, low_memory=False)

    # Group by the city column
    df_city = df.groupby(by='in.city')

    # Identify Portland and save its data
    for id, group in df_city:
        if id == 'OR, Portland':
            df_weather = group


    # Sort the data by bedrooms number:
    df_weather = df_weather.sort_values(by='in.bedrooms', ascending=True)
    df_weather = df_weather.reset_index()

    # Not needed, but in case. Write the updated file to a csv so we can download the load files using ochre
    # df_weather.to_csv('./OR_upgrade0_filtered.csv', index=False)

    return df_weather


def create_dir():
    '''
    This function is called in process_metadata

    From ochre developers: 
        Create a folder called 'cosimulation' to store all files
    '''
    # Root exposes the current directory (where this script lives)
    root = Path (__file__).resolve().parent
    # main_path is the directory where the load profiles live
    main_path = root.parent / 'load_profiles' / 'cosimulation'
    # Create the directories if they don't exist
    main_path.mkdir(parents=True, exist_ok=True)
    return main_path

def download_files (filtered_data):
    # Get the main path of where we're storing the new files
    main_path = create_dir()

    # Read the filtered data
    # df = pd.read_csv(filtered_data,usecols=['bldg_id'])
    building_ids = filtered_data['bldg_id'].to_list()
    upgrades = ["up06"]

    i = 0
    for building in building_ids:

        for upgrade in upgrades:
            i += 1

            input_path = os.path.join(main_path, str(building), upgrade)
            os.makedirs(input_path, exist_ok=True)
            Analysis.download_resstock_model(building_id=building,upgrade_id=upgrade,
                                            local_folder='../datasets/', overwrite=False,
                                            year="2022", release="resstock_tmy3_release_1")
            print(f"Run number {i} is done for building {building}/{upgrade}")
    
    return main_path

if __name__ == '__main__':
    
    metadata = './OR_upgrade06_metadata_and_annual_results.csv'
    df = process_metdata(original_data=metadata)
    df = df.drop('index', axis=1)
    main_path = download_files(filtered_data=df)
    # main_path = create_dir()
    # check_dir(main_path=main_path)