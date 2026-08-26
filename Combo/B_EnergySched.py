# -*- coding: utf-8 -*-
"""
Created on Wed Sep  3 17:39:26 2025
Modified on Nov 19 2025
Modified on Aug 25 2026


@author: danap
@edited by: jdinsmor
@edited by: t-metzler 
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

filename = ''

#"HPWH 50 Input Files", "HPWH 66 Input Files/bldg", "HPWH 80 Input Files", "HPWH All Input Files/bldg"
Input_folder = "HPWH All Input Files"

# Original OCHRE defaults folder
ochre_dir = Path(ochre.__file__).resolve().parent
DEFAULT_INPUT = ochre_dir / "defaults" / "Input Files"
print("OCHRE installed at:", ochre_dir)
print(DEFAULT_INPUT)

DEFAULT_WEATHER = ochre_dir / "defaults" / "Weather" / "USA_OR_Portland.Intl.AP.726980_TMY3.epw"
# G4100510 is Multnomah county weather station, code will complain this is missing but it doesn't work if you actually try to use it

# working folder (writable)
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

# HPWH control parameters (°F)
# GE - Grid Emergency, CP - Critical Peak, Shed
WH_Tcontrol_GEF = 90
WH_Tcontrol_GEdeadbandF = 10
WH_Tcontrol_CPF = 120
WH_Tcontrol_CPdeadbandF = 10
WH_Tcontrol_SHEDF = 126
WH_Tcontrol_deadbandF = 10
# ALU - Advanced load up, LOAD - Load up
WH_Tcontrol_ALUF = 140
WH_Tcontrol_ALUdeadbandF = 2
WH_Tcontrol_LOADF = 130
WH_Tcontrol_LOADdeadbandF = 2

WH_TbaselineF = 130
WH_TdeadbandF = 7
WH_Tinit = 128

count = 0

# Schedule variant
my_schedule1 = {
    'M_ALU_time': '06:30',
    'M_ALU_duration': 0,
    'M_LU_time': '06:30',
    'M_LU_duration': 0,
    'M_S_time': '07:30',
    'M_S_duration': 0,
    'M_CP_time': '7:30',
    'M_CP_duration': 0,
    'M_GE_time': '7:30',
    'M_GE_duration': 0,
    'E_ALU_time': '13:00',
    'E_ALU_duration': 1,
    'E_LU_time': '13:00',
    'E_LU_duration': 0,
    'E_S_time': '14:00',
    'E_S_duration': 6,
    'E_CP_time': '14:00',
    'E_CP_duration': 0,
    'E_GE_time': '14:00',
    'E_GE_duration': 0
}

ramp_duration = {
    "M_LU_in" : 2, 
    "M_LU_out" : 1,
    "M_S_in" : 1,
    "M_S_out" : 2,
    "E_LU_in" : 2,
    "E_LU_out" : 1,
    "E_S_in" : 1,
    "E_S_out" : 2
}

def shift_time(time_str, minutes):
    """Helper function to add minutes to an 'HH:MM' string."""
    # Using 'dt' to match your 'import datetime as dt' alias perfectly
    delta_t = dt.datetime.strptime(time_str, '%H:%M')
    new_delta_t = delta_t + dt.timedelta(minutes=minutes)
    return new_delta_t.strftime('%H:%M')

# List to hold all generated schedules
my_schedule = []

bins = 8

#minutes you will offset schedule
M_LU_in_dt = ramp_duration["M_LU_in"] / bins
M_LU_out_dt = ramp_duration["M_LU_out"] / bins
M_S_in_dt = ramp_duration["M_S_in"] / bins
M_S_out_dt = ramp_duration["M_S_out"] / bins
E_LU_in_dt = ramp_duration["E_LU_in"] / bins
E_LU_out_dt = ramp_duration["E_LU_out"] / bins
E_S_in_dt = ramp_duration["E_S_in"] / bins
E_S_out_dt = ramp_duration["E_S_out"] / bins

# generate 8 schedules, where the earliest schedule is 0*dt for each, and the latest is (bins-1)*dt. 
# This will change duration time if the in and out ramp durations are different, but if the duration is 0 it will stay 0. 
# If the load up goes directly into a shed, the load up out and shed in durations should be forced to be the same and working at the same time.



# Generate new schedules with offsets
for i in range(bins):
    M_LU_offset = i * M_LU_in_dt  # Calculates offset
    new_sched = my_schedule1.copy()
    
    for key, value in new_sched.items():
        # Check if the key is a time variable
        if key.endswith('LU_time') & key.startswith('M') :
            # Shift the start time
            new_sched[key] = shift_time(value, M_LU_offset)
            
    my_schedule.append(new_sched)

#########################################
# TEMPERATURE CONVERSIONS F to C
#########################################

def f_to_c(temp_f): 
    return (temp_f - 32) * 5/9

def f_to_c_DB(temp_f):
    return 5/9 * temp_f

WH_Tcontrol_GEC = f_to_c(WH_Tcontrol_GEF)
WH_Tcontrol_GEdeadbandC = f_to_c(WH_Tcontrol_GEdeadbandF)
WH_Tcontrol_CPC = f_to_c(WH_Tcontrol_CPF)
WH_Tcontrol_CPdeadbandC = f_to_c(WH_Tcontrol_CPdeadbandF)
WH_Tcontrol_SHEDC = f_to_c(WH_Tcontrol_SHEDF)
WH_Tcontrol_deadbandC = f_to_c_DB(WH_Tcontrol_deadbandF)

WH_Tcontrol_ALUC = f_to_c(WH_Tcontrol_ALUF)
WH_Tcontrol_ALUdeadbandC = f_to_c(WH_Tcontrol_ALUdeadbandF)
WH_Tcontrol_LOADC = f_to_c(WH_Tcontrol_LOADF)
WH_Tcontrol_LOADdeadbandC = f_to_c_DB(WH_Tcontrol_LOADdeadbandF)

WH_TbaselineC = f_to_c(WH_TbaselineF)
WH_TdeadbandC = f_to_c_DB(WH_TdeadbandF)
WH_TinitC = f_to_c(WH_Tinit)

#########################################
# HPWH CONTROL FUNCTION
#########################################

def determine_hpwh_control(sim_time, current_temp_c, sched_cfg, **kwargs):
    ctrl_signal = {
        'Water Heating': {
            'Setpoint': WH_TbaselineC,
            'Deadband': WH_TdeadbandC,
            'Load Fraction': 1,
        }
    }

    base_date = sim_time.date()
    def get_time_range(key_prefix):
        start = pd.to_datetime(f"{base_date} {sched_cfg[f'{key_prefix}_time']}")
        end = start + pd.Timedelta(hours=sched_cfg[f'{key_prefix}_duration'])
        return start, end

    ranges = {
        'M_ALU': get_time_range('M_ALU'),
        'M_LU': get_time_range('M_LU'),
        'M_S': get_time_range('M_S'),
        'M_CP': get_time_range('M_CP'),
        'M_GE': get_time_range('M_GE'),
        'E_ALU': get_time_range('E_ALU'),
        'E_LU': get_time_range('E_LU'),
        'E_S': get_time_range('E_S'),
        'E_CP': get_time_range('E_CP'),
        'E_GE': get_time_range('E_GE')
    }

    # ADVANCED LOAD UP
    if ranges['M_ALU'][0] <= sim_time < ranges['M_ALU'][1] or ranges['E_ALU'][0] <= sim_time < ranges['E_ALU'][1]:
        ctrl_signal['Water Heating'].update({
            'Setpoint': WH_Tcontrol_ALUC,
            'Deadband': WH_Tcontrol_ALUdeadbandC
        })

    # LOAD UP
    if ranges['M_LU'][0] <= sim_time < ranges['M_LU'][1] or ranges['E_LU'][0] <= sim_time < ranges['E_LU'][1]:
        ctrl_signal['Water Heating'].update({
            'Setpoint': WH_Tcontrol_LOADC,
            'Deadband': WH_Tcontrol_LOADdeadbandC
        })


    # SHED
    elif ranges['M_S'][0] <= sim_time < ranges['M_S'][1] or ranges['E_S'][0] <= sim_time < ranges['E_S'][1]:
        ctrl_signal['Water Heating'].update({
            'Setpoint': WH_Tcontrol_SHEDC,
            'Deadband': WH_Tcontrol_deadbandC
        })

    # CRITICAL PEAK
    elif ranges['M_CP'][0] <= sim_time < ranges['M_CP'][1] or ranges['E_CP'][0] <= sim_time < ranges['E_CP'][1]:
        ctrl_signal['Water Heating'].update({
            'Setpoint': WH_Tcontrol_CPC,
            'Deadband': WH_Tcontrol_CPdeadbandC
        })

    # GRID EMERGENCY
    elif ranges['M_GE'][0] <= sim_time < ranges['M_GE'][1] or ranges['E_GE'][0] <= sim_time < ranges['E_GE'][1]:
        ctrl_signal['Water Heating'].update({
            'Setpoint': WH_Tcontrol_GEC,
            'Deadband': WH_Tcontrol_GEdeadbandC
        })

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
        #"initialization_time": 1,
        "Equipment": {
            "Water Heating": {
                "Initial Temperature (C)": WH_TinitC, 
                "hp_only_mode": True,
                "Max Tank Temperature": 70,
                "Upper Node": 3,
                "Lower Node": 10,
                "Upper Node Weight": 0.75,
            },
        }
    }
    # quit()

    # Baseline
    base_dwelling = Dwelling(name="HPWH Baseline", **dwelling_args_local)
    for t_base in base_dwelling.sim_times:
        base_ctrl = {"Water Heating": {"Setpoint": WH_TbaselineC, "Deadband": WH_TdeadbandC, "Load Fraction": 1}}
        base_dwelling.update(control_signal=base_ctrl)
    df_base, _, _ = base_dwelling.finalize()

    # Controlled
    sim_dwelling = Dwelling(name="HPWH Controlled", **dwelling_args_local)
    hpwh_unit = sim_dwelling.get_equipment_by_end_use('Water Heating')
    for sim_time in sim_dwelling.sim_times:
        current_setpt = hpwh_unit.schedule.loc[sim_time, 'Water Heating Setpoint (C)']
        control_cmd = determine_hpwh_control(sim_time=sim_time, current_temp_c=current_setpt, sched_cfg=schedule_cfg)
        sim_dwelling.update(control_signal=control_cmd)
    df_ctrl, _, _ = sim_dwelling.finalize()


    df_ctrl = remove_first_day(df_ctrl, Start)
    df_base = remove_first_day(df_base, Start)
    

    CTRL_COLS = ["Time", "Total Electric Power (kW)",
                 "Total Electric Energy (kWh)",
                 "Water Heating Electric Power (kW)",
                 "Water Heating COP (-)",
                 "Water Heating Deadband Upper Limit (C)",
                 "Water Heating Deadband Lower Limit (C)",
                 "Water Heating Heat Pump COP (-)",
                 "Water Heating Control Temperature (C)",
                 "Hot Water Outlet Temperature (C)",
                 "Temperature - Indoor (C)"]
    BASE_COLS = CTRL_COLS
    

    df_ctrl = df_ctrl[[c for c in CTRL_COLS if c in df_ctrl.columns]]

    df_base = df_base[[c for c in BASE_COLS if c in df_base.columns]]
        
    
    df_ctrl.to_csv(os.path.join(results_dir, 'hpwh_controlled.csv'), index=False)
    df_base.to_csv(os.path.join(results_dir, 'hpwh_baseline.csv'), index=False)


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
    print(f"-++++++++++++ {homes}\n {base_dir}",)
    # print(len(homes))
    # x = list(set(homes))
    # print(len(x))
    # quit()
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
    count2 = 0

    # Copy all homes from defaults (if not already copied)
    for item in os.listdir(DEFAULT_INPUT):
        count2 +=1
        if count2 == 20:
            print(f"-----------", DEFAULT_INPUT, item, INPUT_DIR)
        src = os.path.join(DEFAULT_INPUT, item)
        dst = os.path.join(INPUT_DIR, item)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
            count +=1
        count +=1
    # Copy weather file
    if not os.path.exists(WEATHER_FILE):
        shutil.copy(DEFAULT_WEATHER, WEATHER_FILE)
        count +=1

    # Discover homes
    homes = find_all_homes(INPUT_DIR)
    print(f"homes: ", INPUT_DIR)
    print(f"Found {len(homes)} homes")

    # Parallel simulations (threads are Windows-safe)
    # my_schedule is crazy but I wanted to vary schedules within the for loop, so I summed the digits in the home name and mod by 2 to select one of two schedules
    # $ grep -rn "read_psm3(" .
    # ./ochre/utils/schedule.py:186:        df, location = pvlib.iotools.read_psm3(weather_file, map_variables=True)
    # Change to read_nsrdb_psm4 
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(simulate_home, home, WEATHER_FILE, my_schedule[sum(int(char) for char in home if char.isdigit()) % 4]) for home in homes]
        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()  # forces execution and raises exceptions if any
            except Exception as e:
                print("Simulation failed:", e)

    print("All simulations complete!")




# def aggregate_results(homes, work_dir, ctrl_cols=None, base_cols=None):
#     all_ctrl, all_base = [], []

#     for home in homes:
#         results_dir = os.path.join(home, "Results")
#         ctrl_file = os.path.join(results_dir, "hpwh_controlled.csv")
#         base_file = os.path.join(results_dir, "hpwh_baseline.csv")

#         if os.path.exists(ctrl_file):
#             df_ctrl = pd.read_csv(ctrl_file)
#             if ctrl_cols:  # filter only selected columns
#                 df_ctrl = df_ctrl[[c for c in ctrl_cols if c in df_ctrl.columns]]
#             df_ctrl["Home"] = os.path.basename(home)
#             all_ctrl.append(df_ctrl)

#         if os.path.exists(base_file):
#             df_base = pd.read_csv(base_file)
#             if base_cols:
#                 df_base = df_base[[c for c in base_cols if c in df_base.columns]]
#             df_base["Home"] = os.path.basename(home)
#             all_base.append(df_base)

#     if all_ctrl:
#         df_ctrl_all = pd.concat(all_ctrl, ignore_index=True)
#         df_ctrl_all.to_csv(os.path.join(work_dir, "hpwh_controlled_all.csv"), index=False)

#     if all_base:
#         df_base_all = pd.concat(all_base, ignore_index=True)
#         df_base_all.to_csv(os.path.join(work_dir, "hpwh_baseline_all.csv"), index=False)

#     print("Aggregated CSVs written!")

def aggregate_results(homes, work_dir):
    all_ctrl, all_base = [], []

    for home in homes:
        results_dir = os.path.join(home, "Results")
        ctrl_file = os.path.join(results_dir, "hpwh_controlled.csv")
        base_file = os.path.join(results_dir, "hpwh_baseline.csv")
        #print(f"Aggregated CSVs written to {results_dir}!")
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
    
    print(f"Aggregated CSVs written! {count}")




# CTRL_COLS = ["Time", "Total Electric Power (kW)",
#              "Total Electric Energy (kWh)",
#              "Water Heating Electric Power (kW)",
#              "Water Heating COP (-)",
#              "Water Heating Deadband Upper Limit (C)",
#              "Water Heating Deadband Lower Limit (C)",
#              "Water Heating Heat Pump COP (-)",
#              "Water Heating Control Temperature (C)",
#              "Hot Water Outlet Temperature (C)",
#              "Temperature - Indoor (C)"]
# BASE_COLS = CTRL_COLS

aggregate_results(homes, WORKING_DIR)

