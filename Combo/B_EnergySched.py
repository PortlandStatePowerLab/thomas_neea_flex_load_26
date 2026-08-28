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

filename = 'Combo_WH_ALUGECP_test_5'

Input_folder = "HPWH All Input Files"

# Original OCHRE defaults folder
ochre_dir = Path(ochre.__file__).resolve().parent
DEFAULT_INPUT = ochre_dir / "defaults" / "Input Files"
print("OCHRE installed at:", ochre_dir)
print(DEFAULT_INPUT)

DEFAULT_WEATHER = ochre_dir / "defaults" / "Weather" / "USA_OR_Portland.Intl.AP.726980_TMY3.epw"
# G4100510 is Multnomah county weather station, code will complain this is missing but it doesn't work if you actually try to use it

# working folder
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

WH_SIMULATION = "ON"
HVAC_SIMULATION = "ON"
DRYER_SIMULATION = "ON"
EV_SIMULATION = "ON"
BATTERY_SIMULATION = "ON"


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
WH_Tinit = 130

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


# Schedule variant
my_schedule1 = {
    'M_ALU_rampin_start':  '06:30', 'M_ALU_rampin_end':  '06:30',
    'M_ALU_rampout_start': '06:30', 'M_ALU_rampout_end': '06:30',

    'M_LU_rampin_start':   '04:00', 'M_LU_rampin_end':   '04:00',
    'M_LU_rampout_start':  '06:00', 'M_LU_rampout_end':  '06:00',

    'M_S_rampin_start':    '07:00', 'M_S_rampin_end':    '07:00',
    'M_S_rampout_start':   '09:00', 'M_S_rampout_end':   '09:00',

    'M_CP_rampin_start':   '07:30', 'M_CP_rampin_end':   '07:30',
    'M_CP_rampout_start':  '07:30', 'M_CP_rampout_end':  '07:30',

    'M_GE_rampin_start':   '07:30', 'M_GE_rampin_end':   '07:30',
    'M_GE_rampout_start':  '07:30', 'M_GE_rampout_end':  '07:30',

    'E_ALU_rampin_start':  '10:00', 'E_ALU_rampin_end':  '10:00',
    'E_ALU_rampout_start': '12:00', 'E_ALU_rampout_end': '12:00',

    'E_LU_rampin_start':   '15:00', 'E_LU_rampin_end':   '15:00',
    'E_LU_rampout_start':  '15:00', 'E_LU_rampout_end':  '15:00',

    'E_S_rampin_start':    '17:00', 'E_S_rampin_end':    '17:00',
    'E_S_rampout_start':   '17:00', 'E_S_rampout_end':   '17:00',

    'E_CP_rampin_start':   '13:00', 'E_CP_rampin_end':   '13:00',
    'E_CP_rampout_start':  '16:00', 'E_CP_rampout_end':  '16:00',

    'E_GE_rampin_start':   '18:00', 'E_GE_rampin_end':   '18:00',
    'E_GE_rampout_start':  '22:00', 'E_GE_rampout_end':  '22:00',
}

def shift_time(time_str, minutes):
    """Helper function to add minutes to an 'HH:MM' string."""
    delta_t = dt.datetime.strptime(time_str, '%H:%M')
    new_delta_t = delta_t + dt.timedelta(minutes=minutes)
    return new_delta_t.strftime('%H:%M')

bins = 17

#########################################
# STAGGER SCHEDULES FOR RAMPING
#########################################

def create_home_schedule(base_sched, bins, home_idx):
    """
    Calculates staggered start/end timedeltas for a specific home 
    distributed across the defined ramp-in and ramp-out periods.
    """
    bin_idx = home_idx % bins
    
    # Calculate the fraction of the ramp duration this bin represents.
    # We use (bins - 1) so that the first bin is at the exact start (0.0), 
    # and the last bin is at the exact end (1.0) of the ramp period.
    ramp_fraction = (bin_idx / (bins - 1)) if bins > 1 else 0

    def parse_time(time_str):
        t = dt.datetime.strptime(time_str, '%H:%M')
        return pd.Timedelta(hours=t.hour, minutes=t.minute)

    home_schedule = {}
    
    # Process all combinations of Time-of-Day (M/E) and Modes
    times_of_day = ['M', 'E']
    modes = ['ALU', 'LU', 'S', 'CP', 'GE']

    for tod in times_of_day:
        for mode in modes:
            prefix = f"{tod}_{mode}" # e.g. "M_ALU"
            
            # --- RAMP IN (Start of command) ---
            rin_start_str = base_sched.get(f"{prefix}_rampin_start", "00:00")
            rin_end_str = base_sched.get(f"{prefix}_rampin_end", rin_start_str)
            
            rin_start_td = parse_time(rin_start_str)
            rin_end_td = parse_time(rin_end_str)
            rin_duration = rin_end_td - rin_start_td
            
            # Interpolate ramp-in time based on bin position
            home_start_td = rin_start_td + (rin_duration * ramp_fraction)

            # --- RAMP OUT (End of command) ---
            rout_start_str = base_sched.get(f"{prefix}_rampout_start", "00:00")
            rout_end_str = base_sched.get(f"{prefix}_rampout_end", rout_start_str)
            
            rout_start_td = parse_time(rout_start_str)
            rout_end_td = parse_time(rout_end_str)
            rout_duration = rout_end_td - rout_start_td
            
            # Interpolate ramp-out time based on bin position
            home_end_td = rout_start_td + (rout_duration * ramp_fraction)

            home_schedule[prefix] = (home_start_td, home_end_td)

    print(home_idx)
    print(bin_idx)
    print(home_schedule)
    return home_schedule


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
# CONTROL FUNCTION
#########################################

def determine_control(sim_time, current_temp_c, home_schedule_td, **kwargs):
    # 1. Initialize an empty control signal dictionary
    ctrl_signal = {}

    # 2. Add Water Heating if simulated
    if WH_SIMULATION == "ON":
        ctrl_signal['Water Heating'] = {
            'Setpoint': WH_TbaselineC,
            'Deadband': WH_TdeadbandC,
            'Load Fraction': 1,
        }

    # 3. Add HVAC if simulated, checking the month to separate Heating vs Cooling
    # Let's assume May (5) through Sept (9) is Cooling Season
    is_cooling_season = sim_time.month in [5, 6, 7, 8, 9]

    if HVAC_SIMULATION == "ON":
        if is_cooling_season:
            ctrl_signal['HVAC Cooling'] = {
                'Setpoint': AC_TbaselineC,
                'Deadband': AC_TdeadbandC,
                'Load Fraction': 1,
            }
        else:
            ctrl_signal['HVAC Heating'] = {
                'Setpoint': HEAT_TbaselineC,
                'Deadband': HEAT_TdeadbandC,
                'Load Fraction': 1,
            }

    midnight = pd.to_datetime(sim_time.date())

    # 4. Define modes in priority order: 
    # (Mode Name, WH_SP, WH_DB, AC_SP, AC_DB, HEAT_SP, HEAT_DB)
    modes = [
        ('ALU', WH_Tcontrol_ALUC, WH_Tcontrol_ALUdeadbandC, AC_Tcontrol_ALUC, AC_Tcontrol_ALUdeadbandC, HEAT_Tcontrol_ALUC, HEAT_Tcontrol_ALUdeadbandC),
        ('LU',  WH_Tcontrol_LOADC, WH_Tcontrol_LOADdeadbandC, AC_Tcontrol_LOADC, AC_Tcontrol_LOADdeadbandC, HEAT_Tcontrol_LOADC, HEAT_Tcontrol_LOADdeadbandC),
        ('S',   WH_Tcontrol_SHEDC, WH_Tcontrol_deadbandC, AC_Tcontrol_SHEDC, AC_Tcontrol_deadbandC, HEAT_Tcontrol_SHEDC, HEAT_Tcontrol_deadbandC),
        ('CP',  WH_Tcontrol_CPC, WH_Tcontrol_CPdeadbandC, AC_Tcontrol_CPC, AC_Tcontrol_CPdeadbandC, HEAT_Tcontrol_CPC, HEAT_Tcontrol_CPdeadbandC),
        ('GE',  WH_Tcontrol_GEC, WH_Tcontrol_GEdeadbandC, AC_Tcontrol_GEC, AC_Tcontrol_GEdeadbandC, HEAT_Tcontrol_GEC, HEAT_Tcontrol_GEdeadbandC)
    ]

    active_mode = None

    # 5. Check schedules to see if a mode is currently active
    for mode_data in modes:
        mode_name = mode_data[0]
        
        # Check Morning
        m_start, m_end = home_schedule_td[f'M_{mode_name}']
        if (midnight + m_start) <= sim_time < (midnight + m_end):
            active_mode = mode_data
            break

        # Check Evening
        e_start, e_end = home_schedule_td[f'E_{mode_name}']
        if (midnight + e_start) <= sim_time < (midnight + e_end):
            active_mode = mode_data
            break

    # 6. If a mode is active, apply its setpoints to the simulated devices
    if active_mode:
        _, wh_sp, wh_db, ac_sp, ac_db, heat_sp, heat_db = active_mode
        
        if WH_SIMULATION == "ON":
            ctrl_signal['Water Heating'].update({'Setpoint': wh_sp, 'Deadband': wh_db})
            
        if HVAC_SIMULATION == "ON":
            if is_cooling_season:
                ctrl_signal['HVAC Cooling'].update({'Setpoint': ac_sp, 'Deadband': ac_db})
            else:
                ctrl_signal['HVAC Heating'].update({'Setpoint': heat_sp, 'Deadband': heat_db})

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

    equipment = []

    if WH_SIMULATION == "ON":
        equipment["Water Heating"] = {
                "Initial Temperature (C)": WH_TinitC, 
                "hp_only_mode": True,
                "Max Tank Temperature": 70,
                "Upper Node": 3,
                "Lower Node": 10,
                "Upper Node Weight": 0.75,
        }



    dwelling_args_local = {
        "start_time": Start,
        "time_res": dt.timedelta(minutes=t_res),
        "duration": dt.timedelta(days=Duration),
        "hpxml_file": hpxml_file,
        "hpxml_schedule_file": filtered_sched_file,
        "weather_file": weather_file_path,
        "verbosity": 7,
        #"initialization_time": 1,
        "Equipment": equipment
    }

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
        control_cmd = determine_control(sim_time=sim_time, current_temp_c=current_setpt, home_schedule_td=schedule_cfg)
        sim_dwelling.update(control_signal=control_cmd)
    df_ctrl, _, _ = sim_dwelling.finalize()

    df_ctrl = remove_first_day(df_ctrl, Start)
    df_base = remove_first_day(df_base, Start)
    
    CTRL_COLS = ["Time", "Total Electric Power (kW)",
                 "Total Electric Energy (kWh)",
                 "Water Heating Electric Power (kW)"]
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

    # Parallel simulations
    # $ grep -rn "read_psm3(" .
    # ./ochre/utils/schedule.py:186:        df, location = pvlib.iotools.read_psm3(weather_file, map_variables=True)
    # Change to read_nsrdb_psm4 
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for home in homes:
            # Extract digits from the home folder name to use as a unique ID
            home_basename = os.path.basename(home)
            home_num = sum(int(c) for c in home_basename if c.isdigit())
            
            # Generate the exact shifted timedeltas for THIS specific home
            home_sched_td = create_home_schedule(my_schedule1, bins=bins, home_idx=home_num)
            
            # Submit to the thread pool
            futures.append(executor.submit(simulate_home, home, WEATHER_FILE, home_sched_td))

        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()  # forces execution and raises exceptions if any
            except Exception as e:
                print("Simulation failed:", e)

    print("All simulations complete!")


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

aggregate_results(homes, WORKING_DIR)