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
import copy
import traceback
import re
import random
import numpy as np

#########################################
# USER SETTINGS & EV CONFIGURATION
#########################################

filename = 'EV_Test_34'
Input_folder = "EV All Portland Input Files"

# EV Control Settings
CONTROL_MODE = 'max_p'
DEFAULT_CHARGER_POWER_KW = 11.5 # Fallback 1.6 for Level 1, 5.6 for Level 2 (Dynamically checked per home below)
DEFAULT_CAPACITY_KWH = 60.0 # Fallback capacity if missing from HPXML

# Duty Cycle Multipliers (1.0 = 100% capacity)
LOAD_UP_PCT = 1.0   # Force charge at max capacity
SHED_PCT = 0.25     # Shed capacity (e.g., charge at only 25% max power)

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

# Schedule variant
my_schedule1 = {
    'M_LU_time': '07:00',
    'M_LU_duration': 0,
    'M_S_time': '08:00',
    'M_S_duration': 0,
    'E_ALU_time': '16:00',
    'E_ALU_duration': 0,
    'E_S_time': '15:00',
    'E_S_duration': 6,
}

def shift_time(time_str, minutes):
    """Helper function to add minutes to an 'HH:MM' string."""
    # Using 'dt' to match 'import datetime as dt' alias
    delta_t = dt.datetime.strptime(time_str, '%H:%M')
    new_delta_t = delta_t + dt.timedelta(minutes=minutes)
    return new_delta_t.strftime('%H:%M')

# List to hold all generated schedules
my_schedule = []

#minutes you will offset schedules
timestep = 15

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

def determine_EV_control(sim_time, sched_cfg, control_mode, charger_kw, ev_name):
    base_date = sim_time.date()
    # Inherit timezone from OCHRE's sim_time to prevent offset-naive comparison bugs
    tz = sim_time.tzinfo 
    
    def get_time_range(key_prefix):
        if f'{key_prefix}_time' not in sched_cfg:
            return None, None
        
        time_str = sched_cfg[f'{key_prefix}_time']
        hours = sched_cfg[f'{key_prefix}_duration']
        
        # Use native datetime instead of pd.to_datetime for safe comparison with sim_time
        hour, minute = map(int, time_str.split(':'))
        start = dt.datetime(base_date.year, base_date.month, base_date.day, hour, minute, tzinfo=tz)
        end = start + dt.timedelta(hours=hours)
        return start, end

    ranges = {
        'Load_Up_M': get_time_range('M_LU'),
        'Load_Up_E': get_time_range('E_ALU'),
        'Shed_M': get_time_range('M_S'),
        'Shed_E': get_time_range('E_S')
    }

    # Determine current operational state
    state = 'Normal'
    for state_name, (start, end) in ranges.items():
        if start and end and start <= sim_time < end:
            if 'Load_Up' in state_name:
                state = 'Load_Up'
            elif 'Shed' in state_name:
                state = 'Shed'
            break 
            
    if state == 'Normal':
        fraction = 1.0

    # Map state to percentage
    if state == 'Load_Up':
        fraction = LOAD_UP_PCT
    elif state == 'Shed':
        fraction = SHED_PCT

    # Format the control signal using the dynamically found ev_name
    ctrl_signal = {ev_name: {}}

        
    if control_mode == 'max_p':
        charge_limit = abs(fraction * charger_kw)
        
        if state == 'Load_Up':
            # Force charging by setting a specific setpoint
            ctrl_signal[ev_name]['Max Power'] = charger_kw
        elif state == 'Shed':
            # Cap the maximum charging speed (P Max bounds the load)
            ctrl_signal[ev_name]['Max Power'] = charge_limit
        elif state == 'Normal':
            ctrl_signal[ev_name]['Max Power'] = charger_kw
            
    return ctrl_signal

#########################################
# SCHEDULE FILTERING
#########################################

def filter_schedules(home_path):
    orig_sched_file = os.path.join(home_path, CSV_ADDRESS)
    filtered_sched_file = os.path.join(home_path, 'filtered_schedules.csv')

    df_sched = pd.read_csv(orig_sched_file)
    valid_schedule_names = set(ALL_SCHEDULE_NAMES.keys())
    
    # Catch any variation of EV / Vehicle schedules
    filtered_columns = [
        col for col in df_sched.columns 
        if col in valid_schedule_names 
        or 'ev' in col.lower() 
        or 'vehicle' in col.lower()
        or 'plug' in col.lower()
    ]
    
    dropped_columns = [col for col in df_sched.columns if col not in filtered_columns]
    if dropped_columns:
        print(f"Dropped invalid schedules for {home_path}: {dropped_columns}")

    df_sched_filtered = df_sched[filtered_columns]
    df_sched_filtered.to_csv(filtered_sched_file, index=False)
    return filtered_sched_file

#########################################
# CHARGER PARSER HELPER
#########################################

def get_ev_charger_power(hpxml_path, default_kw=20):
    """
    Parses the home's HPXML file to determine the power the EV charger draws
    """
    try:
        tree = ET.parse(hpxml_path)
        root = tree.getroot()
        
        # Remove namespaces for easier tag matching
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]
                
        for charger in root.findall('.//ElectricVehicleCharger'):
            charge_elem = charger.find('ChargingPower')
            
            if charge_elem is not None and charge_elem.text:
                return float(charge_elem.text) / 1000
                
    except Exception as e:
        print(f"[WARNING] Failed to parse EV charger level from {hpxml_path}. Using default {default_kw}. Error: {e}")
    
    return default_kw

#########################################
# CAPACITY PARSER HELPER
#########################################

def get_ev_capacity_or_range(hpxml_path, default_capacity_kwh=60.0):
    """
    Parses the home's HPXML file to determine the EV's usable or nominal battery capacity.
    Returns capacity in kWh.
    """
    try:
        tree = ET.parse(hpxml_path)
        root = tree.getroot()
        
        # Remove namespaces for easier tag matching
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]
                
        # Search for Battery element under ElectricVehicle/Vehicle
        for battery in root.findall('.//Battery'):
            # Prefer UsableCapacity, fallback to NominalCapacity
            usable = battery.find('UsableCapacity/Value')
            if usable is not None and usable.text:
                return float(usable.text)
                
            nominal = battery.find('NominalCapacity/Value')
            if nominal is not None and nominal.text:
                return float(nominal.text)
                
    except Exception as e:
        print(f"[WARNING] Failed to parse EV capacity from {hpxml_path}. Using default {default_capacity_kwh} kWh. Error: {e}")
        
    return default_capacity_kwh


#########################################
# SIMULATION FUNCTION
#########################################

def simulate_home(home_path, weather_file_path, schedule_cfg):
    filtered_sched_file = filter_schedules(home_path)
    hpxml_file = os.path.join(home_path, XML_ADDRESS)
    results_dir = os.path.join(home_path, "Results")
    os.makedirs(results_dir, exist_ok=True)
    
    # Dynamically determine charger wattage for this specific home
    home_charger_kw = get_ev_charger_power(hpxml_file, DEFAULT_CHARGER_POWER_KW)

    # Dynamically determine battery capacity for this vehicle
    home_ev_capacity = get_ev_capacity_or_range(hpxml_file, DEFAULT_CAPACITY_KWH)

    # Get the folder name (e.g., 'bldg0011875-up00')
    home_name = os.path.basename(home_path)
    
    # Remove all non-digit characters (leaves '001187500') and convert to integer
    home_seed = int(re.sub(r'\D', '', home_name))

    ev_names = ["EV"]

    if home_charger_kw > 8:
        home_charger = "Level 2"
    else:
        home_charger = "Level 1"

    
    dwelling_args_local = {
        "start_time": Start,
        "time_res": dt.timedelta(minutes=t_res),
        "duration": dt.timedelta(days=Duration),
        "hpxml_file": hpxml_file,
        "hpxml_schedule_file": filtered_sched_file,
        "weather_file": weather_file_path,
        "verbosity": 7,
        "seed": home_seed,
        "Equipment": {
            "EV": {
                "vehicle_type": "BEV",
                "capacity": home_ev_capacity,
                "charging_level": home_charger,
                "max_power": home_charger_kw
            }
        }
    }

    # Baseline Run
    random.seed(home_seed)
    np.random.seed(home_seed)
    base_dwelling = Dwelling(name="EV_Simulation", **copy.deepcopy(dwelling_args_local))
    for t_base in base_dwelling.sim_times:
        base_dwelling.update() 
    df_base, _, _ = base_dwelling.finalize()

    # Controlled Run
    random.seed(20)
    np.random.seed(20)
    sim_dwelling = Dwelling(name="EV_Simulation", **copy.deepcopy(dwelling_args_local))
    for sim_time in sim_dwelling.sim_times:
        
        control_cmd = {}
        # Only attempt EV control if we actually found an EV in this home
        if ev_names:
            primary_ev = ev_names[0] # Control the first EV found
            ev_ctrl = determine_EV_control(
                sim_time=sim_time, 
                sched_cfg=schedule_cfg,
                control_mode=CONTROL_MODE,
                charger_kw=home_charger_kw,
                ev_name=primary_ev
            )
            control_cmd.update(ev_ctrl)

        if control_cmd:
            sim_dwelling.update(control_signal=control_cmd)
        else:
            sim_dwelling.update()
            
    df_ctrl, _, _ = sim_dwelling.finalize()

    # ---------------------------------------------------------
    # 3. CLEANUP & EXPORT
    # ---------------------------------------------------------
    df_ctrl = remove_first_day(df_ctrl, Start)
    df_base = remove_first_day(df_base, Start)
    
    target_base_cols = ["Time", "Total Electric Power (kW)", "Total Electric Energy (kWh)"]
    
    # Catching the newly generated EV output columns
    ev_pwr_cols_ctrl = [c for c in df_ctrl.columns if ('ev' in c.lower() or 'vehicle' in c.lower()) and 'power' in c.lower()]
    ev_pwr_cols_base = [c for c in df_base.columns if ('ev' in c.lower() or 'vehicle' in c.lower()) and 'power' in c.lower()]
    ev_soc_cols_ctrl = [c for c in df_ctrl.columns if 'soc' in c.lower()]
    ev_soc_cols_base = [c for c in df_base.columns if 'soc' in c.lower()]
    
    CTRL_COLS = target_base_cols + ev_pwr_cols_ctrl + ev_soc_cols_ctrl
    BASE_COLS = target_base_cols + ev_pwr_cols_base + ev_soc_cols_base
    
    df_ctrl = df_ctrl[[c for c in CTRL_COLS if c in df_ctrl.columns]]
    df_base = df_base[[c for c in BASE_COLS if c in df_base.columns]]
        
    df_ctrl.to_csv(os.path.join(results_dir, 'home_controlled.csv'), index=False)
    df_base.to_csv(os.path.join(results_dir, 'home_baseline.csv'), index=False)

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

    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as executor:
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
        ctrl_file = os.path.join(results_dir, "home_controlled.csv")
        base_file = os.path.join(results_dir, "home_baseline.csv")
        
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