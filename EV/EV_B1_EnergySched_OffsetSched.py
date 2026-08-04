# -*- coding: utf-8 -*-
"""
Created on Wed Sep  3 17:39:26 2025
Modified on Nov 19 2025
Modified on Jul 31 2026

@author: danap
@edited by: jdinsmor
@edited by: t-metzler
"""

import os
import shutil
import datetime as dt
import pandas as pd
import xml.etree.ElementTree as ET
from ochre import Dwelling
from ochre.utils.schedule import ALL_SCHEDULE_NAMES
import concurrent.futures
from pathlib import Path
import ochre

#########################################
# USER SETTINGS & EV CONFIGURATION
#########################################

filename = 'EV_Test_2'
Input_folder = "EV Input Files"

# EV Control Settings
CONTROL_MODE = 'load_fraction' # Choose 'load_fraction' or 'p_setpoint'
DEFAULT_CHARGER_POWER_W = 5600 # Fallback 1600 for Level 1, 5600 for Level 2 (Dynamically checked per home below)

# Setpoint Multipliers (1.0 = 100% capacity)
LOAD_UP_PCT = 1.0   # Force charge at max capacity
SHED_PCT = 0.25     # Shed capacity (e.g., charge at only 25% max power)
V2G_PCT = -1.0      # Vehicle to Grid (Negative indicates discharging back to grid)

# Original OCHRE defaults folder
ochre_dir = Path(ochre.__file__).resolve().parent
DEFAULT_INPUT = ochre_dir / "defaults" / "Input Files"
print("OCHRE installed at:", ochre_dir)

DEFAULT_WEATHER = ochre_dir / "defaults" / "Weather" / "USA_OR_Portland.Intl.AP.726980_TMY3.epw"
#DEFAULT_WEATHER = ochre_dir / "defaults" / "Weather" / "G4100510_2018.csv" 
# ^ Incorrect format for the weather file, it doesn't want csv
# G4100510 is Multnomah county weather station, code will complain this is missing but it doesn't work otherwise

# Safe working folder (writable)
script_dir = os.path.dirname(os.path.abspath(__file__))
fl_dir = os.path.dirname(script_dir)
WORKING_DIR = os.path.dirname(fl_dir)
INPUT_DIR = os.path.join(WORKING_DIR, Input_folder, "bldg")
WEATHER_DIR = os.path.join(WORKING_DIR, "Weather")
WEATHER_FILE = os.path.join(WEATHER_DIR, "USA_OR_Portland.Intl.AP.726980_TMY3.epw")
XML_ADDRESS = "home.xml"
CSV_ADDRESS = "in.schedules.csv"

# Simulation parameters
Start = dt.datetime(2018, 1, 11, 0, 0)
Duration = 2  # days
t_res = 15  # minutes
count = 0

# Schedule variant (Added V2G time block)
my_schedule1 = {
    'M_LU_time': '06:30',
    'M_LU_duration': 1,
    'M_S_time': '07:30',
    'M_S_duration': 4,
    'E_ALU_time': '13:00',
    'E_ALU_duration': 1,
    'E_S_time': '14:00',
    'E_S_duration': 4,
    'V2G_time': '18:00',     # Vehicle-to-Grid start time
    'V2G_duration': 3        # Vehicle-to-Grid duration
}

def shift_time(time_str, minutes):
    """Helper function to add minutes to an 'HH:MM' string."""
    # Using 'dt' to match your 'import datetime as dt' alias perfectly
    delta_t = dt.datetime.strptime(time_str, '%H:%M')
    new_delta_t = delta_t + dt.timedelta(minutes=minutes)
    return new_delta_t.strftime('%H:%M')

# List to hold all generated schedules
my_schedule = []

#minutes you will offset schedules
timestep = 30

#number of bins
bins = 8

# Generate schedules with offsets
for i in range(bins):
    offset = i * timestep  
    new_sched = my_schedule1.copy()
    
    for key, value in new_sched.items():
        # Check if the key is a time variable
        if key.endswith('_time'):
            # Shift the start time
            new_sched[key] = shift_time(value, offset)
            
        # Note: durations remain exactly the same across all schedules
            
    my_schedule.append(new_sched)

#########################################
# EV CONTROL FUNCTION
#########################################

def determine_EV_control(sim_time, sched_cfg, control_mode, charger_w):
    ctrl_signal = {'EV': {}}
    base_date = sim_time.date()
    
    def get_time_range(key_prefix):
        if f'{key_prefix}_time' not in sched_cfg:
            return None, None
        start = pd.to_datetime(f"{base_date} {sched_cfg[f'{key_prefix}_time']}")
        end = start + pd.Timedelta(hours=sched_cfg[f'{key_prefix}_duration'])
        return start, end

    ranges = {
        'Load_Up_M': get_time_range('M_LU'),
        'Load_Up_E': get_time_range('E_ALU'),
        'Shed_M': get_time_range('M_S'),
        'Shed_E': get_time_range('E_S'),
        'V2G': get_time_range('V2G'),
    }

    # Determine current operational state
    state = 'Normal'
    for state_name, (start, end) in ranges.items():
        if start and end and start <= sim_time < end:
            if 'Load_Up' in state_name:
                state = 'Load_Up'
            elif 'Shed' in state_name:
                state = 'Shed'
            elif 'V2G' in state_name:
                state = 'V2G'
            break 
            
    if state == 'Normal':
        return {} # Return empty to let OCHRE run the default schedule

    # Map state to percentage
    if state == 'Load_Up':
        fraction = LOAD_UP_PCT
    elif state == 'Shed':
        fraction = SHED_PCT
    elif state == 'V2G':
        fraction = V2G_PCT

    # Format the control signal
    if control_mode == 'load_fraction':
        ctrl_signal['EV']['Load Fraction'] = fraction
    elif control_mode == 'p_setpoint':
        ctrl_signal['EV']['P Setpoint'] = fraction * charger_w 
        
    return ctrl_signal

#########################################
# SCHEDULE FILTERING
#########################################

def filter_schedules(home_path):
    orig_sched_file = os.path.join(home_path, CSV_ADDRESS)
    filtered_sched_file = os.path.join(home_path, 'filtered_schedules.csv')

    df_sched = pd.read_csv(orig_sched_file)
    valid_schedule_names = set(ALL_SCHEDULE_NAMES.keys())
    filtered_columns = [col for col in df_sched.columns if col in valid_schedule_names]
    dropped_columns = [col for col in df_sched.columns if col not in filtered_columns]
    if dropped_columns:
        print(f"Dropped invalid schedules for {home_path}: {dropped_columns}")

    df_sched_filtered = df_sched[filtered_columns]
    df_sched_filtered.to_csv(filtered_sched_file, index=False)
    return filtered_sched_file

#########################################
# CHARGER PARSER HELPER
#########################################

def get_ev_charger_power(hpxml_path, default_w=5600):
    """
    Parses the home's HPXML file to determine if the EV uses a Level 1 or Level 2 charger.
    Returns 1600 for Level 1, 5600 for Level 2.
    """
    try:
        tree = ET.parse(hpxml_path)
        root = tree.getroot()
        
        # Remove namespaces for easier tag matching
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]
                
        for ev in root.findall('.//ElectricVehicle'):
            level_elem = ev.find('ChargerLevel')
            if level_elem is not None and level_elem.text:
                text_val = level_elem.text.strip().lower()
                if '1' in text_val:
                    return 1600
                elif '2' in text_val:
                    return 5600
    except Exception as e:
        print(f"[WARNING] Failed to parse EV charger level from {hpxml_path}. Using default {default_w}. Error: {e}")
    
    return default_w

#########################################
# SIMULATION FUNCTION
#########################################

def simulate_home(home_path, weather_file_path, schedule_cfg):

    filtered_sched_file = filter_schedules(home_path)
    hpxml_file = os.path.join(home_path, XML_ADDRESS)
    results_dir = os.path.join(home_path, "Results")
    os.makedirs(results_dir, exist_ok=True)
    
    # Dynamically determine charger wattage for this specific home
    home_charger_w = get_ev_charger_power(hpxml_file, DEFAULT_CHARGER_POWER_W)

    dwelling_args_local = {
        "start_time": Start,
        "time_res": dt.timedelta(minutes=t_res),
        "duration": dt.timedelta(days=Duration),
        "hpxml_file": hpxml_file,
        "hpxml_schedule_file": filtered_sched_file,
        "weather_file": weather_file_path,
        "verbosity": 7,
    }

   # Baseline (Default operation without forced signals)
    base_dwelling = Dwelling(name="EV Baseline", **dwelling_args_local)
    for t_base in base_dwelling.sim_times:
        base_dwelling.update() 
    df_base, _, _ = base_dwelling.finalize()

    # Controlled
    sim_dwelling = Dwelling(name="EV Controlled", **dwelling_args_local)
    for sim_time in sim_dwelling.sim_times:
        control_cmd = determine_EV_control(
            sim_time=sim_time, 
            sched_cfg=schedule_cfg,
            control_mode=CONTROL_MODE,
            charger_w=home_charger_w
        )
        if control_cmd:
            sim_dwelling.update(control_signal=control_cmd)
        else:
            sim_dwelling.update()
            
    df_ctrl, _, _ = sim_dwelling.finalize()

    df_ctrl = remove_first_day(df_ctrl, Start)
    df_base = remove_first_day(df_base, Start)
    
    # We define our target columns, but we also dynamically grab any EV related columns
    # so they aren't accidentally dropped if the name is slightly different in this OCHRE version.
    target_base_cols = [
        "Time", 
        "Total Electric Power (kW)",
        "Total Electric Energy (kWh)"
    ]
    
    # Dynamically find the EV power column. It might be named differently depending on OCHRE versions 
    # e.g., 'EV Electric Power (kW)', 'EV Power (kW)', 'EV Active Power (kW)'
    ev_cols_ctrl = [col for col in df_ctrl.columns if 'ev' in col.lower() and 'power' in col.lower()]
    ev_cols_base = [col for col in df_base.columns if 'ev' in col.lower() and 'power' in col.lower()]

    # df_ctrl.to_csv(os.path.join(results_dir, 'ev_baseline.csv'), index=False)
    
    CTRL_COLS = target_base_cols + ev_cols_ctrl
    BASE_COLS = target_base_cols + ev_cols_base
    
    # Keep only the columns that actually exist in the dataframe
    df_ctrl = df_ctrl[[c for c in CTRL_COLS if c in df_ctrl.columns]]
    df_base = df_base[[c for c in BASE_COLS if c in df_base.columns]]
        
    df_ctrl.to_csv(os.path.join(results_dir, 'ev_controlled.csv'), index=False)
    df_base.to_csv(os.path.join(results_dir, 'ev_baseline.csv'), index=False)

    return df_ctrl, df_base

#########################################
# FIND ALL HOMES
#########################################

def find_all_homes(base_dir):
    homes = []
    for item in os.listdir(base_dir):
        home_path = os.path.join(base_dir, item)
        if os.path.isdir(home_path):
            # Only add folders with required files
            if os.path.isfile(os.path.join(home_path, XML_ADDRESS)) and \
               os.path.isfile(os.path.join(home_path, CSV_ADDRESS)):
                homes.append(home_path)
    return homes

#########################################
# DELETE FIRST DAY ONLY
#########################################

def remove_first_day(df, start_date):
    """
    Remove the first day of simulation results.
    Works whether 'Time' is a column or the index.
    """
    # If 'Time' column doesn't exist, try using the index
    if 'Time' not in df.columns:
        df = df.reset_index()
        if 'index' in df.columns:
            df.rename(columns={'index': 'Time'}, inplace=True)

    # Ensure Time is datetime
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')

    # Remove first day
    first_day_end = start_date + pd.Timedelta(days=1)
    return df[df['Time'] >= first_day_end].copy()

#########################################
# MAIN EXECUTION
#########################################

if __name__ == "__main__":
    # Ensure working folders exist
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(WEATHER_DIR, exist_ok=True)
    try:
        weather_path = Path(WEATHER_DIR)
        weather_path.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Weather directory ready: {weather_path}")
    except Exception as e:
        print(f"[ERROR] Failed to create directory {weather_path}: {e}")

    for item in os.listdir(DEFAULT_INPUT):
        src = os.path.join(DEFAULT_INPUT, item)
        dst = os.path.join(INPUT_DIR, item)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
            
    if not os.path.exists(WEATHER_FILE):
        shutil.copy(DEFAULT_WEATHER, WEATHER_FILE)

    # Discover homes
    homes = find_all_homes(INPUT_DIR)
    print(f"homes: ", INPUT_DIR)
    print(f"Found {len(homes)} homes")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(simulate_home, home, WEATHER_FILE, my_schedule[sum(int(char) for char in home if char.isdigit()) % bins]) for home in homes]
        for f in concurrent.futures.as_completed(futures):
            try:
                f.result() 
            except Exception as e:
                print("Simulation failed:", e)

    print("All simulations complete!")

def aggregate_results(homes, work_dir):
    all_ctrl, all_base = [], []

    for home in homes:
        results_dir = os.path.join(home, "Results")
        ctrl_file = os.path.join(results_dir, "ev_controlled.csv")
        base_file = os.path.join(results_dir, "ev_baseline.csv")
        
        if os.path.exists(ctrl_file):
            df_ctrl = pd.read_csv(ctrl_file)
            df_ctrl["Home"] = os.path.basename(home)
            all_ctrl.append(df_ctrl)

        if os.path.exists(base_file):
            df_base = pd.read_csv(base_file)
            df_base["Home"] = os.path.basename(home)
            all_base.append(df_base)

    if all_ctrl:
        df_ctrl_all = pd.concat(all_ctrl, ignore_index=True)
        df_ctrl_all.to_csv(os.path.join(work_dir, filename + "_controlled.csv"), index=False)

    if all_base:
        df_base_all = pd.concat(all_base, ignore_index=True)
        df_base_all.to_csv(os.path.join(work_dir, filename + "_baseline.csv"), index=False)
    
    print(f"Aggregated CSVs written!")

if __name__ == "__main__":
    aggregate_results(homes, WORKING_DIR)