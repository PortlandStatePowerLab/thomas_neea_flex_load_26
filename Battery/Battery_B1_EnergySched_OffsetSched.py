# -*- coding: utf-8 -*-
"""
Modified to simulate Residential Batteries with Load Up (charge) and Shed (discharge) schedules.

Created on Wed Sep  3 17:39:26 2025
Modified on Nov 19 2025
Modified on Aug 11 2026

@author: danap
@edited by: jdinsmor
@edited for batteries by: t-metzler
"""


import os
import shutil
import datetime as dt
import pandas as pd
from ochre import Dwelling
from ochre.utils.schedule import ALL_SCHEDULE_NAMES
import concurrent.futures
from pathlib import Path
import ochre

#########################################
# USER SETTINGS
#########################################

filename = 'Battery_Test_4'
Input_folder = "Almost All Portland Input Files"

# Original OCHRE defaults folder
ochre_dir = Path(ochre.__file__).resolve().parent
DEFAULT_INPUT = ochre_dir / "defaults" / "Input Files"
DEFAULT_WEATHER = ochre_dir / "defaults" / "Weather" / "USA_OR_Portland.Intl.AP.726980_TMY3.epw"

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
Start = dt.datetime(2018, 7, 11, 0, 0)
Duration = 2  # days
t_res = 15  # minutes

#########################################
# BATTERY SPECIFICATIONS
#########################################
BATTERY_PARAMS = {
    "capacity_kwh": 12,         # Usable energy capacity in kWh
    "capacity": 5.0,            # Max continuous power rating in kW
    "efficiency": 0.98,         # Discharging efficiency
    "efficiency_charge": 0.98,  # Charging efficiency
    "soc_init": 0.5,            # Start at 50% SOC
    "soc_min": 0.1,             # Minimum allowable SOC
    "soc_max": 1.0,             # Maximum allowable SOC
}

# Control commands in kW (+ is charging/Load Up, - is discharging/Shed)
P_LOAD_UP_KW = 0.5    # Charge battery at 3 kW
P_SHED_KW = -0.5      # Discharge battery at 3 kW to power the home
P_IDLE_KW = 0.0       # Idle

#########################################
# SCHEDULE GENERATION
#########################################
my_schedule1 = {
    'M_LU_time': '00:00',
    'M_LU_duration': 0,
    'M_S_time': '08:00',
    'M_S_duration': 0,
    'E_ALU_time': '00:00',
    'E_ALU_duration': 15,
    'E_S_time': '15:00',
    'E_S_duration': 6
}

def shift_time(time_str, minutes):
    """Helper function to add minutes to an 'HH:MM' string."""
    delta_t = dt.datetime.strptime(time_str, '%H:%M')
    new_delta_t = delta_t + dt.timedelta(minutes=minutes)
    return new_delta_t.strftime('%H:%M')

my_schedule = []
timestep = 15  # minutes to offset schedules
bins = 8

for i in range(bins):
    offset = i * timestep
    new_sched = my_schedule1.copy()
    for key, value in new_sched.items():
        if key.endswith('_time'):
            new_sched[key] = shift_time(value, offset)
    my_schedule.append(new_sched)

#########################################
# BATTERY CONTROL FUNCTION
#########################################

def determine_battery_control(sim_time, sched_cfg):
    """
    Returns battery control dictionary:
      - +kW -> Charge (Load Up)
      - -kW -> Discharge to supply dwelling loads (Shed)
      - 0.0 -> Idle
    """
    ctrl_signal = {
        'Battery': {
            'P Setpoint': P_IDLE_KW
        }
    }

    base_date = sim_time.date()
    
    def get_time_range(key_prefix):
        start = pd.to_datetime(f"{base_date} {sched_cfg[f'{key_prefix}_time']}")
        end = start + pd.Timedelta(hours=sched_cfg[f'{key_prefix}_duration'])
        return start, end

    ranges = {
        'M_LU': get_time_range('M_LU'),
        'M_S': get_time_range('M_S'),
        'E_ALU': get_time_range('E_ALU'),
        'E_S': get_time_range('E_S'),
    }

    # Check if we are in a Load Up (charging) window
    if ranges['M_LU'][0] <= sim_time < ranges['M_LU'][1] or ranges['E_ALU'][0] <= sim_time < ranges['E_ALU'][1]:
        ctrl_signal['Battery']['P Setpoint'] = P_LOAD_UP_KW
        
    # Check if we are in a Shed (discharging to home) window
    elif ranges['M_S'][0] <= sim_time < ranges['M_S'][1] or ranges['E_S'][0] <= sim_time < ranges['E_S'][1]:
        ctrl_signal['Battery']['P Setpoint'] = P_SHED_KW

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
    df_sched_filtered = df_sched[filtered_columns]
    df_sched_filtered.to_csv(filtered_sched_file, index=False)
    return filtered_sched_file

#########################################
# SIMULATION FUNCTION
#########################################

def simulate_home(home_path, weather_file_path, schedule_cfg):
    filtered_sched_file = filter_schedules(home_path)
    hpxml_file = os.path.join(home_path, XML_ADDRESS)
    results_dir = os.path.join(home_path, "Results")
    os.makedirs(results_dir, exist_ok=True)

    dwelling_args_local = {
        "start_time": Start,
        "time_res": dt.timedelta(minutes=t_res),
        "duration": dt.timedelta(days=Duration),
        "hpxml_file": hpxml_file,
        "hpxml_schedule_file": filtered_sched_file,
        "weather_file": weather_file_path,
        "verbosity": 7,
        "Equipment": {
            "Battery": BATTERY_PARAMS
        }
    }

    # Baseline Simulation (Battery exists but remains idle / 0 kW setpoint)
    base_dwelling = Dwelling(name="Battery Baseline", **dwelling_args_local)
    for _ in base_dwelling.sim_times:
        base_ctrl = {"Battery": {"P Setpoint": P_IDLE_KW}}
        base_dwelling.update(control_signal=base_ctrl)
    df_base, _, _ = base_dwelling.finalize()

    # Controlled Simulation (Battery executes Load Up and Shed commands)
    sim_dwelling = Dwelling(name="Battery Controlled", **dwelling_args_local)
    for sim_time in sim_dwelling.sim_times:
        control_cmd = determine_battery_control(sim_time=sim_time, sched_cfg=schedule_cfg)
        sim_dwelling.update(control_signal=control_cmd)
    df_ctrl, _, _ = sim_dwelling.finalize()

    # Remove warmup day
    df_ctrl = remove_first_day(df_ctrl, Start)
    df_base = remove_first_day(df_base, Start)

    # Keep relevant columns including battery power and state of charge
    CTRL_COLS = [
        "Time", 
        "Total Electric Power (kW)",
        "Total Electric Energy (kWh)",
        "Battery Electric Power (kW)",
        "Battery SOC (-)"
    ]

    df_ctrl = df_ctrl[[c for c in CTRL_COLS if c in df_ctrl.columns]]
    df_base = df_base[[c for c in CTRL_COLS if c in df_base.columns]]
        
    df_ctrl.to_csv(os.path.join(results_dir, 'battery_controlled.csv'), index=False)
    df_base.to_csv(os.path.join(results_dir, 'battery_baseline.csv'), index=False)

    return df_ctrl, df_base

#########################################
# FIND ALL HOMES & UTILITIES
#########################################

def find_all_homes(base_dir):
    homes = []
    for item in os.listdir(base_dir):
        home_path = os.path.join(base_dir, item)
        if os.path.isdir(home_path):
            if os.path.isfile(os.path.join(home_path, XML_ADDRESS)) and \
               os.path.isfile(os.path.join(home_path, CSV_ADDRESS)):
                homes.append(home_path)
    return homes

def remove_first_day(df, start_date):
    if 'Time' not in df.columns:
        df = df.reset_index()
        if 'index' in df.columns:
            df.rename(columns={'index': 'Time'}, inplace=True)

    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    first_day_end = start_date + pd.Timedelta(days=1)
    return df[df['Time'] >= first_day_end].copy()

def aggregate_results(homes, work_dir):
    all_ctrl, all_base = [], []

    for home in homes:
        results_dir = os.path.join(home, "Results")
        ctrl_file = os.path.join(results_dir, "battery_controlled.csv")
        base_file = os.path.join(results_dir, "battery_baseline.csv")
        
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
    
    print("Aggregated CSVs written successfully!")

#########################################
# MAIN EXECUTION
#########################################

if __name__ == "__main__":
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(WEATHER_DIR, exist_ok=True)

    # Copy homes from defaults
    for item in os.listdir(DEFAULT_INPUT):
        src = os.path.join(DEFAULT_INPUT, item)
        dst = os.path.join(INPUT_DIR, item)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)

    # Copy weather file
    if not os.path.exists(WEATHER_FILE):
        shutil.copy(DEFAULT_WEATHER, WEATHER_FILE)

    homes = find_all_homes(INPUT_DIR)
    print(f"Found {len(homes)} homes to simulate.")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(
                simulate_home, 
                home, 
                WEATHER_FILE, 
                my_schedule[sum(int(char) for char in home if char.isdigit()) % bins]
            ) for home in homes
        ]
        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print("Simulation failed:", e)

    print("All simulations complete!")
    aggregate_results(homes, WORKING_DIR)