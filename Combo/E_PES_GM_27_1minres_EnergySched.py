# -*- coding: utf-8 -*-
"""
1-Minute Resolution Energy Scheduling Simulation, Data Parsing, and Plotting
Starts at Midnight (00:00), Initialized 00:00-08:00, Evaluated 08:00-10:00
Load Up Command sent at 08:30
"""

import os
import shutil
import datetime as dt
import pandas as pd
import xml.etree.ElementTree as ET
import re
import copy
import concurrent.futures
from pathlib import Path
import ochre
from ochre import Dwelling
from ochre.utils.schedule import ALL_SCHEDULE_NAMES
import numpy as np
import random
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

#########################################
# USER SETTINGS & PATH SETUP
#########################################

# --- TOGGLE SWITCH FOR SIMULATION ---
# Set to False to skip OCHRE simulation and quickly adjust/re-generate plots
RUN_SIMULATION = False  

filename = 'IEEE_PES_GM_27_1min_1'
Input_folder = "IEEE PES GM 2027 All Input Files"

ochre_dir = Path(ochre.__file__).resolve().parent
DEFAULT_INPUT = ochre_dir / "defaults" / "Input Files"
DEFAULT_WEATHER = ochre_dir / "defaults" / "Weather" / "USA_OR_Portland.Intl.AP.726980_TMY3.epw"

script_dir = os.path.dirname(os.path.abspath(__file__))
fl_dir = os.path.dirname(script_dir)
WORKING_DIR = os.path.dirname(fl_dir)
INPUT_DIR = os.path.join(WORKING_DIR, Input_folder, "bldg")
WEATHER_DIR = os.path.join(WORKING_DIR, "Weather")
WEATHER_FILE = os.path.join(WEATHER_DIR, "USA_OR_Portland.Intl.AP.726980_TMY3.epw")
XML_ADDRESS = "home.xml"
CSV_ADDRESS = "in.schedules.csv"

# ---------------------------------------------------------
# SIMULATION TIMING (1-Minute Resolution, 10-Hour Total Run)
# ---------------------------------------------------------
Start = dt.datetime(2018, 8, 11, 0, 0)
Duration = dt.timedelta(hours=10)  # 00:00 to 10:00 (8h initialization + 2h study)
t_res = 1  # 1 minute time resolution

# Study window for output data and plotting
STUDY_START_TIME = dt.time(8, 0)
STUDY_END_TIME = dt.time(10, 0)

# ---------------------------------------------------------
# CONTROL PARAMETERS (°F)
# ---------------------------------------------------------
# Water Heater Controls
WH_Tcontrol_GEF = 90
WH_Tcontrol_GEdeadbandF = 10
WH_Tcontrol_CPF = 120
WH_Tcontrol_CPdeadbandF = 10
WH_Tcontrol_SHEDF = 126
WH_Tcontrol_deadbandF = 10
WH_Tcontrol_ALUF = 140
WH_Tcontrol_ALUdeadbandF = 2
WH_Tcontrol_LOADF = 130
WH_Tcontrol_LOADdeadbandF = 2

WH_TbaselineF = 130
WH_TdeadbandF = 7
WH_Tinit = 130

WH_RESPONSE_MIN = 30
WH_RESPONSE_MAX = 90

# AC Controls
AC_Tcontrol_GEF = 95
AC_Tcontrol_GEdeadbandF = 4
AC_Tcontrol_CPF = 80
AC_Tcontrol_CPdeadbandF = 4
AC_Tcontrol_SHEDF = 76
AC_Tcontrol_deadbandF = 4
AC_Tcontrol_ALUF = 64
AC_Tcontrol_ALUdeadbandF = 2
AC_Tcontrol_LOADF = 68
AC_Tcontrol_LOADdeadbandF = 2

AC_TbaselineF = 72
AC_TdeadbandF = 2
AC_TinitF = 72

# Heating Controls
HEAT_Tcontrol_GEF = 45
HEAT_Tcontrol_GEdeadbandF = 4
HEAT_Tcontrol_CPF = 60
HEAT_Tcontrol_CPdeadbandF = 4
HEAT_Tcontrol_SHEDF = 64
HEAT_Tcontrol_deadbandF = 4
HEAT_Tcontrol_ALUF = 76
HEAT_Tcontrol_ALUdeadbandF = 2
HEAT_Tcontrol_LOADF = 72
HEAT_Tcontrol_LOADdeadbandF = 2

HEAT_TbaselineF = 68
HEAT_TdeadbandF = 2
HEAT_TinitF = 68

HVAC_RESPONSE_MIN = 30
HVAC_RESPONSE_MAX = 90

# Dryer duty cycles
dryer_duty_cycle_shed = 0.5
dryer_duty_cycle_cp = 0.25
dryer_duty_cycle_ge = 0

# EV Settings
DEFAULT_CHARGER_POWER_KW = 11.5
DEFAULT_CAPACITY_KWH = 60.0
EV_SHED_PCT = 0.5
EV_CP_PCT = 0.25
EV_GE_PCT = 0

# Battery Settings
BATTERY_PARAMS = {
    "capacity_kwh": 10,
    "capacity": 1.0,
    "efficiency": 0.98,
    "efficiency_charge": 0.98,
    "soc_init": 0.5,
    "soc_min": 0.0,
    "soc_max": 1.0,
}

P_Battery_ALU_KW = 1.0 * BATTERY_PARAMS['capacity']
P_Battery_LU_KW = 0.25 * BATTERY_PARAMS['capacity']
P_Battery_SHED_KW = -0.25 * BATTERY_PARAMS['capacity']
P_Battery_CP_KW = -0.5 * BATTERY_PARAMS['capacity']
P_Battery_GE_KW = -1.0 * BATTERY_PARAMS['capacity']
P_Battery_IDLE_KW = 0.0

# ---------------------------------------------------------
# LOAD DEVICE CONFIGURATION
# ---------------------------------------------------------
devices_file = os.path.join(script_dir, "B0_Devices.csv")
try:
    df_devices = pd.read_csv(devices_file)
    device_sim_map = dict(zip(df_devices['Device'], df_devices['Simulation']))
except FileNotFoundError:
    print(f"[WARNING] {devices_file} not found. Defaulting to OFF.")
    device_sim_map = {}

WH_SIMULATION = device_sim_map.get("WH", "OFF")
HVAC_SIMULATION = device_sim_map.get("HVAC", "OFF")
# DRYER_SIMULATION = device_sim_map.get("Dryer", "OFF")
# EV_SIMULATION = device_sim_map.get("EV", "OFF")
DRYER_SIMULATION = "OFF"
EV_SIMULATION = "OFF"
BATTERY_SIMULATION = device_sim_map.get("Battery", "OFF")

# ---------------------------------------------------------
# LOAD COMMAND SCHEDULE (Defaults to Load Up at 08:30)
# ---------------------------------------------------------
schedule_file = os.path.join(script_dir, "B0_Commands_Schedule.csv")
my_schedule1 = {}

try:
    df_sched = pd.read_csv(schedule_file)
    for index, row in df_sched.iterrows():
        command = str(row['Command']).strip()
        on_off = str(row['OnOff']).strip().upper()
        
        if on_off == 'ON':
            start_rin_str = str(row['START RAMP IN']).strip()
            dur_rin = float(row['DURATION RAMP IN'])
            t_start_rin = dt.datetime.strptime(start_rin_str, '%H:%M')
            t_end_rin = t_start_rin + dt.timedelta(hours=dur_rin)
            
            my_schedule1[f"{command}_rampin_start"] = t_start_rin.strftime('%H:%M')
            my_schedule1[f"{command}_rampin_end"] = t_end_rin.strftime('%H:%M')
            
            start_rout_str = str(row['START RAMP OUT']).strip()
            dur_rout = float(row['DURATION RAMP OUT'])
            t_start_rout = dt.datetime.strptime(start_rout_str, '%H:%M')
            t_end_rout = t_start_rout + dt.timedelta(hours=dur_rout)
            
            my_schedule1[f"{command}_rampout_start"] = t_start_rout.strftime('%H:%M')
            my_schedule1[f"{command}_rampout_end"] = t_end_rout.strftime('%H:%M')
except FileNotFoundError:
    print(f"[INFO] {schedule_file} not found. Injecting default 08:30 Load Up command.")

# Default fallback: Send Load Up command at 08:30 AM
if not my_schedule1:
    my_schedule1 = {
        'M_LU_rampin_start': '08:30',
        'M_LU_rampin_end': '08:30',
        'M_LU_rampout_start': '10:00',
        'M_LU_rampout_end': '10:00'
    }

bins = 17

#########################################
# STAGGER SCHEDULES & HELPERS
#########################################

def create_home_schedule(base_sched, bins, home_idx):
    bin_idx = home_idx % bins
    ramp_fraction = (bin_idx / (bins - 1)) if bins > 1 else 0

    def parse_time(time_str):
        t = dt.datetime.strptime(time_str, '%H:%M')
        return pd.Timedelta(hours=t.hour, minutes=t.minute)

    home_schedule = {}
    times_of_day = ['M', 'E']
    modes = ['ALU', 'LU', 'S', 'CP', 'GE']

    for tod in times_of_day:
        for mode in modes:
            prefix = f"{tod}_{mode}"
            rin_start_str = base_sched.get(f"{prefix}_rampin_start", "00:00")
            rin_end_str = base_sched.get(f"{prefix}_rampin_end", rin_start_str)
            rin_start_td, rin_end_td = parse_time(rin_start_str), parse_time(rin_end_str)
            home_start_td = rin_start_td + ((rin_end_td - rin_start_td) * ramp_fraction)

            rout_start_str = base_sched.get(f"{prefix}_rampout_start", "00:00")
            rout_end_str = base_sched.get(f"{prefix}_rampout_end", rout_start_str)
            rout_start_td, rout_end_td = parse_time(rout_start_str), parse_time(rout_end_str)
            home_end_td = rout_start_td + ((rout_end_td - rout_start_td) * ramp_fraction)

            home_schedule[prefix] = (home_start_td, home_end_td)

    return home_schedule

def f_to_c(temp_f): return (temp_f - 32) * 5/9
def f_to_c_DB(temp_f): return 5/9 * temp_f

WH_Tcontrol_GEC, WH_Tcontrol_GEdeadbandC = f_to_c(WH_Tcontrol_GEF), f_to_c_DB(WH_Tcontrol_GEdeadbandF)
WH_Tcontrol_CPC, WH_Tcontrol_CPdeadbandC = f_to_c(WH_Tcontrol_CPF), f_to_c_DB(WH_Tcontrol_CPdeadbandF)
WH_Tcontrol_SHEDC, WH_Tcontrol_deadbandC = f_to_c(WH_Tcontrol_SHEDF), f_to_c_DB(WH_Tcontrol_deadbandF)
WH_Tcontrol_ALUC, WH_Tcontrol_ALUdeadbandC = f_to_c(WH_Tcontrol_ALUF), f_to_c_DB(WH_Tcontrol_ALUdeadbandF)
WH_Tcontrol_LOADC, WH_Tcontrol_LOADdeadbandC = f_to_c(WH_Tcontrol_LOADF), f_to_c_DB(WH_Tcontrol_LOADdeadbandF)
WH_TbaselineC, WH_TdeadbandC, WH_TinitC = f_to_c(WH_TbaselineF), f_to_c_DB(WH_TdeadbandF), f_to_c(WH_Tinit)

AC_Tcontrol_GEC, AC_Tcontrol_GEdeadbandC = f_to_c(AC_Tcontrol_GEF), f_to_c_DB(AC_Tcontrol_GEdeadbandF)
AC_Tcontrol_CPC, AC_Tcontrol_CPdeadbandC = f_to_c(AC_Tcontrol_CPF), f_to_c_DB(AC_Tcontrol_CPdeadbandF)
AC_Tcontrol_SHEDC, AC_Tcontrol_deadbandC = f_to_c(AC_Tcontrol_SHEDF), f_to_c_DB(AC_Tcontrol_deadbandF)
AC_Tcontrol_ALUC, AC_Tcontrol_ALUdeadbandC = f_to_c(AC_Tcontrol_ALUF), f_to_c_DB(AC_Tcontrol_ALUdeadbandF)
AC_Tcontrol_LOADC, AC_Tcontrol_LOADdeadbandC = f_to_c(AC_Tcontrol_LOADF), f_to_c_DB(AC_Tcontrol_LOADdeadbandF)
AC_TbaselineC, AC_TdeadbandC, AC_TinitC = f_to_c(AC_TbaselineF), f_to_c_DB(AC_TdeadbandF), f_to_c(AC_TinitF)

HEAT_Tcontrol_GEC, HEAT_Tcontrol_GEdeadbandC = f_to_c(HEAT_Tcontrol_GEF), f_to_c_DB(HEAT_Tcontrol_GEdeadbandF)
HEAT_Tcontrol_CPC, HEAT_Tcontrol_CPdeadbandC = f_to_c(HEAT_Tcontrol_CPF), f_to_c_DB(HEAT_Tcontrol_CPdeadbandF)
HEAT_Tcontrol_SHEDC, HEAT_Tcontrol_deadbandC = f_to_c(HEAT_Tcontrol_SHEDF), f_to_c_DB(HEAT_Tcontrol_deadbandF)
HEAT_Tcontrol_ALUC, HEAT_Tcontrol_ALUdeadbandC = f_to_c(HEAT_Tcontrol_ALUF), f_to_c_DB(HEAT_Tcontrol_ALUdeadbandF)
HEAT_Tcontrol_LOADC, HEAT_Tcontrol_LOADdeadbandC = f_to_c(HEAT_Tcontrol_LOADF), f_to_c_DB(HEAT_Tcontrol_LOADdeadbandF)
HEAT_TbaselineC, HEAT_TdeadbandC, HEAT_TinitC = f_to_c(HEAT_TbaselineF), f_to_c_DB(HEAT_TdeadbandF), f_to_c(HEAT_TinitF)

def get_ev_charger_power(hpxml_path, default_kw=20):
    try:
        tree = ET.parse(hpxml_path)
        root = tree.getroot()
        for elem in root.iter():
            if '}' in elem.tag: elem.tag = elem.tag.split('}', 1)[1]
        for charger in root.findall('.//ElectricVehicleCharger'):
            charge_elem = charger.find('ChargingPower')
            if charge_elem is not None and charge_elem.text: return float(charge_elem.text) / 1000
    except Exception: pass
    return default_kw

def get_ev_capacity_or_range(hpxml_path, default_capacity_kwh=60.0):
    try:
        tree = ET.parse(hpxml_path)
        root = tree.getroot()
        for elem in root.iter():
            if '}' in elem.tag: elem.tag = elem.tag.split('}', 1)[1]
        for battery in root.findall('.//Battery'):
            usable = battery.find('UsableCapacity/Value')
            if usable is not None and usable.text: return float(usable.text)
            nominal = battery.find('NominalCapacity/Value')
            if nominal is not None and nominal.text: return float(nominal.text)
    except Exception: pass
    return default_capacity_kwh

#########################################
# CONTROL EVALUATION
#########################################

def determine_control(sim_time, current_temp_c, home_schedule_td, home_charger_kw=None, 
                      wh_delay=None, hvac_delay=None, **kwargs):
    wh_delay = wh_delay if wh_delay is not None else pd.Timedelta(seconds=0)
    hvac_delay = hvac_delay if hvac_delay is not None else pd.Timedelta(seconds=0)
    ctrl_signal = {}

    if WH_SIMULATION == "ON":
        ctrl_signal['Water Heating'] = {'Setpoint': WH_TbaselineC, 'Deadband': WH_TdeadbandC, 'Load Fraction': 1}

    is_cooling_season = sim_time.month in [5, 6, 7, 8, 9]

    if HVAC_SIMULATION == "ON":
        if is_cooling_season:
            ctrl_signal['HVAC Cooling'] = {'Setpoint': AC_TbaselineC, 'Deadband': AC_TdeadbandC, 'Load Fraction': 1}
            ctrl_signal['HVAC Heating'] = {'Setpoint': HEAT_Tcontrol_GEC, 'Deadband': HEAT_TdeadbandC, 'Load Fraction': 1}
        else:
            ctrl_signal['HVAC Heating'] = {'Setpoint': HEAT_TbaselineC, 'Deadband': HEAT_TdeadbandC, 'Load Fraction': 1}
            ctrl_signal['HVAC Cooling'] = {'Setpoint': AC_Tcontrol_GEC, 'Deadband': AC_TdeadbandC, 'Load Fraction': 1}

    if DRYER_SIMULATION == "ON":
        ctrl_signal['Clothes Dryer'] = {'Load Fraction': 1}

    if BATTERY_SIMULATION == "ON":
        ctrl_signal['Battery'] = {'P Setpoint': P_Battery_IDLE_KW}

    midnight = pd.to_datetime(sim_time.date())
    modes = [
        ('ALU', WH_Tcontrol_ALUC, WH_Tcontrol_ALUdeadbandC, AC_Tcontrol_ALUC, AC_Tcontrol_ALUdeadbandC, HEAT_Tcontrol_ALUC, HEAT_Tcontrol_ALUdeadbandC),
        ('LU',  WH_Tcontrol_LOADC, WH_Tcontrol_LOADdeadbandC, AC_Tcontrol_LOADC, AC_Tcontrol_LOADdeadbandC, HEAT_Tcontrol_LOADC, HEAT_Tcontrol_LOADdeadbandC),
        ('S',   WH_Tcontrol_SHEDC, WH_Tcontrol_deadbandC, AC_Tcontrol_SHEDC, AC_Tcontrol_deadbandC, HEAT_Tcontrol_SHEDC, HEAT_Tcontrol_deadbandC),
        ('CP',  WH_Tcontrol_CPC, WH_Tcontrol_CPdeadbandC, AC_Tcontrol_CPC, AC_Tcontrol_CPdeadbandC, HEAT_Tcontrol_CPC, HEAT_Tcontrol_CPdeadbandC),
        ('GE',  WH_Tcontrol_GEC, WH_Tcontrol_GEdeadbandC, AC_Tcontrol_GEC, AC_Tcontrol_GEdeadbandC, HEAT_Tcontrol_GEC, HEAT_Tcontrol_GEdeadbandC)
    ]

    def get_active_mode_for_delay(delay_td):
        for mode_data in modes:
            mode_name = mode_data[0]
            m_start, m_end = home_schedule_td[f'M_{mode_name}']
            if (midnight + m_start + delay_td) <= sim_time < (midnight + m_end + delay_td):
                return mode_data
            e_start, e_end = home_schedule_td[f'E_{mode_name}']
            if (midnight + e_start + delay_td) <= sim_time < (midnight + e_end + delay_td):
                return mode_data
        return None

    wh_mode = get_active_mode_for_delay(wh_delay)
    hvac_mode = get_active_mode_for_delay(hvac_delay)
    base_mode = get_active_mode_for_delay(pd.Timedelta(seconds=0))

    if WH_SIMULATION == "ON" and wh_mode:
        _, wh_sp, wh_db, _, _, _, _ = wh_mode
        ctrl_signal['Water Heating'].update({'Setpoint': wh_sp, 'Deadband': wh_db})

    if HVAC_SIMULATION == "ON" and hvac_mode:
        _, _, _, ac_sp, ac_db, heat_sp, heat_db = hvac_mode
        if is_cooling_season:
            ctrl_signal['HVAC Cooling'].update({'Setpoint': ac_sp, 'Deadband': ac_db})
        else:
            ctrl_signal['HVAC Heating'].update({'Setpoint': heat_sp, 'Deadband': heat_db})

    if EV_SIMULATION == "ON" and home_charger_kw is not None:
        ev_state = 'Normal'
        if base_mode:
            current_mode = base_mode[0]
            if current_mode == 'S': ev_state = 'Shed'
            elif current_mode == 'CP': ev_state = 'CP'
            elif current_mode == 'GE': ev_state = 'GE'

        fraction = EV_SHED_PCT if ev_state == 'Shed' else (EV_CP_PCT if ev_state == 'CP' else (EV_GE_PCT if ev_state == 'GE' else 1.0))
        commanded_kw = abs(fraction * home_charger_kw)
        ctrl_signal['EV'] = {'Max Power': max(commanded_kw, 0.001)}

    if BATTERY_SIMULATION == "ON":
        battery_state = base_mode[0] if base_mode else 'Normal'
        battery_p_map = {
            'ALU': P_Battery_ALU_KW,
            'LU': P_Battery_LU_KW,
            'S': P_Battery_SHED_KW,
            'CP': P_Battery_CP_KW,
            'GE': P_Battery_GE_KW
        }
        battery_p = battery_p_map.get(battery_state, P_Battery_IDLE_KW)
        ctrl_signal['Battery'] = {'P Setpoint': battery_p}

    return ctrl_signal

#########################################
# PREPARE SCHEDULES (1-MIN RESOLUTION)
#########################################

def prepare_schedules(home_path, sched_cfg, t_res_minutes=1):
    orig_sched_file = os.path.join(home_path, CSV_ADDRESS)
    base_sched_file = os.path.join(home_path, 'baseline_schedules.csv')
    ctrl_sched_file = os.path.join(home_path, 'controlled_schedules.csv')

    df_sched = pd.read_csv(orig_sched_file)
    valid_schedule_names = set(ALL_SCHEDULE_NAMES.keys())
    filtered_columns = [
        col for col in df_sched.columns 
        if col in valid_schedule_names or 'ev' in col.lower() or 'vehicle' in col.lower() or 'plug' in col.lower()
    ]
    if filtered_columns:
        df_sched = df_sched[filtered_columns].copy()

    df_sched.to_csv(base_sched_file, index=False)

    dryer_cols = [c for c in df_sched.columns if 'dryer' in c.lower()]
    if not dryer_cols:
        df_sched.to_csv(ctrl_sched_file, index=False)
        return base_sched_file, ctrl_sched_file

    dryer_col = dryer_cols[0]
    df_sched['Datetime'] = pd.date_range(start="2018-01-01 00:00:00", periods=len(df_sched), freq=f'{t_res_minutes}min')
    df_sched.set_index('Datetime', inplace=True)

    duty_cycles = np.ones(len(df_sched), dtype=float)
    time_of_day = df_sched.index - df_sched.index.normalize()

    curtailment_modes = {'S': dryer_duty_cycle_shed, 'CP': dryer_duty_cycle_cp, 'GE': dryer_duty_cycle_ge}
    for tod in ['M', 'E']:
        for mode, dc_value in curtailment_modes.items():
            key = f"{tod}_{mode}"
            if key in sched_cfg:
                start_td, end_td = sched_cfg[key]
                mask = (time_of_day >= start_td) & (time_of_day < end_td)
                duty_cycles[mask] = np.minimum(duty_cycles[mask], dc_value)

    in_shed = duty_cycles < 1.0
    orig_vals = df_sched[dryer_col].values
    new_vals = np.zeros_like(orig_vals, dtype=float)
    max_cap = orig_vals.max() if orig_vals.max() > 0 else 1.0
    work_queue = 0.0

    for i in range(len(orig_vals)):
        work_queue += orig_vals[i]
        if work_queue < 1e-6: work_queue = 0.0
        if work_queue > 0:
            if i > 0 and in_shed[i] != in_shed[i-1]:
                run_amt = 0.0
            else:
                allowed_rate = max_cap * duty_cycles[i]
                run_amt = min(work_queue, allowed_rate)
            new_vals[i] = run_amt
            work_queue -= run_amt

    df_sched[dryer_col] = new_vals
    df_sched.reset_index(drop=True, inplace=True)
    df_sched.to_csv(ctrl_sched_file, index=False)
    return base_sched_file, ctrl_sched_file

#########################################
# DATA WINDOW FILTERING (08:00 - 10:00 AM)
#########################################

def filter_8am_to_10am(df):
    """Filters results to keep only timestamps between 08:00 AM and 10:00 AM."""
    if 'Time' not in df.columns:
        df = df.reset_index()
        if 'index' in df.columns:
            df.rename(columns={'index': 'Time'}, inplace=True)

    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    times = df['Time'].dt.time
    mask = (times >= STUDY_START_TIME) & (times <= STUDY_END_TIME)
    return df[mask].copy()

#########################################
# SIMULATION FUNCTION
#########################################

def simulate_home(home_path, weather_file_path, schedule_cfg):
    base_sched_file, ctrl_sched_file = prepare_schedules(home_path, schedule_cfg, t_res)
    hpxml_file = os.path.join(home_path, XML_ADDRESS)
    results_dir = os.path.join(home_path, "Results")
    os.makedirs(results_dir, exist_ok=True)

    equipment = {}
    if WH_SIMULATION == "ON":
        equipment["Water Heating"] = {
            "Initial Temperature (C)": WH_TinitC,
            "hp_only_mode": True,
            "Max Tank Temperature": 70,
            "Upper Node": 3,
            "Lower Node": 10,
            "Upper Node Weight": 0.75,
        }

    if BATTERY_SIMULATION == "ON":
        equipment["Battery"] = BATTERY_PARAMS

    home_charger_kw = None
    if EV_SIMULATION == "ON":
        home_charger_kw = get_ev_charger_power(hpxml_file, DEFAULT_CHARGER_POWER_KW)
        home_ev_capacity = get_ev_capacity_or_range(hpxml_file, DEFAULT_CAPACITY_KWH)
        home_charger = "Level 2" if home_charger_kw > 8 else "Level 1"
        equipment["EV"] = {
            "vehicle_type": "BEV",
            "capacity": home_ev_capacity,
            "charging_level": home_charger,
            "max_power": home_charger_kw
        }

    home_name = os.path.basename(home_path)
    home_num_str = re.sub(r'\D', '', home_name)
    home_seed = int(home_num_str) if home_num_str else 0

    dwelling_args_local = {
        "start_time": Start,
        "time_res": dt.timedelta(minutes=t_res),
        "duration": Duration,
        "hpxml_file": hpxml_file,
        "weather_file": weather_file_path,
        "verbosity": 7,
        "seed": home_seed,
        "Equipment": equipment
    }

    # Baseline Simulation
    random.seed(home_seed)
    np.random.seed(home_seed)
    base_dwelling = Dwelling(name="Home Baseline", hpxml_schedule_file=base_sched_file, **copy.deepcopy(dwelling_args_local))
    
    for t_base in base_dwelling.sim_times:
        base_ctrl = {}
        if WH_SIMULATION == "ON":
            base_ctrl["Water Heating"] = {"Setpoint": WH_TbaselineC, "Deadband": WH_TdeadbandC, "Load Fraction": 1}
        if HVAC_SIMULATION == "ON":
            base_ctrl["HVAC Cooling"] = {"Setpoint": AC_TbaselineC, "Deadband": AC_TdeadbandC, "Load Fraction": 1}
            base_ctrl["HVAC Heating"] = {"Setpoint": HEAT_TbaselineC, "Deadband": HEAT_TdeadbandC, "Load Fraction": 1}
        if EV_SIMULATION == "ON" and home_charger_kw is not None:
            base_ctrl["EV"] = {"Max Power": home_charger_kw}
        base_dwelling.update(control_signal=base_ctrl)
    df_base, _, _ = base_dwelling.finalize()

    # Delays
    wh_delay = pd.Timedelta(seconds=random.uniform(WH_RESPONSE_MIN, WH_RESPONSE_MAX))
    hvac_delay = pd.Timedelta(seconds=random.uniform(HVAC_RESPONSE_MIN, HVAC_RESPONSE_MAX))

    # Controlled Simulation
    random.seed(home_seed)
    np.random.seed(home_seed)
    sim_dwelling = Dwelling(name="Home Controlled", hpxml_schedule_file=ctrl_sched_file, **copy.deepcopy(dwelling_args_local))
    
    hpwh_unit = sim_dwelling.get_equipment_by_end_use('Water Heating') if WH_SIMULATION == "ON" else None

    for sim_time in sim_dwelling.sim_times:
        current_setpt = WH_TinitC
        if hpwh_unit is not None:
            current_setpt = hpwh_unit.schedule.loc[sim_time, 'Water Heating Setpoint (C)']

        control_cmd = determine_control(
            sim_time=sim_time,
            current_temp_c=current_setpt,
            home_schedule_td=schedule_cfg,
            home_charger_kw=home_charger_kw,
            wh_delay=wh_delay,
            hvac_delay=hvac_delay
        )
        sim_dwelling.update(control_signal=control_cmd) if control_cmd else sim_dwelling.update()

    df_ctrl, _, _ = sim_dwelling.finalize()

    # Filter to 08:00 - 10:00 study window
    df_ctrl = filter_8am_to_10am(df_ctrl)
    df_base = filter_8am_to_10am(df_base)

    CTRL_COLS = ["Time", "Total Electric Power (kW)", "Total Electric Energy (kWh)"]
    if WH_SIMULATION == "ON": CTRL_COLS.append("Water Heating Electric Power (kW)")
    if HVAC_SIMULATION == "ON": CTRL_COLS.extend(["HVAC Heating Electric Power (kW)", "HVAC Cooling Electric Power (kW)"])
    if DRYER_SIMULATION == "ON": CTRL_COLS.append("Clothes Dryer Electric Power (kW)")
    if EV_SIMULATION == "ON": CTRL_COLS.extend(["EV Electric Power (kW)", "EV SOC (-)"])
    if BATTERY_SIMULATION == "ON": CTRL_COLS.extend(["Battery Electric Power (kW)", "Battery SOC (-)"])

    df_ctrl = df_ctrl[[c for c in CTRL_COLS if c in df_ctrl.columns]]
    df_base = df_base[[c for c in CTRL_COLS if c in df_base.columns]]

    df_ctrl.to_csv(os.path.join(results_dir, 'home_controlled.csv'), index=False)
    df_base.to_csv(os.path.join(results_dir, 'home_baseline.csv'), index=False)

    return df_ctrl, df_base

def find_all_homes(base_dir):
    homes = []
    for item in os.listdir(base_dir):
        home_path = os.path.join(base_dir, item)
        if os.path.isdir(home_path) and os.path.isfile(os.path.join(home_path, XML_ADDRESS)) and os.path.isfile(os.path.join(home_path, CSV_ADDRESS)):
            homes.append(home_path)
    return homes

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
        pd.concat(all_ctrl, ignore_index=True).to_csv(os.path.join(work_dir, filename + "_controlled.csv"), index=False)
    if all_base:
        pd.concat(all_base, ignore_index=True).to_csv(os.path.join(work_dir, filename + "_baseline.csv"), index=False)

#########################################
# C1 INTEGRATION: DATA PARSING
#########################################

def process_c1_data(input_file, output_file, wanted_col):
    if not os.path.exists(input_file):
        return
    df = pd.read_csv(input_file).dropna(axis=0)
    df['time'] = pd.to_datetime(df['Time'], errors='coerce')
    df['hr_min'] = df['time'].dt.strftime('%H:%M')

    df_pivot = df.pivot_table(index='Home', columns='hr_min', values=wanted_col)
    df_pivot.to_csv(output_file, index=True)

def run_c1_parsing():
    input_file_base = os.path.join(WORKING_DIR, filename + "_baseline.csv")
    input_file_ctrl = os.path.join(WORKING_DIR, filename + "_controlled.csv")
    folder_path = os.path.join(WORKING_DIR, "Ready_data", filename)
    os.makedirs(folder_path, exist_ok=True)

    mappings = []
    if WH_SIMULATION == "ON":
        mappings.append(('Water Heating Electric Power (kW)', '_WH_power.csv'))
    if HVAC_SIMULATION == "ON":
        mappings.append(('HVAC Cooling Electric Power (kW)', '_AC_power.csv'))
        mappings.append(('HVAC Heating Electric Power (kW)', '_HEAT_power.csv'))
    if DRYER_SIMULATION == "ON":
        mappings.append(('Clothes Dryer Electric Power (kW)', '_Dryer_power.csv'))
    if EV_SIMULATION == "ON":
        mappings.append(('EV Electric Power (kW)', '_EV_power.csv'))
        mappings.append(('EV SOC (-)', '_EV_SOC.csv'))
    if BATTERY_SIMULATION == "ON":
        mappings.append(('Battery Electric Power (kW)', '_BATT_power.csv'))
        mappings.append(('Battery SOC (-)', '_BATT_SOC.csv'))

    mappings.append(('Total Electric Power (kW)', '_total_power.csv'))

    for col, suffix in mappings:
        out_base = os.path.join(folder_path, filename + "_baseline" + suffix)
        out_ctrl = os.path.join(folder_path, filename + "_controlled" + suffix)
        process_c1_data(input_file_base, out_base, col)
        process_c1_data(input_file_ctrl, out_ctrl, col)

#########################################
# C2 INTEGRATION: PLOTTING (08:00 - 10:00)
#########################################

def save_avg(file_path):
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        averages = df.mean(numeric_only=True)
        df.loc['Average'] = averages
        df.to_csv(file_path, index=False)

def get_active_commands():
    commands = []
    for cmd_key, times in my_schedule1.items():
        if 'rampin_start' in cmd_key:
            cmd_name = cmd_key.replace('_rampin_start', '')
            t0 = pd.to_datetime(my_schedule1[f"{cmd_name}_rampin_start"], format='%H:%M')
            t1 = pd.to_datetime(my_schedule1[f"{cmd_name}_rampin_end"], format='%H:%M')
            t2 = pd.to_datetime(my_schedule1[f"{cmd_name}_rampout_start"], format='%H:%M')
            t3 = pd.to_datetime(my_schedule1[f"{cmd_name}_rampout_end"], format='%H:%M')

            if 'ALU' in cmd_name: c_type, color = 'Advanced Load Up', "#00FF087C"
            elif 'LU' in cmd_name: c_type, color = 'Load Up', "#0077FF85"
            elif 'CP' in cmd_name: c_type, color = 'Critical Peak', "#FF660083"
            elif 'GE' in cmd_name: c_type, color = 'Grid Emergency', "#FF00008F"
            elif 'S' in cmd_name: c_type, color = 'Shed', "#FF00DD8D"
            else: c_type, color = 'Other', '#9E9E9E'

            commands.append({'type': c_type, 'color': color, 'times': [t0, t1, t2, t3]})
    return commands

def plot_data(baseline_file, controlled_file, title, photo_file, schedule_commands):
    if not (os.path.exists(baseline_file) and os.path.exists(controlled_file)):
        return

    df_base = pd.read_csv(baseline_file, index_col=0)
    df_con = pd.read_csv(controlled_file, index_col=0)

    # Calculate the number of homes (total rows minus the 'Average' row)
    num_homes = len(df_base) - 1

    df_base = pd.DataFrame(df_base.iloc[[0, -1]].iloc[1, :]).reset_index()
    df_con = pd.DataFrame(df_con.iloc[[0, -1]].iloc[1, :]).reset_index()

    df_base.columns = ['Time', 'baseline']
    df_con.columns = ['Time', 'controlled']

    df_base['Time'] = pd.to_datetime(df_base['Time'], format='%H:%M', errors='coerce')
    df_con['Time'] = pd.to_datetime(df_con['Time'], format='%H:%M', errors='coerce')

    fig, ax1 = plt.subplots(figsize=(9, 6))

    ax1.plot(df_base['Time'], df_base['baseline'], label='Baseline', color='#004C6D', linewidth=2)
    ax1.plot(df_con['Time'], df_con['controlled'], label='Controlled', color='#E26D28', linewidth=2)
    ax1.set_ylabel('Power (kW)')
    ax1.set_title(f"{title} (n={num_homes})")
    ax1.grid(True, alpha=0.3)

    # Lock x-axis strictly to 08:00 - 10:00 with 15-minute intervals
    t_start = pd.to_datetime('08:00', format='%H:%M')
    t_end = pd.to_datetime('09:00', format='%H:%M')
    ax1.set_xlim(t_start, t_end)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.MinuteLocator(interval=15))
    plt.setp(ax1.get_xticklabels(), rotation=45)

    ax2 = ax1.twinx()
    ax2.set_ylabel('Fraction of units given command')
    ax2.set_ylim(0, 1)

    added_labels = set()
    for cmd in schedule_commands:
        y_vals = [0, 1, 1, 0]
        label = cmd['type'] if cmd['type'] not in added_labels else ""
        if label: added_labels.add(label)
        ax2.plot(cmd['times'], y_vals, color=cmd['color'], linewidth=1)
        ax2.fill_between(cmd['times'], y_vals, color=cmd['color'], alpha=0.1, label=label)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=4, frameon=False)

    plt.tight_layout()
    plt.savefig(photo_file, dpi=300, bbox_inches='tight')
    plt.close()

def plot_combined_controlled_loads(folder_path, schedule_commands, photo_file):
    """Plots controlled WH, HVAC (AC/HEAT), and Battery power consumption on the same axes."""
    fig, ax1 = plt.subplots(figsize=(9, 6))
    
    device_configs = [
        ('Water Heating', '_WH_power.csv', "#A31401"),
        ('HVAC Cooling', '_AC_power.csv', "#00ACAC"),
        ('Battery', '_BATT_power.csv', '#EDAE49')
    ]
    
    has_data = False
    num_homes = None
    for label, suffix, color in device_configs:
        ctrl_f = os.path.join(folder_path, filename + "_controlled" + suffix)
        if os.path.exists(ctrl_f):
            df_con = pd.read_csv(ctrl_f, index_col=0)
            if not df_con.empty:
                if num_homes is None:
                    num_homes = len(df_con) - 1
                avg_series = df_con.iloc[-1]
                df_plot = pd.DataFrame(avg_series).reset_index()
                df_plot.columns = ['Time', 'Power']
                df_plot['Time'] = pd.to_datetime(df_plot['Time'], format='%H:%M', errors='coerce')
                
                ax1.plot(df_plot['Time'], df_plot['Power'], label=f'{label} (Controlled)', color=color, linewidth=2)
                has_data = True

    if not has_data:
        plt.close()
        return

    ax1.set_ylabel('Power (kW)')
    title_text = 'Controlled Power Consumption: WH, HVAC & Battery'
    if num_homes is not None:
        title_text += f' (n={num_homes})'
    ax1.set_title(title_text)
    ax1.grid(True, alpha=0.3)

    # Lock x-axis strictly to 08:00 - 10:00 with 15-minute intervals
    t_start = pd.to_datetime('08:00', format='%H:%M')
    t_end = pd.to_datetime('09:00', format='%H:%M')
    ax1.set_xlim(t_start, t_end)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.MinuteLocator(interval=15))
    plt.setp(ax1.get_xticklabels(), rotation=45)

    ax2 = ax1.twinx()
    ax2.set_ylabel('Fraction of units given command')
    ax2.set_ylim(0, 1)

    added_labels = set()
    for cmd in schedule_commands:
        y_vals = [0, 1, 1, 0]
        label = cmd['type'] if cmd['type'] not in added_labels else ""
        if label: added_labels.add(label)
        ax2.plot(cmd['times'], y_vals, color=cmd['color'], linewidth=1)
        ax2.fill_between(cmd['times'], y_vals, color=cmd['color'], alpha=0.1, label=label)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=4, frameon=False)

    plt.tight_layout()
    plt.savefig(photo_file, dpi=300, bbox_inches='tight')
    plt.close()

def run_c2_plotting():
    folder_path = os.path.join(WORKING_DIR, "Ready_data", filename)
    active_commands = get_active_commands()

    plots = []
    if WH_SIMULATION == "ON": plots.append(('_WH_power.csv', 'Average Power Consumption per Water Heater', '_WH_plot.png'))
    if HVAC_SIMULATION == "ON":
        plots.append(('_AC_power.csv', 'Average Power Consumption per AC System', '_AC_plot.png'))
        plots.append(('_HEAT_power.csv', 'Average Power Consumption per Heating System', '_HEAT_plot.png'))
    if DRYER_SIMULATION == "ON": plots.append(('_Dryer_power.csv', 'Average Power Consumption per Dryer', '_Dryer_plot.png'))
    if EV_SIMULATION == "ON":
        plots.append(('_EV_power.csv', 'Average Power Consumption per EV', '_EV_plot.png'))
        plots.append(('_EV_SOC.csv', 'Average State of Charge per EV', '_EV_SOC_plot.png'))
    if BATTERY_SIMULATION == "ON":
        plots.append(('_BATT_power.csv', 'Average Power Consumption per Battery', '_BATT_plot.png'))
        plots.append(('_BATT_SOC.csv', 'Average State of Charge per Battery', '_BATT_SOC_plot.png'))

    plots.append(('_total_power.csv', 'Average Total Power Consumption per Household', '_total_plot.png'))

    for suffix, title, img_suffix in plots:
        base_f = os.path.join(folder_path, filename + "_baseline" + suffix)
        ctrl_f = os.path.join(folder_path, filename + "_controlled" + suffix)
        img_f = os.path.join(folder_path, filename + img_suffix)

        save_avg(base_f)
        save_avg(ctrl_f)
        plot_data(base_f, ctrl_f, title, img_f, active_commands)

    # Generate multi-device controlled plot for WH, HVAC, and Battery
    comb_img_f = os.path.join(folder_path, filename + "_controlled_WH_HVAC_Battery_plot.png")
    plot_combined_controlled_loads(folder_path, active_commands, comb_img_f)

#########################################
# MAIN EXECUTION FLOW
#########################################

if __name__ == "__main__":
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(WEATHER_DIR, exist_ok=True)

    # Setup directories
    for item in os.listdir(DEFAULT_INPUT):
        src = os.path.join(DEFAULT_INPUT, item)
        dst = os.path.join(INPUT_DIR, item)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)

    if not os.path.exists(WEATHER_FILE):
        shutil.copy(DEFAULT_WEATHER, WEATHER_FILE)

    homes = find_all_homes(INPUT_DIR)

    # Check ON/OFF switch for simulation
    if RUN_SIMULATION:
        print(f"Found {len(homes)} homes. Running 1-minute simulation from 00:00 to 10:00...")
        with concurrent.futures.ProcessPoolExecutor(max_workers=8) as executor:
            futures = []
            for home in homes:
                home_basename = os.path.basename(home)
                home_num_str = re.sub(r'\D', '', home_basename)
                home_num = int(home_num_str) if home_num_str else 0
                
                home_sched_td = create_home_schedule(my_schedule1, bins=bins, home_idx=home_num)
                futures.append(executor.submit(simulate_home, home, WEATHER_FILE, home_sched_td))

            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    print("Simulation error:", e)

        print("Simulations complete. Aggregating raw datasets...")
        aggregate_results(homes, WORKING_DIR)
        print("Parsing data into 1-minute pivoted CSVs (C1)...")
        run_c1_parsing()
    else:
        print("[INFO] RUN_SIMULATION is False. Skipping simulation step.")
        # Re-parse existing raw CSVs into pivoted format if present
        if os.path.exists(os.path.join(WORKING_DIR, filename + "_controlled.csv")):
            print("Re-parsing existing dataset into pivoted CSVs (C1)...")
            run_c1_parsing()

    print("Generating plots for 08:00 AM to 10:00 AM (C2)...")
    run_c2_plotting()

    print("Pipeline complete! Visualizations and parsed CSVs saved to:", os.path.join(WORKING_DIR, "Ready_data", filename))