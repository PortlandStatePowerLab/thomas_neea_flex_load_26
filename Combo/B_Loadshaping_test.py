"""
Author: Thomas Metzler
Created: 9/10/26
Adjusts load up and shed commands to keep power consumption at a constant level.
"""

import os
import shutil
import datetime as dt
import pandas as pd
import ochre
from ochre import Dwelling, ScheduledLoad
from ochre.utils.schedule import ALL_SCHEDULE_NAMES
import ochre.utils.schedule as ochre_schedule
import concurrent.futures
from pathlib import Path
import random
import numpy as np
import traceback
import re
import xml.etree.ElementTree as ET

#########################################
# USER SETTINGS
#########################################

filename = 'Loadshape_Test_8'
Input_folder = "Combo HPWH HVAC Dryer EV All Input Files"

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
Start = dt.datetime(2018, 8, 11, 0, 0)
Duration = 2  # days
t_res = 5  # minutes


# --- GLOBAL VPP EVENT SETTINGS ---
# Define the time window for active load shaping
# (Replaced by dynamic hourly setpoints from CSV)
# VPP_START_TIME = dt.time(14, 0)
# VPP_END_TIME = dt.time(23, 0)

# Fleet-agnostic average power targets
# AVERAGE_SETPOINT_KW = 1.9     # Target average power PER HOME during VPP event (Now dynamic)
# AVERAGE_DEADBAND_KW = 0.01     # Tolerance PER HOME to prevent constant toggling (Loaded from CSV)
# ESTIMATED_LOAD_KW = 0.5       # Est. power ADDED when forcing a unit ON (LOAD) or lost when restored to NORMAL
# ESTIMATED_SHED_KW = 0.3       # Est. power DROPPED when allowing a unit to SHED or gained when restored to NORMAL

# --- DEADBAND RELEASE & COMMAND DURATION SETTINGS ---
DEADBAND_SETTLE_MINUTES = 30          # Minutes power must remain in deadband before releasing stuck devices
MIN_HOLD_FOR_RELEASE_MINUTES = 15     # Minimum minutes a device must be held before deadband release targets it
DEADBAND_RELEASE_SAFETY_FACTOR = 0.70 # Fraction of deadband half-width used as safe headroom during release
DEADBAND_RELEASE_STEP_FRACTION = 0.50  # Fraction of available safe headroom used per timestep for smooth release

# --- PID CONTROLLER GAINS ---
# Tune these parameters to adjust responsiveness and damp oscillations
# (Loaded from CSV)
# KP = 2.0                      # Proportional gain
# KI = 0.1                      # Integral gain
# KD = 0.1                      # Derivative gain

# WH control parameters (°F)
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
WH_Tinit = 130

# Response time in seconds
WH_RESPONSE_MIN = 30
WH_RESPONSE_MAX = 90


count = 0

# AC control parameters (°F)
# GE - Grid Emergency, CP - Critical Peak, Shed
AC_Tcontrol_GEF = 95
AC_Tcontrol_GEdeadbandF = 4
AC_Tcontrol_CPF = 80
AC_Tcontrol_CPdeadbandF = 4
AC_Tcontrol_SHEDF = 76
AC_Tcontrol_deadbandF = 4
# ALU - Advanced load up, LOAD - Load up
AC_Tcontrol_ALUF = 64
AC_Tcontrol_ALUdeadbandF = 2
AC_Tcontrol_LOADF = 68
AC_Tcontrol_LOADdeadbandF = 2

AC_TbaselineF = 72
AC_TdeadbandF = 2
AC_TinitF = 72

# Heating control parameters (°F)
# GE - Grid Emergency, CP - Critical Peak, Shed
HEAT_Tcontrol_GEF = 45
HEAT_Tcontrol_GEdeadbandF = 4
HEAT_Tcontrol_CPF = 60
HEAT_Tcontrol_CPdeadbandF = 4
HEAT_Tcontrol_SHEDF = 64
HEAT_Tcontrol_deadbandF = 4
# ALU - Advanced load up, LOAD - Load up
HEAT_Tcontrol_ALUF = 76
HEAT_Tcontrol_ALUdeadbandF = 2
HEAT_Tcontrol_LOADF = 72
HEAT_Tcontrol_LOADdeadbandF = 2

HEAT_TbaselineF = 68
HEAT_TdeadbandF = 2
HEAT_TinitF = 68

# Response time in seconds
HVAC_RESPONSE_MIN = 30
HVAC_RESPONSE_MAX = 90

# Dryer duty cycle parameters, dryers can't load up only curtail power
dryer_duty_cycle_shed = 0.5
dryer_duty_cycle_cp = 0.25
dryer_duty_cycle_ge = 0

# EV Control Settings
DEFAULT_CHARGER_POWER_KW = 11.5 # Fallback 1.6 for Level 1, 5.6 for Level 2 (Dynamically checked per home below)
DEFAULT_CAPACITY_KWH = 60.0 # Fallback capacity if missing from HPXML
EV_SHED_PCT = 0.5
EV_CP_PCT = 0.25
EV_GE_PCT = 0

# Battery Control Settings
BATTERY_PARAMS = {
    "capacity_kwh": 10,         # Usable energy capacity in kWh
    "capacity": 1.0,            # Max continuous power rating in kW
    "efficiency": 0.98,         # Discharging efficiency
    "efficiency_charge": 0.98,  # Charging efficiency
    "soc_init": 0.5,            # Start at 50% SOC
    "soc_min": 0.0,             # Minimum allowable SOC
    "soc_max": 1.0,             # Maximum allowable SOC
}

# Control commands in kW (+ is charging/Load Up, - is discharging/Shed)
P_Battery_ALU_KW = 1.0 * BATTERY_PARAMS['capacity']        # Charge battery ALU
P_Battery_LU_KW = 0.25 * BATTERY_PARAMS['capacity']        # Charge battery LU
P_Battery_SHED_KW = -0.25 * BATTERY_PARAMS['capacity']     # Discharge battery Shed
P_Battery_CP_KW = -0.5 * BATTERY_PARAMS['capacity']        # Discharge battery CP
P_Battery_GE_KW = -1.0 * BATTERY_PARAMS['capacity']        # Discharge battery GE
P_Battery_IDLE_KW = 0.0                                    # Idle


# ---------------------------------------------------------
# LOAD DEVICES FROM CSV
# ---------------------------------------------------------

devices_file = os.path.join(script_dir, "B0_Devices.csv")
try:
    df_devices = pd.read_csv(devices_file)
    # Convert to dictionary mapping 'Device' to 'Simulation'
    device_sim_map = dict(zip(df_devices['Device'], df_devices['Simulation']))
except FileNotFoundError:
    print(f"[WARNING] {devices_file} not found. Defaulting to OFF.")
    device_sim_map = {}

WH_SIMULATION = device_sim_map.get("WH", "OFF")
HVAC_SIMULATION = device_sim_map.get("HVAC", "OFF")
DRYER_SIMULATION = device_sim_map.get("Dryer", "OFF")
EV_SIMULATION = device_sim_map.get("EV", "OFF")
BATTERY_SIMULATION = device_sim_map.get("Battery", "OFF")

# ---------------------------------------------------------
# LOAD SHAPING CONTROLS FROM CSV
# ---------------------------------------------------------
controls_file = os.path.join(script_dir, "B0_Load_Shaping_Controls.csv")

# Defaults in case of failure or missing values
hourly_settings = {h: {"target": "OFF", "deadband": 0.1} for h in range(24)}
AVERAGE_DEADBAND_KW = 0.1
KP, KI, KD = 1.0, 1.0, 1.0
FAST_COMMAND_PRIORITY = ['DRYER', 'EV', 'BATTERY', 'HVAC', 'WH']
SLOW_COMMAND_PRIORITY = []
ALLOWED_COMMANDS = []

try:
    # # Read the first three columns, skipping the header
    df_ctrls = pd.read_csv(controls_file, usecols=[0, 1, 2], names=['Control', 'Value', 'Deadband'], skiprows=1)
    df_ctrls = df_ctrls.dropna(subset=['Control'])
    
    FAST_COMMAND_PRIORITY_TEMP = []
    SLOW_COMMAND_PRIORITY_TEMP = []
    ALLOWED_COMMANDS_TEMP = []
    
    for idx, row in df_ctrls.iterrows():
        cmd = str(row['Control']).strip()
        val = str(row['Value']).strip()
        db_val = row['Deadband']
        
        # Check if the command is a time string like "0:00"
        if ':' in cmd:
            hour = int(cmd.split(':')[0])
            # Parse the deadband float, fallback to 0.1 if missing/invalid
            try:
                db_float = float(db_val)
            except (ValueError, TypeError):
                db_float = 0.1
            hourly_settings[hour] = {"target": val, "deadband": db_float}
            
        elif cmd.lower() == 'deadband':
            # Keep global fallback just in case
            try:
                AVERAGE_DEADBAND_KW = float(val)
            except ValueError:
                pass
        elif cmd.startswith('Fast'):
            FAST_COMMAND_PRIORITY_TEMP.append(val)
        elif cmd.startswith('Slow'):
            SLOW_COMMAND_PRIORITY_TEMP.append(val)
        elif cmd in ['ALU', 'LU', 'SHED', 'CP', 'GE']:
            if val.upper() == 'ON':
                ALLOWED_COMMANDS_TEMP.append(cmd)
        elif cmd == 'KP':
            KP = float(val)
        elif cmd == 'KI':
            KI = float(val)
        elif cmd == 'KD':
            KD = float(val)
            
    if FAST_COMMAND_PRIORITY_TEMP:
        FAST_COMMAND_PRIORITY = [v.upper() for v in FAST_COMMAND_PRIORITY_TEMP]
    if SLOW_COMMAND_PRIORITY_TEMP:
        SLOW_COMMAND_PRIORITY = [v.upper() for v in SLOW_COMMAND_PRIORITY_TEMP]
    if ALLOWED_COMMANDS_TEMP:
        ALLOWED_COMMANDS = ALLOWED_COMMANDS_TEMP
        
except Exception as e:
    print(f"[WARNING] Could not load fully from {controls_file}. Using defaults where missing. Error: {e}")


#########################################
# POWER ADJUSTMENT ESTIMATIONS
#########################################

WH_CAP_KW = 0.5
HVAC_CAP_KW = 12
DRYER_CAP_KW = 15
EV_CAP_KW = 9.5
BATT_CAP_KW = 1

WH_ALU_FRAC = 1.1
WH_END_ALU_FRAC = 0.01
WH_LU_FRAC = 0.4
WH_END_LU_FRAC = 0.05
WH_NORM_FRAC = 0.2
WH_SHED_FRAC = 0.05
WH_END_SHED_FRAC = 0.4
WH_CP_FRAC = 0.01
WH_END_CP_FRAC = 0.8
WH_GE_FRAC = 0
WH_END_GE_FRAC = 1.1

HVAC_ALU_FRAC = 0.75
HVAC_END_ALU_FRAC = 0.001
HVAC_LU_FRAC = 0.5
HVAC_END_LU_FRAC = 0.01
HVAC_NORM_FRAC = 0.1
HVAC_SHED_FRAC = 0.01
HVAC_END_SHED_FRAC = 0.5
HVAC_CP_FRAC = 0.001
HVAC_END_CP_FRAC = 0.4
HVAC_GE_FRAC = 0
HVAC_END_GE_FRAC = 0.75

DRYER_NORM_FRAC = 0.3
DRYER_SHED_FRAC = 0.15
DRYER_END_SHED_FRAC = 0.3
DRYER_CP_FRAC = 0.07
DRYER_END_CP_FRAC = 0.3
DRYER_GE_FRAC = 0
DRYER_END_GE_FRAC = 0.3

EV_NORM_FRAC = 1.0
EV_SHED_FRAC = 0.5
EV_END_SHED_FRAC = 1.0
EV_CP_FRAC = 0.25
EV_END_CP_FRAC = 1.0
EV_GE_FRAC = 0
EV_END_GE_FRAC = 1.0

BATT_ALU_FRAC = 1.0
BATT_LU_FRAC = 0.25
BATT_NORM_FRAC = 0
BATT_SHED_FRAC = -0.25
BATT_CP_FRAC = -0.5
BATT_GE_FRAC = -1

# --- MULTI-DEVICE FRACTION MAPPING FOR DYNAMIC DISPATCH ---
# This bridges your original variables to the generic priority queue
FRAC_MAP = {
    'WH': {'CAP': WH_CAP_KW, 'NORMAL': WH_NORM_FRAC, 'LU': WH_LU_FRAC, 'END_LU': WH_END_LU_FRAC, 'ALU': WH_ALU_FRAC, 'END_ALU': WH_END_ALU_FRAC, 'SHED': WH_SHED_FRAC, 'END_SHED': WH_END_SHED_FRAC, 'CP': WH_CP_FRAC, 'END_CP': WH_END_CP_FRAC, 'GE': WH_GE_FRAC, 'END_GE': WH_END_GE_FRAC},
    'HVAC': {'CAP': HVAC_CAP_KW, 'NORMAL': HVAC_NORM_FRAC, 'LU': HVAC_LU_FRAC, 'END_LU': HVAC_END_LU_FRAC, 'ALU': HVAC_ALU_FRAC, 'END_ALU': HVAC_END_ALU_FRAC, 'SHED': HVAC_SHED_FRAC, 'END_SHED': HVAC_END_SHED_FRAC, 'CP': HVAC_CP_FRAC, 'END_CP': HVAC_END_CP_FRAC, 'GE': HVAC_GE_FRAC, 'END_GE': HVAC_END_GE_FRAC},
    'DRYER': {'CAP': DRYER_CAP_KW, 'NORMAL': DRYER_NORM_FRAC, 'LU': 0.0, 'END_LU': 0.0, 'ALU': 0.0, 'END_ALU': 0.0, 'SHED': DRYER_SHED_FRAC, 'END_SHED': DRYER_END_SHED_FRAC, 'CP': DRYER_CP_FRAC, 'END_CP': DRYER_END_CP_FRAC, 'GE': DRYER_GE_FRAC, 'END_GE': DRYER_END_GE_FRAC},
    'EV': {'CAP': EV_CAP_KW, 'NORMAL': EV_NORM_FRAC, 'LU': 0.0, 'END_LU': 0.0, 'ALU': 0.0, 'END_ALU': 0.0, 'SHED': EV_SHED_FRAC, 'END_SHED': EV_END_SHED_FRAC, 'CP': EV_CP_FRAC, 'END_CP': EV_END_CP_FRAC, 'GE': EV_GE_FRAC, 'END_GE': EV_END_GE_FRAC},
    'BATTERY': {'CAP': BATT_CAP_KW, 'NORMAL': BATT_NORM_FRAC, 'LU': BATT_LU_FRAC, 'END_LU': 0.0, 'ALU': BATT_ALU_FRAC, 'END_ALU': 0.0, 'SHED': BATT_SHED_FRAC, 'END_SHED': 0.0, 'CP': BATT_CP_FRAC, 'END_CP': 0.0, 'GE': BATT_GE_FRAC, 'END_GE': 0.0}
}

#########################################
# TEMPERATURE CONVERSIONS F to C
#########################################

def f_to_c(temp_f): 
    return (temp_f - 32) * 5/9

def f_to_c_DB(temp_f):
    return 5/9 * temp_f

WH_Tcontrol_GEC = f_to_c(WH_Tcontrol_GEF)
WH_Tcontrol_GEdeadbandC = f_to_c_DB(WH_Tcontrol_GEdeadbandF)
WH_Tcontrol_CPC = f_to_c(WH_Tcontrol_CPF)
WH_Tcontrol_CPdeadbandC = f_to_c_DB(WH_Tcontrol_CPdeadbandF)
WH_Tcontrol_SHEDC = f_to_c(WH_Tcontrol_SHEDF)
WH_Tcontrol_deadbandC = f_to_c_DB(WH_Tcontrol_deadbandF)

WH_Tcontrol_ALUC = f_to_c(WH_Tcontrol_ALUF)
WH_Tcontrol_ALUdeadbandC = f_to_c_DB(WH_Tcontrol_ALUdeadbandF)
WH_Tcontrol_LOADC = f_to_c(WH_Tcontrol_LOADF)
WH_Tcontrol_LOADdeadbandC = f_to_c_DB(WH_Tcontrol_LOADdeadbandF)

WH_TbaselineC = f_to_c(WH_TbaselineF)
WH_TdeadbandC = f_to_c_DB(WH_TdeadbandF)
WH_TinitC = f_to_c(WH_Tinit)


AC_Tcontrol_GEC = f_to_c(AC_Tcontrol_GEF)
AC_Tcontrol_GEdeadbandC = f_to_c_DB(AC_Tcontrol_GEdeadbandF)
AC_Tcontrol_CPC = f_to_c(AC_Tcontrol_CPF)
AC_Tcontrol_CPdeadbandC = f_to_c_DB(AC_Tcontrol_CPdeadbandF)
AC_Tcontrol_SHEDC = f_to_c(AC_Tcontrol_SHEDF)
AC_Tcontrol_deadbandC = f_to_c_DB(AC_Tcontrol_deadbandF)

AC_Tcontrol_ALUC = f_to_c(AC_Tcontrol_ALUF)
AC_Tcontrol_ALUdeadbandC = f_to_c_DB(AC_Tcontrol_ALUdeadbandF)
AC_Tcontrol_LOADC = f_to_c(AC_Tcontrol_LOADF)
AC_Tcontrol_LOADdeadbandC = f_to_c_DB(AC_Tcontrol_LOADdeadbandF)

AC_TbaselineC = f_to_c(AC_TbaselineF)
AC_TdeadbandC = f_to_c_DB(AC_TdeadbandF)
AC_TinitC = f_to_c(AC_TinitF)


HEAT_Tcontrol_GEC = f_to_c(HEAT_Tcontrol_GEF)
HEAT_Tcontrol_GEdeadbandC = f_to_c_DB(HEAT_Tcontrol_GEdeadbandF)
HEAT_Tcontrol_CPC = f_to_c(HEAT_Tcontrol_CPF)
HEAT_Tcontrol_CPdeadbandC = f_to_c_DB(HEAT_Tcontrol_CPdeadbandF)
HEAT_Tcontrol_SHEDC = f_to_c(HEAT_Tcontrol_SHEDF)
HEAT_Tcontrol_deadbandC = f_to_c_DB(HEAT_Tcontrol_deadbandF)

HEAT_Tcontrol_ALUC = f_to_c(HEAT_Tcontrol_ALUF)
HEAT_Tcontrol_ALUdeadbandC = f_to_c_DB(HEAT_Tcontrol_ALUdeadbandF)
HEAT_Tcontrol_LOADC = f_to_c(HEAT_Tcontrol_LOADF)
HEAT_Tcontrol_LOADdeadbandC = f_to_c_DB(HEAT_Tcontrol_LOADdeadbandF)

HEAT_TbaselineC = f_to_c(HEAT_TbaselineF)
HEAT_TdeadbandC = f_to_c_DB(HEAT_TdeadbandF)
HEAT_TinitC = f_to_c(HEAT_TinitF)

#########################################
# HELPER FUNCTIONS
#########################################

# Map 'electric_vehicle_charging' to OCHRE's internal schedule tuple (Category, Name)
ochre_schedule.ALL_SCHEDULE_NAMES['electric_vehicle_charging'] = ('EV', 'electric_vehicle')

def get_15min_schedule_idx(sim_time, start_of_year, num_rows):
    """
    Maps any sub-15-minute timestamp to its exact 15-minute schedule row index
    using integer floor division to avoid floating-point boundary drift.
    """
    elapsed_sec = int((sim_time - start_of_year).total_seconds())
    idx = (elapsed_sec // (15 * 60)) % num_rows
    return idx

def filter_schedules(home_path):
    orig_sched_file = os.path.join(home_path, CSV_ADDRESS)
    filtered_sched_file = os.path.join(home_path, 'filtered_schedules.csv')

    df_sched = pd.read_csv(orig_sched_file)
    valid_schedule_names = set(ALL_SCHEDULE_NAMES.keys())
    filtered_columns = [col for col in df_sched.columns if col in valid_schedule_names]

    df_sched[filtered_columns].to_csv(filtered_sched_file, index=False)
    return filtered_sched_file

def find_all_homes(base_dir):
    images = []
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


def update_device_command(device_state, new_target, sim_time):
    """
    Updates reactive device target state and applies a random response delay.
    """
    # If a new command target is received, sample a delay and schedule execution
    if new_target != device_state["target_cmd"]:
        device_state["target_cmd"] = new_target
        delay_sec = random.uniform(device_state["min_delay"], device_state["max_delay"])
        device_state["effective_time"] = sim_time + pd.Timedelta(seconds=delay_sec)
    
    # Transition active state once effective time is reached
    if sim_time >= device_state["effective_time"]:
        device_state["active_cmd"] = device_state["target_cmd"]
        
    return device_state["active_cmd"]


def set_device_target_cmd(device_state, new_cmd, sim_time):
    """
    Sets a device's target command while tracking continuous hold duration.
    For DRYER, also flags pending_off=True on any mode transition so OCHRE
    sees a clean 1-timestep zero gap when splitting or resuming cycles.
    """
    prev_cmd = device_state.get("target_cmd", "NORMAL")
    if new_cmd != prev_cmd and "pending_off" in device_state:
        device_state["pending_off"] = True

    if new_cmd == "NORMAL":
        device_state["target_cmd"] = "NORMAL"
        device_state["cmd_start_time"] = None
    else:
        if device_state.get("cmd_start_time") is None:
            device_state["cmd_start_time"] = sim_time
        device_state["target_cmd"] = new_cmd


def get_device_hold_minutes(device_state, sim_time):
    """
    Returns how many consecutive minutes a device has been under a non-NORMAL command.
    """
    start_t = device_state.get("cmd_start_time")
    if start_t is None or device_state.get("target_cmd", "NORMAL") == "NORMAL":
        return 0.0
    return max(0.0, (sim_time - start_t).total_seconds() / 60.0)


def update_dryer_live_schedule(home_data, sim_time):
    """
    Option B live dryer controller:
    1. Accumulates scheduled 5-minute dryer power into work_queue.
    2. Enforces a 1-timestep zero gap (pending_off) on mode changes.
    3. Dispenses energy according to the active duty cycle (NORMAL, SHED, CP, GE).
    4. Mutates dryer_eq.schedule in memory at sim_time before sim_dw.update(),
       eliminating the 15-minute CSV 3-to-1 overwrite issue.
    """
    dryer_state = home_data["device_states"]["DRYER"]
    dryer_eq = dryer_state.get("equipment")
    sched_col = dryer_state.get("sched_col")

    if dryer_eq is None or sched_col is None or sim_time not in dryer_eq.schedule.index:
        return 0.0

    # Add the unmodified 5-minute scheduled power draw to the energy queue
    scheduled_kw = float(dryer_state["orig_schedule"].loc[sim_time])
    if scheduled_kw > 0:
        dryer_state["work_queue"] += scheduled_kw

    # Clean up floating point precision remnants
    if dryer_state["work_queue"] < 1e-6:
        dryer_state["work_queue"] = 0.0

    active_mode = dryer_state["active_cmd"]
    rated_kw = dryer_state["rated_kw"]

    if dryer_state["pending_off"]:
        # Force a 0 for one 5-minute timestep when entering or exiting a shed state
        dispense_kw = 0.0
        dryer_state["pending_off"] = False
    elif dryer_state["work_queue"] > 1e-6:
        if active_mode == "SHED":
            dc = dryer_duty_cycle_shed
        elif active_mode == "CP":
            dc = dryer_duty_cycle_cp
        elif active_mode == "GE":
            dc = dryer_duty_cycle_ge
        else:
            dc = 1.0

        allowed_kw = rated_kw * dc
        dispense_kw = min(dryer_state["work_queue"], allowed_kw)
        dryer_state["work_queue"] = max(0.0, dryer_state["work_queue"] - dispense_kw)
    else:
        dispense_kw = 0.0
        dryer_state["work_queue"] = 0.0

    # Mutate OCHRE's in-memory 5-minute schedule directly for this timestep
    dryer_eq.schedule.loc[sim_time, sched_col] = dispense_kw
    return dispense_kw


def estimate_transition_delta_kw(home_data, dev, current_cmd, next_cmd, cap_kw):
    """
    Estimates fleet power change (+kW adds load, -kW drops load) when transitioning
    a device from current_cmd to next_cmd.
    """
    cur = "LU" if current_cmd == "LOAD" else current_cmd
    nxt = "LU" if next_cmd == "LOAD" else next_cmd
    if cur == nxt:
        return 0.0

    if nxt == "NORMAL":
        if cur in ["ALU", "LU"]:
            frac_diff = FRAC_MAP[dev][f"END_{cur}"] - FRAC_MAP[dev][cur]
        elif cur in ["SHED", "CP", "GE"]:
            frac_diff = FRAC_MAP[dev][f"END_{cur}"] - FRAC_MAP[dev][cur]
        else:
            frac_diff = 0.0
    else:
        frac_diff = FRAC_MAP[dev][nxt] - FRAC_MAP[dev][cur]

    return frac_diff * cap_kw


def release_stuck_devices_in_deadband(
    fleet_data,
    sim_time,
    average_power_kw,
    setpoint_kw,
    deadband_kw,
    num_homes,
    enabled_simulations,
    get_device_cap_kw_fn,
    is_ev_charging_fn,
    is_dryer_active_fn,
):
    """
    Gradually releases devices held in active commands back toward NORMAL once
    fleet power has remained within the deadband for at least DEADBAND_SETTLE_MINUTES,
    while keeping predicted average power safely inside the deadband.
    """
    released_count = 0
    predicted_avg_kw = average_power_kw

    # Step-down mapping so severe commands unwind smoothly without large power spikes
    step_release_map = {
        "GE": "CP",
        "CP": "SHED",
        "SHED": "NORMAL",
        "ALU": "LU",
        "LU": "NORMAL",
        "LOAD": "NORMAL",
    }

    controllable_devs = [
        d for d in ["WH", "HVAC", "DRYER", "EV", "BATTERY"]
        if enabled_simulations.get(d) == "ON"
    ]

    # Collect candidates currently held beyond MIN_HOLD_FOR_RELEASE_MINUTES
    shed_candidates = []
    load_candidates = []

    for h in fleet_data:
        for dev in controllable_devs:
            dev_state = h["device_states"][dev]
            cur_cmd = dev_state["target_cmd"]
            if cur_cmd == "NORMAL":
                continue
            if dev == "EV" and not is_ev_charging_fn(h):
                continue

            hold_min = get_device_hold_minutes(dev_state, sim_time)
            if hold_min < MIN_HOLD_FOR_RELEASE_MINUTES:
                continue

            next_cmd = step_release_map.get(cur_cmd, "NORMAL")
            cap_kw = get_device_cap_kw_fn(h, dev)
            # Idle dryers (empty work_queue) draw 0 kW when restored, so they cost 0 headroom
            if dev == "DRYER" and not is_dryer_active_fn(h):
                delta_kw = 0.0
            else:
                delta_kw = estimate_transition_delta_kw(h, dev, cur_cmd, next_cmd, cap_kw)

            entry = {
                "home": h,
                "dev": dev,
                "cur_cmd": cur_cmd,
                "next_cmd": next_cmd,
                "hold_min": hold_min,
                "delta_kw": delta_kw,
                "tie": random.random(),
            }
            if cur_cmd in ["GE", "CP", "SHED"] and delta_kw >= 0:
                shed_candidates.append(entry)
            elif cur_cmd in ["ALU", "LU", "LOAD"] and delta_kw < 0:
                load_candidates.append(entry)

    # Prioritize devices held for the longest continuous duration
    shed_candidates.sort(key=lambda x: (-x["hold_min"], x["tie"]))
    load_candidates.sort(key=lambda x: (-x["hold_min"], x["tie"]))

    safe_db = DEADBAND_RELEASE_SAFETY_FACTOR * deadband_kw

    # Stage 1: Cancel opposing Load-Up and Shed commands simultaneously (~0 net kW shift)
    used_homes_devs = set()
    s_idx, l_idx = 0, 0
    while s_idx < len(shed_candidates) and l_idx < len(load_candidates):
        s_item = shed_candidates[s_idx]
        l_item = load_candidates[l_idx]

        net_delta_kw = s_item["delta_kw"] + l_item["delta_kw"]
        cand_avg_kw = predicted_avg_kw + (net_delta_kw / num_homes)

        if abs(setpoint_kw - cand_avg_kw) <= safe_db:
            set_device_target_cmd(s_item["home"]["device_states"][s_item["dev"]], s_item["next_cmd"], sim_time)
            set_device_target_cmd(l_item["home"]["device_states"][l_item["dev"]], l_item["next_cmd"], sim_time)
            used_homes_devs.add((id(s_item["home"]), s_item["dev"]))
            used_homes_devs.add((id(l_item["home"]), l_item["dev"]))
            predicted_avg_kw = cand_avg_kw
            released_count += 2
            s_idx += 1
            l_idx += 1
        else:
            # Advance whichever side has the larger magnitude delta to find a closer match
            if abs(s_item["delta_kw"]) >= abs(l_item["delta_kw"]):
                s_idx += 1
            else:
                l_idx += 1

    # Stage 2: Single-sided release bounded by remaining safe deadband headroom
    predicted_raw_error = setpoint_kw - predicted_avg_kw

    # Release stuck SHED/CP/GE devices if there is safe upward headroom below setpoint + safe_db
    add_budget_kw = max(0.0, (predicted_raw_error + safe_db)) * num_homes * DEADBAND_RELEASE_STEP_FRACTION
    for item in shed_candidates:
        if (id(item["home"]), item["dev"]) in used_homes_devs:
            continue
        if item["delta_kw"] <= add_budget_kw:
            set_device_target_cmd(item["home"]["device_states"][item["dev"]], item["next_cmd"], sim_time)
            add_budget_kw -= item["delta_kw"]
            predicted_avg_kw += item["delta_kw"] / num_homes
            released_count += 1

    # Release stuck ALU/LU/LOAD devices if there is safe downward headroom above setpoint - safe_db
    predicted_raw_error = setpoint_kw - predicted_avg_kw
    drop_budget_kw = max(0.0, (-predicted_raw_error + safe_db)) * num_homes * DEADBAND_RELEASE_STEP_FRACTION
    for item in load_candidates:
        if drop_budget_kw <= 0:
            break
        if (id(item["home"]), item["dev"]) in used_homes_devs:
            continue
        drop_kw = abs(item["delta_kw"])
        if 0 < drop_kw <= drop_budget_kw:
            set_device_target_cmd(item["home"]["device_states"][item["dev"]], item["next_cmd"], sim_time)
            drop_budget_kw -= drop_kw
            predicted_avg_kw -= drop_kw / num_homes
            released_count += 1

    return released_count

def get_interpolated_vpp_settings(sim_time, hourly_settings):
    """
    Computes linearly interpolated target power setpoint and deadband for any minute/second
    within the timestep between the current hour and the next hour node.
    """
    hour = sim_time.hour
    next_hour = (hour + 1) % 24
    
    # Calculate fractional hour progress (0.0 to 1.0)
    frac = (sim_time.minute * 60 + sim_time.second) / 3600.0

    curr_data = hourly_settings.get(hour, {"target": "OFF", "deadband": 0.1})
    next_data = hourly_settings.get(next_hour, {"target": "OFF", "deadband": 0.1})

    curr_target_raw = str(curr_data["target"]).strip().upper()
    next_target_raw = str(next_data["target"]).strip().upper()

    # Determine activity states
    curr_is_active = curr_target_raw != "OFF"
    next_is_active = next_target_raw != "OFF"

    if not curr_is_active and not next_is_active:
        return False, 0.0, 0.1

    curr_sp = float(curr_target_raw) if curr_is_active else None
    next_sp = float(next_target_raw) if next_is_active else None
    curr_db = float(curr_data.get("deadband", 0.1))
    next_db = float(next_data.get("deadband", 0.1))

    # Interpolation across transition states
    if curr_is_active and next_is_active:
        sp = curr_sp + (next_sp - curr_sp) * frac
        db = curr_db + (next_db - curr_db) * frac
        is_active = True
    elif curr_is_active and not next_is_active:
        # Smoothly ramp down towards 0 at the end of the event window
        sp = curr_sp * (1.0 - frac)
        db = curr_db
        is_active = True
    else:
        # Smoothly ramp up from 0 at the start of the event window
        sp = next_sp * frac
        db = next_db
        is_active = True

    return is_active, sp, db

def _build_ev_equipment(hpxml_file):
    charger_kw = get_ev_charger_power(hpxml_file, DEFAULT_CHARGER_POWER_KW)
    capacity_kwh = get_ev_capacity_or_range(hpxml_file, DEFAULT_CAPACITY_KWH)
    return charger_kw, {
        "vehicle_type": "BEV",
        "capacity": capacity_kwh,
        "charging_level": "Level 2" if charger_kw > 8 else "Level 1",
        "max_power": charger_kw,
    }

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

def is_ev_charging(home_data):
    ev_eq = home_data["sim"].get_equipment_by_end_use("EV")
    return (
        ev_eq is not None
        and getattr(ev_eq, "in_event", False)
        and getattr(ev_eq, "electric_kw", 0.0) > 0.05
    )

#########################################
# CONTROL & INITIALIZATION
#########################################

def get_wh_setpoint(mode_name):
    mode = mode_name.upper()
    if mode in ["LOAD", "LU"]:
        return WH_Tcontrol_LOADC, WH_Tcontrol_LOADdeadbandC
    elif mode == "ALU":
        return WH_Tcontrol_ALUC, WH_Tcontrol_ALUdeadbandC
    elif mode in ["SHED", "S"]:
        return WH_Tcontrol_SHEDC, WH_Tcontrol_deadbandC
    elif mode == "CP":
        return WH_Tcontrol_CPC, WH_Tcontrol_CPdeadbandC
    elif mode == "GE":
        return WH_Tcontrol_GEC, WH_Tcontrol_GEdeadbandC
    else:  # "NORMAL"
        return WH_TbaselineC, WH_TdeadbandC

def get_hvac_setpoints(mode_name, is_cooling_season):
    mode = mode_name.upper()
    if mode in ["LOAD", "LU"]:
        ac_sp, ac_db = AC_Tcontrol_LOADC, AC_Tcontrol_LOADdeadbandC
        heat_sp, heat_db = HEAT_Tcontrol_LOADC, HEAT_Tcontrol_LOADdeadbandC
    elif mode == "ALU":
        ac_sp, ac_db = AC_Tcontrol_ALUC, AC_Tcontrol_ALUdeadbandC
        heat_sp, heat_db = HEAT_Tcontrol_ALUC, HEAT_Tcontrol_ALUdeadbandC
    elif mode in ["SHED", "S"]:
        ac_sp, ac_db = AC_Tcontrol_SHEDC, AC_Tcontrol_deadbandC
        heat_sp, heat_db = HEAT_Tcontrol_SHEDC, HEAT_Tcontrol_deadbandC
    elif mode == "CP":
        ac_sp, ac_db = AC_Tcontrol_CPC, AC_Tcontrol_CPdeadbandC
        heat_sp, heat_db = HEAT_Tcontrol_CPC, HEAT_Tcontrol_CPdeadbandC
    elif mode == "GE":
        ac_sp, ac_db = AC_Tcontrol_GEC, AC_Tcontrol_GEdeadbandC
        heat_sp, heat_db = HEAT_Tcontrol_GEC, HEAT_Tcontrol_GEdeadbandC
    else:  # "NORMAL"
        ac_sp, ac_db = AC_TbaselineC, AC_TdeadbandC
        heat_sp, heat_db = HEAT_TbaselineC, HEAT_TdeadbandC

    if is_cooling_season:
        return (ac_sp, ac_db), (HEAT_Tcontrol_GEC, HEAT_TdeadbandC)
    else:
        return (AC_Tcontrol_GEC, AC_TdeadbandC), (heat_sp, heat_db)


def determine_control(sim_time, active_commands, home_charger_kw=None):
    # Initialize control signal dictionary
    ctrl_signal = {}

    # Water Heating control
    if WH_SIMULATION == "ON":
        wh_sp, wh_db = get_wh_setpoint(active_commands.get("WH", "NORMAL"))
        ctrl_signal['Water Heating'] = {
            'Setpoint': wh_sp,
            'Deadband': wh_db,
            'Load Fraction': 1
        }

    # HVAC control
    if HVAC_SIMULATION == "ON":
        # Add HVAC if simulated, checking the month to separate Heating vs Cooling
        # Let's assume May (5) through Sept (9) is Cooling Season in Portland
        hvac_mode = active_commands.get("HVAC", "NORMAL")
        is_cooling_season = sim_time.month in [5, 6, 7, 8, 9]
        cool_cfg, heat_cfg = get_hvac_setpoints(hvac_mode, is_cooling_season)
        ctrl_signal['HVAC Cooling'] = {'Setpoint': cool_cfg[0], 'Deadband': cool_cfg[1], 'Load Fraction': 1}
        ctrl_signal['HVAC Heating'] = {'Setpoint': heat_cfg[0], 'Deadband': heat_cfg[1], 'Load Fraction': 1}

    # EV control (tracks global mode)
    if EV_SIMULATION == "ON" and home_charger_kw is not None:
        ev_mode = active_commands.get("EV", "NORMAL")
        fraction = EV_SHED_PCT if ev_mode in ["SHED", "S"] else (EV_CP_PCT if ev_mode == "CP" else (EV_GE_PCT if ev_mode == "GE" else 1.0))
        commanded_kw = abs(fraction * home_charger_kw)
        ctrl_signal['EV'] = {'Max Power': max(commanded_kw, 0.001)}

    # Add batteries if simulated
    if BATTERY_SIMULATION == "ON":
        batt_mode = active_commands.get("BATTERY", "NORMAL")
        battery_p_map = {
            'ALU': P_Battery_ALU_KW,
            'LU': P_Battery_LU_KW,
            'LOAD': P_Battery_LU_KW,
            'S': P_Battery_SHED_KW,
            'SHED': P_Battery_SHED_KW,
            'CP': P_Battery_CP_KW,
            'GE': P_Battery_GE_KW
        }
        battery_p = battery_p_map.get(batt_mode, P_Battery_IDLE_KW)
        ctrl_signal['Battery'] = {
            'P Setpoint': battery_p
        }

    return ctrl_signal


def _extract_dryer_schedule_info(dw):
    """
    Retrieves the Clothes Dryer equipment object and a clean copy of its
    5-minute upsampled baseline power schedule from an initialized Dwelling.
    """
    dryer_eq = dw.get_equipment_by_end_use("Clothes Dryer")
    if dryer_eq is None or not hasattr(dryer_eq, "schedule") or dryer_eq.schedule is None:
        return None, None, None, DRYER_CAP_KW

    numeric_cols = [
        c for c in dryer_eq.schedule.columns
        if pd.api.types.is_numeric_dtype(dryer_eq.schedule[c])
    ]
    if not numeric_cols:
        return dryer_eq, None, None, DRYER_CAP_KW

    # Prefer column explicitly mentioning dryer/power, fallback to first numeric column
    preferred = [c for c in numeric_cols if "dryer" in c.lower() or "kw" in c.lower() or "power" in c.lower()]
    sched_col = preferred[0] if preferred else numeric_cols[0]

    orig_schedule = dryer_eq.schedule[sched_col].copy()
    max_val = float(orig_schedule.max())
    rated_kw = max_val if max_val > 0 else DRYER_CAP_KW
    return dryer_eq, sched_col, orig_schedule, rated_kw


def init_base(home_path, weather_file_path):
    filtered_sched_file = filter_schedules(home_path)
    hpxml_file = os.path.join(home_path, XML_ADDRESS)
    
    equipment = {}
    if BATTERY_SIMULATION == "ON":
        equipment["Battery"] = BATTERY_PARAMS
    if DRYER_SIMULATION == "ON":
        # Match ScheduledLoad class so baseline and controlled runs share identical uncurtailed behavior
        equipment["Clothes Dryer"] = {"equipment_class": ScheduledLoad}

    home_num_str = re.sub(r'\D', '', os.path.basename(home_path))
    home_seed = int(home_num_str) if home_num_str else 0

    home_charger_kw = None
    if EV_SIMULATION == "ON":
        home_charger_kw, equipment["EV"] = _build_ev_equipment(hpxml_file)
    
    dw = Dwelling(name=f"Base_{os.path.basename(home_path)}",
                  start_time=Start,
                  time_res=dt.timedelta(minutes=t_res),
                  duration=dt.timedelta(days=Duration),
                  hpxml_file=hpxml_file,
                  hpxml_schedule_file=filtered_sched_file,
                  weather_file=weather_file_path,
                  verbosity=7,
                  Equipment=equipment,
                  seed=home_seed)
    return {"path": home_path, "dw": dw}

def init_ctrl(home_path, weather_file_path):
    hpxml_file = os.path.join(home_path, XML_ADDRESS)
    # Uses the unmodified filtered_schedules.csv directly; dryer schedule is mutated live in memory
    filtered_sched_file = os.path.join(home_path, 'filtered_schedules.csv')
    
    equipment = {}
    if WH_SIMULATION == "ON":
        equipment['Water Heating'] = {
            "Initial Temperature (C)": WH_TinitC, 
            "hp_only_mode": True,
            "Max Tank Temperature": 70,
            "Upper Node": 3,
            "Lower Node": 10,
            "Upper Node Weight": 0.75,
        }

    if DRYER_SIMULATION == "ON":
        # ScheduledLoad reads dryer_eq.schedule directly at every 5-minute timestep
        equipment["Clothes Dryer"] = {"equipment_class": ScheduledLoad}

    if BATTERY_SIMULATION == "ON":
        equipment["Battery"] = BATTERY_PARAMS

    home_num_str = re.sub(r'\D', '', os.path.basename(home_path))
    home_seed = int(home_num_str) if home_num_str else 0

    home_charger_kw = None
    if EV_SIMULATION == "ON":
        home_charger_kw, equipment["EV"] = _build_ev_equipment(hpxml_file)

    dw = Dwelling(name=f"Ctrl_{os.path.basename(home_path)}",
                  start_time=Start,
                  time_res=dt.timedelta(minutes=t_res),
                  duration=dt.timedelta(days=Duration),
                  hpxml_file=hpxml_file,
                  hpxml_schedule_file=filtered_sched_file,
                  weather_file=weather_file_path,
                  verbosity=7,
                  Equipment=equipment,
                  seed=home_seed)

    dryer_eq, dryer_sched_col, dryer_orig_sched, dryer_rated_kw = _extract_dryer_schedule_info(dw)
    
    return {
        "sim": dw, 
        "path": home_path,
        "home_charger_kw": home_charger_kw,
        "device_states": {
            "WH": {"active_cmd": "NORMAL", "target_cmd": "NORMAL", "effective_time": pd.Timestamp.min, "min_delay": WH_RESPONSE_MIN, "max_delay": WH_RESPONSE_MAX, "cmd_start_time": None, "total_controlled_min": 0.0},
            "HVAC": {"active_cmd": "NORMAL", "target_cmd": "NORMAL", "effective_time": pd.Timestamp.min, "min_delay": HVAC_RESPONSE_MIN, "max_delay": HVAC_RESPONSE_MAX, "cmd_start_time": None, "total_controlled_min": 0.0},
            "DRYER": {
                "active_cmd": "NORMAL", "target_cmd": "NORMAL", "effective_time": pd.Timestamp.min,
                "min_delay": 0, "max_delay": 0, "cmd_start_time": None, "total_controlled_min": 0.0,
                "work_queue": 0.0, "pending_off": False,
                "equipment": dryer_eq, "sched_col": dryer_sched_col,
                "orig_schedule": dryer_orig_sched, "rated_kw": dryer_rated_kw
            },
            "EV": {"active_cmd": "NORMAL", "target_cmd": "NORMAL", "effective_time": pd.Timestamp.min, "min_delay": 0, "max_delay": 0, "cmd_start_time": None, "total_controlled_min": 0.0},
            "BATTERY": {"active_cmd": "NORMAL", "target_cmd": "NORMAL", "effective_time": pd.Timestamp.min, "min_delay": 0, "max_delay": 0, "cmd_start_time": None, "total_controlled_min": 0.0},
        }
    }

#########################################
# MAIN EXECUTION
#########################################

if __name__ == "__main__":
    # --- Directory Setup ---
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(WEATHER_DIR, exist_ok=True)
    
    # Copy homes from defaults
    count2 = 0
    for item in os.listdir(DEFAULT_INPUT):
        count2 += 1
        src = os.path.join(DEFAULT_INPUT, item)
        dst = os.path.join(INPUT_DIR, item)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
            count += 1
        count += 1
        
    # Copy weather file
    if not os.path.exists(WEATHER_FILE):
        shutil.copy(DEFAULT_WEATHER, WEATHER_FILE)
        count += 1

    homes = find_all_homes(INPUT_DIR)
    print(f"Found {len(homes)} homes")

    if not homes:
        print("No homes found. Exiting.")
        exit()

    # =========================================================================
    # PASS 1: OCHRE BASELINE RUN
    # =========================================================================
    print(f"--- PASS 1: Running Baseline OCHRE for {len(homes)} homes ---")
    baseline_dwellings = []
    successful_homes = [] # Track which homes actually survived initialization

    # try:
    #     init_base(homes[0], WEATHER_FILE)
    # except Exception:
    #     traceback.print_exc()
    # quit()
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as executor:
        # Use a dictionary to map the future back to the home path for logging
        futures = {executor.submit(init_base, h, WEATHER_FILE): h for h in homes}
        for f in concurrent.futures.as_completed(futures):
            home_path = futures[f]
            try:
                baseline_dwellings.append(f.result())
                successful_homes.append(home_path)
            except Exception as e:
                # Catch the error, print a warning, and move on
                print(f"Skipping {os.path.basename(home_path)} due to init error: {e}")
                
    # Reassign the main homes list so Pass 2 completely ignores the broken homes
    homes = successful_homes

    if not homes:
        print("No dwellings were initialized. Exiting.")
        exit()
            
    sim_times = baseline_dwellings[0]["dw"].sim_times
    
    # Run Baseline Loop
    for t in sim_times:
        for b in baseline_dwellings:
            b["dw"].update()
            
    # Extract True Baseline Data
    baseline_data = {}
    for b in baseline_dwellings:
        df, _, _ = b["dw"].finalize()
        baseline_data[b["path"]] = df

    # =========================================================================
    # PASS 2: OCHRE CONTROL RUN (REACTIVE LOAD SHAPING & LIVE DRYER CONTROL)
    # =========================================================================
    print("--- PASS 2: Running Controlled OCHRE Simulation (Live Dryer + VPP PID) ---")
    fleet_data = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(init_ctrl, h, WEATHER_FILE) for h in homes]
        for f in concurrent.futures.as_completed(futures):
            try:
                fleet_data.append(f.result())
            except Exception as e:
                print("Initialization failed:", e)

    num_homes = len(fleet_data)
    average_power_kw = 0.0
    vpp_state_log = [] # Add this line to initialize the log

    # PID State tracking variables
    integral_error = 0.0
    previous_error = 0.0
    in_deadband_minutes = 0.0

    enabled_simulations = {
        "WH": WH_SIMULATION, "HVAC": HVAC_SIMULATION, "DRYER": DRYER_SIMULATION,
        "EV": EV_SIMULATION, "BATTERY": BATTERY_SIMULATION
    }

    # Helpers to verify live EV charging state, active dryer work, and per-home device capacity
    def is_ev_charging(home_data):
        ev_eq = home_data["sim"].get_equipment_by_end_use("EV")
        if ev_eq is None or not getattr(ev_eq, "in_event", False):
            return False
        soc = getattr(ev_eq, "soc", 0.0)
        soc_max = getattr(ev_eq, "soc_max_ctrl", 1.0)
        return soc < (soc_max - 1e-4)

    def is_dryer_active(home_data, current_time):
        # True if the dryer currently has queued work or scheduled load arriving at current_time
        d_state = home_data["device_states"]["DRYER"]
        orig_sched = d_state.get("orig_schedule")
        incoming_kw = float(orig_sched.loc[current_time]) if (orig_sched is not None and current_time in orig_sched.index) else 0.0
        return (d_state["work_queue"] + incoming_kw) > 1e-4

    def get_device_cap_kw(home_data, dev):
        if dev == "EV" and home_data.get("home_charger_kw") is not None:
            return home_data["home_charger_kw"]
        if dev == "DRYER":
            return home_data["device_states"]["DRYER"].get("rated_kw", DRYER_CAP_KW)
        return FRAC_MAP[dev]["CAP"]

    print("Starting Co-Simulation Time Loop...")
    for sim_time in sim_times:
        deadband_released_this_step = 0
        
        # Reset any EV that has unplugged or finished charging back to NORMAL
        if EV_SIMULATION == "ON":
            for h in fleet_data:
                if h["device_states"]["EV"]["target_cmd"] != "NORMAL" and not is_ev_charging(h):
                    set_device_target_cmd(h["device_states"]["EV"], "NORMAL", sim_time)

        # Accumulate cumulative controlled minutes across all active devices (including DRYER)
        for h in fleet_data:
            for dev_name, dev_state in h["device_states"].items():
                if dev_state["target_cmd"] != "NORMAL":
                    dev_state["total_controlled_min"] += t_res

        # Determine smoothly interpolated VPP state and deadband from CSV schedule
        is_vpp_active, AVERAGE_SETPOINT_KW, AVERAGE_DEADBAND_KW = get_interpolated_vpp_settings(
            sim_time, hourly_settings
        )

        if is_vpp_active:
            
            # --- Active Load Shaping Dispatch Logic (Bidirectional & Asymmetrical) ---
            # Calculate raw error first: Error = Setpoint - Actual
            raw_error = AVERAGE_SETPOINT_KW - average_power_kw
            priority_list = FAST_COMMAND_PRIORITY if raw_error > 0.25 else SLOW_COMMAND_PRIORITY
            
            # 1. Apply the deadband directly to the actual error
            if abs(raw_error) <= AVERAGE_DEADBAND_KW:
                # Inside the deadband: freeze PID error tracking and track deadband dwell time
                # pid_output = 0.0
                error = 0.0
                integral_error = 0.0
                previous_error = 0.0
                in_deadband_minutes += t_res

                # Once power remains within deadband long enough, gradually release stuck devices
                if in_deadband_minutes >= DEADBAND_SETTLE_MINUTES:
                    deadband_released_this_step = release_stuck_devices_in_deadband(
                        fleet_data=fleet_data,
                        sim_time=sim_time,
                        average_power_kw=average_power_kw,
                        setpoint_kw=AVERAGE_SETPOINT_KW,
                        deadband_kw=AVERAGE_DEADBAND_KW,
                        num_homes=num_homes,
                        enabled_simulations=enabled_simulations,
                        get_device_cap_kw_fn=get_device_cap_kw,
                        is_ev_charging_fn=is_ev_charging,
                        is_dryer_active_fn=lambda h: is_dryer_active(h, sim_time),
                    )
            else:
                # Outside the deadband: compute PID normally and reset deadband dwell timer
                in_deadband_minutes = 0.0
                error = raw_error
                priority_list = FAST_COMMAND_PRIORITY if error > 0.25 else SLOW_COMMAND_PRIORITY
            
            # Discrete-time tracking transformations
            integral_error += error
            
            # --- ANTI-WINDUP CLAMPING ---
            # Prevent the integral from building up a massive "memory" when error stays positive or negative for hours
            MAX_INTEGRAL = 1.0
            MIN_INTEGRAL = -1.0
            integral_error = max(min(integral_error, MAX_INTEGRAL), MIN_INTEGRAL)
            
            derivative_error = error - previous_error
            previous_error = error
            
            # Compute PID output value
            pid_output = (KP * error) + (KI * integral_error) + (KD * derivative_error)
            
            # 2. Trigger dispatch using a near-zero threshold, since the deadband is already handled
            if pid_output < -0.01:
                # OVER setpoint -> Need to DROP load
                total_kw_to_drop = abs(pid_output) * num_homes
                
                # 1. Turn off active LOAD commands first (High impact, using explicit END fractions)
                for dev in priority_list:
                    if total_kw_to_drop <= 0: break
                    if enabled_simulations.get(dev) != "ON": continue
                    
                    for active_cmd in ["ALU", "LU", "LOAD"]:
                        homes_to_end = [
                            h for h in fleet_data
                            if h["device_states"][dev]["target_cmd"] == active_cmd
                            and (dev != "EV" or is_ev_charging(h))
                        ]
                        # Prioritize releasing devices held for the longest continuous duration
                        homes_to_end.sort(key=lambda item: (-get_device_hold_minutes(item["device_states"][dev], sim_time), random.random()))
                        
                        # Use your explicit END_ fraction logic
                        frac_key = active_cmd if active_cmd != "LOAD" else "LU"
                        end_frac_key = f"END_{active_cmd}" if active_cmd != "LOAD" else "END_LU"
                        frac_diff = FRAC_MAP[dev][frac_key] - FRAC_MAP[dev][end_frac_key]
                        
                        if frac_diff > 0:
                            for h in homes_to_end:
                                if total_kw_to_drop <= 0: break
                                drop_per_unit = frac_diff * get_device_cap_kw(h, dev)
                                if drop_per_unit > 0:
                                    set_device_target_cmd(h["device_states"][dev], "NORMAL", sim_time)
                                    total_kw_to_drop -= drop_per_unit
                        
                # 2. Cascade into deeper shed commands (Conservative first across ALL devices, including DRYER live)
                shed_transitions = [
                    ("NORMAL", "SHED"),
                    ("SHED", "CP"),
                    ("CP", "GE")
                ]
                
                for current_state, next_state in shed_transitions:
                    if total_kw_to_drop <= 0: break
                    
                    for dev in priority_list:
                        if total_kw_to_drop <= 0: break
                        if enabled_simulations.get(dev) != "ON": continue
                        
                        if next_state in ALLOWED_COMMANDS:
                            available_homes = [
                                h for h in fleet_data
                                if h["device_states"][dev]["target_cmd"] == current_state
                                and (dev != "EV" or is_ev_charging(h))
                                and (dev != "DRYER" or is_dryer_active(h, sim_time))
                            ]
                            # Rotate control burden across homes with lowest cumulative controlled time
                            available_homes.sort(key=lambda item: (item["device_states"][dev]["total_controlled_min"], random.random()))
                            
                            # Drop = Current Command Power - Next Command Power
                            drop_fraction = FRAC_MAP[dev][current_state] - FRAC_MAP[dev][next_state]
                            
                            if drop_fraction > 0:
                                for h in available_homes:
                                    if total_kw_to_drop <= 0: break
                                    drop_per_unit = drop_fraction * get_device_cap_kw(h, dev)
                                    if drop_per_unit > 0:
                                        set_device_target_cmd(h["device_states"][dev], next_state, sim_time)
                                        total_kw_to_drop -= drop_per_unit
                        
            elif pid_output > 0.01:
                # UNDER setpoint -> Need to ADD load
                total_kw_to_add = pid_output * num_homes
                
                # 1. Turn off active SHED commands first (Low impact, using explicit END fractions, including DRYER live)
                for dev in priority_list:
                    if total_kw_to_add <= 0: break
                    if enabled_simulations.get(dev) != "ON": continue
                    
                    for active_cmd in ["GE", "CP", "SHED"]:
                        homes_to_end = [
                            h for h in fleet_data
                            if h["device_states"][dev]["target_cmd"] == active_cmd
                            and (dev != "EV" or is_ev_charging(h))
                        ]
                        # Prioritize releasing devices held for the longest continuous duration
                        homes_to_end.sort(key=lambda item: (-get_device_hold_minutes(item["device_states"][dev], sim_time), random.random()))
                        
                        frac_diff = FRAC_MAP[dev][f'END_{active_cmd}'] - FRAC_MAP[dev][f'{active_cmd}']

                        if frac_diff > 0:
                            for h in homes_to_end:
                                if total_kw_to_add <= 0: break
                                if dev == "DRYER" and not is_dryer_active(h, sim_time):
                                    # Restoring an idle dryer adds 0 kW, so free it without consuming kW budget
                                    set_device_target_cmd(h["device_states"][dev], "NORMAL", sim_time)
                                    continue
                                add_per_unit = frac_diff * get_device_cap_kw(h, dev)
                                if add_per_unit > 0:
                                    set_device_target_cmd(h["device_states"][dev], "NORMAL", sim_time)
                                    total_kw_to_add -= add_per_unit
                            
                # 2. Cascade into deeper load commands (Conservative first)
                load_transitions = [
                    ("NORMAL", "LU"),
                    ("LU", "ALU")
                ]
                
                for current_state, next_state in load_transitions:
                    if total_kw_to_add <= 0: break
                    
                    for dev in priority_list:
                        if total_kw_to_add <= 0: break
                        if enabled_simulations.get(dev) != "ON": continue
                        
                        if next_state in ALLOWED_COMMANDS:
                            available_homes = [
                                h for h in fleet_data
                                if h["device_states"][dev]["target_cmd"] == current_state
                                and (dev != "EV" or is_ev_charging(h))
                            ]
                            # Rotate control burden across homes with lowest cumulative controlled time
                            available_homes.sort(key=lambda item: (item["device_states"][dev]["total_controlled_min"], random.random()))
                            
                            # Drop = Current Command Power - Next Command Power
                            add_fraction = FRAC_MAP[dev][next_state] - FRAC_MAP[dev][current_state]
                            
                            if add_fraction > 0:
                                for h in available_homes:
                                    if total_kw_to_add <= 0: break
                                    add_per_unit = add_fraction * get_device_cap_kw(h, dev)
                                    if add_per_unit > 0:
                                        set_device_target_cmd(h["device_states"][dev], next_state, sim_time)
                                        total_kw_to_add -= add_per_unit

        else:
            # --- VPP is OFF. Force all homes back to normal ---
            for h in fleet_data:
                for dev_name in h["device_states"]:
                    set_device_target_cmd(h["device_states"][dev_name], "NORMAL", sim_time)
            
            # Reset PID memory tracking to prevent baseline distortion at next event start
            integral_error = 0.0
            previous_error = 0.0
            in_deadband_minutes = 0.0

        # Initialize 
        current_step_aggregate_power = 0.0
        
        for home_data in fleet_data:
            sim_dw = home_data["sim"]
            
            # Evaluate delayed reactive commands across all enabled devices
            active_cmds = {}
            for dev_name, dev_state in home_data["device_states"].items():
                active_cmds[dev_name] = update_device_command(
                    dev_state,
                    dev_state["target_cmd"],
                    sim_time
                )

            # Mutate the dryer's 5-minute in-memory schedule before OCHRE updates
            if DRYER_SIMULATION == "ON":
                update_dryer_live_schedule(home_data, sim_time)
            
            # 2. Controlled Update (driven purely by the VPP state now)
            control_cmd = determine_control(
                sim_time=sim_time,
                active_commands=active_cmds,
                home_charger_kw=home_data.get("home_charger_kw")
            )
            
            # The update() method usually returns a dictionary of the current timestep's metrics
            metrics = sim_dw.update(control_signal=control_cmd)
            
            # 3. Read back real-time power
            # We will try the returned metrics first, then fall back to the standard current_results attribute
            if isinstance(metrics, dict) and "Total Electric Power (kW)" in metrics:
                home_power = metrics["Total Electric Power (kW)"]
            elif hasattr(sim_dw, 'current_results'):
                home_power = sim_dw.current_results.get("Total Electric Power (kW)", 0.0)
            else:
                # Failsafe so the code doesn't crash, though it means our VPP controller will read 0
                home_power = 0.0 
                
            current_step_aggregate_power += home_power
            
        # Recalculate average fleet power for the next time step's logic
        aggregate_power_kw = current_step_aggregate_power
        average_power_kw = aggregate_power_kw / num_homes

        active_hold_durations = [
            get_device_hold_minutes(h["device_states"][dev], sim_time)
            for h in fleet_data
            for dev in ["WH", "HVAC", "DRYER", "EV", "BATTERY"]
            if h["device_states"][dev]["target_cmd"] != "NORMAL"
        ]

        # --- NEW: Log Fleet States for this Timestep ---
        vpp_state_log.append({
            "Time": sim_time,
            "Target Average Power (kW)": AVERAGE_SETPOINT_KW if is_vpp_active else "OFF",
            "Deadband (kW)": AVERAGE_DEADBAND_KW if is_vpp_active else "OFF",
            "Actual Average Power (kW)": average_power_kw,
            "Aggregate Power (kW)": aggregate_power_kw,
            "In Deadband Duration (min)": in_deadband_minutes if is_vpp_active else 0.0,
            "Deadband Released Devices": deadband_released_this_step,
            "Avg Device Hold (min)": float(np.mean(active_hold_durations)) if active_hold_durations else 0.0,
            "Max Device Hold (min)": float(np.max(active_hold_durations)) if active_hold_durations else 0.0,
            "WH in NORMAL": sum(1 for h in fleet_data if h["device_states"]["WH"]["active_cmd"] == "NORMAL"),
            "WH in ALU": sum(1 for h in fleet_data if h["device_states"]["WH"]["active_cmd"] in ["ALU"]),
            "WH in LOAD": sum(1 for h in fleet_data if h["device_states"]["WH"]["active_cmd"] in ["LOAD", "LU"]),
            "WH in SHED": sum(1 for h in fleet_data if h["device_states"]["WH"]["active_cmd"] in ["SHED"]),
            "WH in CP": sum(1 for h in fleet_data if h["device_states"]["WH"]["active_cmd"] in ["CP"]),
            "WH in GE": sum(1 for h in fleet_data if h["device_states"]["WH"]["active_cmd"] in ["GE"]),
            "HVAC in NORMAL": sum(1 for h in fleet_data if h["device_states"]["HVAC"]["active_cmd"] == "NORMAL"),
            "HVAC in ALU": sum(1 for h in fleet_data if h["device_states"]["HVAC"]["active_cmd"] in ["ALU"]),
            "HVAC in LOAD": sum(1 for h in fleet_data if h["device_states"]["HVAC"]["active_cmd"] in ["LOAD", "LU"]),
            "HVAC in SHED": sum(1 for h in fleet_data if h["device_states"]["HVAC"]["active_cmd"] in ["SHED"]),
            "HVAC in CP": sum(1 for h in fleet_data if h["device_states"]["HVAC"]["active_cmd"] in ["CP"]),
            "HVAC in GE": sum(1 for h in fleet_data if h["device_states"]["HVAC"]["active_cmd"] in ["GE"]),
            "DRY in NORMAL": sum(1 for h in fleet_data if h["device_states"]["DRYER"]["active_cmd"] == "NORMAL"),
            "DRY in SHED": sum(1 for h in fleet_data if h["device_states"]["DRYER"]["active_cmd"] == "SHED"),
            "DRY in CP": sum(1 for h in fleet_data if h["device_states"]["DRYER"]["active_cmd"] == "CP"),
            "DRY in GE": sum(1 for h in fleet_data if h["device_states"]["DRYER"]["active_cmd"] == "GE"),
            "EV in NORMAL": sum(1 for h in fleet_data if h["device_states"]["EV"]["active_cmd"] == "NORMAL"),
            "EV in SHED": sum(1 for h in fleet_data if h["device_states"]["EV"]["active_cmd"] in ["SHED"]),
            "EV in CP": sum(1 for h in fleet_data if h["device_states"]["EV"]["active_cmd"] in ["CP"]),
            "EV in GE": sum(1 for h in fleet_data if h["device_states"]["EV"]["active_cmd"] in ["GE"]),
            "BATT in NORMAL": sum(1 for h in fleet_data if h["device_states"]["BATTERY"]["active_cmd"] == "NORMAL"),
            "BATT in ALU": sum(1 for h in fleet_data if h["device_states"]["BATTERY"]["active_cmd"] in ["ALU"]),
            "BATT in LOAD": sum(1 for h in fleet_data if h["device_states"]["BATTERY"]["active_cmd"] in ["LOAD", "LU"]),
            "BATT in SHED": sum(1 for h in fleet_data if h["device_states"]["BATTERY"]["active_cmd"] in ["SHED"]),
            "BATT in CP": sum(1 for h in fleet_data if h["device_states"]["BATTERY"]["active_cmd"] in ["CP"]),
            "BATT in GE": sum(1 for h in fleet_data if h["device_states"]["BATTERY"]["active_cmd"] in ["GE"]),
        })

    # --- 3. Finalize and Output Data ---
    print("Simulation complete! Finalizing results...")
    
    CTRL_COLS = ["Time", "Total Electric Power (kW)", "Total Electric Energy (kWh)"]
    if WH_SIMULATION == "ON":
        CTRL_COLS.append("Water Heating Electric Power (kW)")
    # if HVAC_SIMULATION == "ON":
        CTRL_COLS.extend(["HVAC Heating Electric Power (kW)", "HVAC Cooling Electric Power (kW)"])
    # if DRYER_SIMULATION == "ON":
        CTRL_COLS.append("Clothes Dryer Electric Power (kW)")
    # if EV_SIMULATION == "ON":
        CTRL_COLS.append("EV Electric Power (kW)")
        CTRL_COLS.append("EV SOC (-)")
    # if BATTERY_SIMULATION == "ON":
        CTRL_COLS.append("Battery Electric Power (kW)")
        CTRL_COLS.append("Battery SOC (-)")
    
    for home_data in fleet_data:
        home_path = home_data["path"]
        results_dir = os.path.join(home_path, "Results")
        os.makedirs(results_dir, exist_ok=True)
        
        # Pull baseline data calculated from pass 1
        df_base = baseline_data[home_path]
        df_ctrl, _, _ = home_data["sim"].finalize()
        
        df_base = remove_first_day(df_base, Start)
        df_ctrl = remove_first_day(df_ctrl, Start)
        
        df_ctrl = df_ctrl[[c for c in CTRL_COLS if c in df_ctrl.columns]]
        df_base = df_base[[c for c in CTRL_COLS if c in df_base.columns]]
        
        df_ctrl.to_csv(os.path.join(results_dir, 'home_controlled.csv'), index=False)
        df_base.to_csv(os.path.join(results_dir, 'home_baseline.csv'), index=False)

    # --- 4. Aggregate ---
    aggregate_results(homes, WORKING_DIR)

    # --- 5. Export VPP State Log ---
    print("Saving VPP state log...")
    df_vpp_log = pd.DataFrame(vpp_state_log)
    df_vpp_log = remove_first_day(df_vpp_log, Start)
    os.makedirs(os.path.join(WORKING_DIR, "ready_data", filename), exist_ok=True)
    vpp_log_path = os.path.join(WORKING_DIR, "ready_data", filename, filename + "_VPP_Fleet_States.csv")
    df_vpp_log.to_csv(vpp_log_path, index=False)
    print(f"VPP State Log saved to: {vpp_log_path}")