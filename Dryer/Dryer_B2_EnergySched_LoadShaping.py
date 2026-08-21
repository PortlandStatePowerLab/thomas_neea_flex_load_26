"""
Author: Thomas Metzler
Created: 8/19/26

Adjusts load up and shed commands to keep dryer fleet power consumption at a constant level.
Modified to account for dryer constraints (managing load via SHED and NORMAL restoration only).
Runs the baseline and calculates the number of homes to shed, then adjusts schedule and runs controlled.
Schedules can not be adjusted dynamically, and dryers can only be controlled through schedules.
Only sends sheds to active dryers. 
"""

import os
import shutil
import datetime as dt
import pandas as pd
import numpy as np
from ochre import Dwelling
from ochre.utils.schedule import ALL_SCHEDULE_NAMES
import concurrent.futures
from pathlib import Path
import ochre
import random

#########################################
# USER SETTINGS
#########################################

filename = 'Dryer_test_Loadshape_10'
Input_folder = "Dryer Input Files 2"

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
Start = dt.datetime(2018, 1, 11, 0, 0)
Duration = 2  # days
t_res = 15  # minutes

# --- GLOBAL VPP EVENT SETTINGS ---
VPP_START_TIME = dt.time(12, 0)
VPP_END_TIME = dt.time(23, 0)

# Fleet-agnostic average power targets
AVERAGE_SETPOINT_KW = 1.5     
AVERAGE_DEADBAND_KW = 0.1     
ESTIMATED_SHED_KW = 1.5  

# Duty cycle power fraction during SHED mode (e.g., 0.5 = 50% power)
DUTY_CYCLE_FRACTION = 0.5

# --- PID CONTROLLER GAINS ---
KP = 1.0                      
KI = 0.8                      
KD = 1.0                      

#########################################
# HELPER FUNCTIONS
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
        ctrl_file = os.path.join(results_dir, "dryer_controlled.csv")
        base_file = os.path.join(results_dir, "dryer_baseline.csv")
        
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
    print("Aggregated CSVs written!")

#########################################
# PASS 1: PYTHON VPP PRE-SIMULATION
#########################################

def pre_process_schedules(homes):
    """
    Simulates the entire year purely in Pandas to calculate the PID logic, 
    delay events with 0-timesteps, apply the duty cycle, and shift energy.
    """
    print(f"--- PASS 1: Pre-processing Schedules for {len(homes)} homes ---")
    fleet_data = []
    
    # Load all homes into memory
    for home in homes:
        orig_sched_file = os.path.join(home, CSV_ADDRESS)
        df = pd.read_csv(orig_sched_file)
        
        dryer_cols = [c for c in df.columns if 'dryer' in c.lower()]
        dryer_col = dryer_cols[0] if dryer_cols else None
        
        if dryer_col:
            orig_vals = df[dryer_col].values
            max_cap = orig_vals.max() if orig_vals.max() > 0 else 1.0
        else:
            orig_vals = np.zeros(len(df))
            max_cap = 1.0
            
        fleet_data.append({
            "path": home,
            "df": df,
            "dryer_col": dryer_col,
            "orig_vals": orig_vals,
            "new_vals": [],
            "max_cap": max_cap,
            "mode": "NORMAL",
            "pending_off": False,
            "work_queue": 0.0
        })

    # Generate the time series using the simulation parameters to match OCHRE exactly
    time_series = pd.date_range(
        start=Start, 
        periods=len(fleet_data[0]["df"]), 
        freq=pd.Timedelta(minutes=t_res)
    )
    
    average_power_kw = 0.0
    integral_error = 0.0
    previous_error = 0.0
    num_homes = len(fleet_data)
    vpp_state_log = []
    
    # Run the Python Time Loop
    for idx, current_time in enumerate(time_series):
        current_time_of_day = current_time.time()
        is_vpp_active = VPP_START_TIME <= current_time_of_day < VPP_END_TIME
        
        # 1. Update Energy Queues
        for h in fleet_data:
            val = h["orig_vals"][idx]
            if h["max_cap"] > 0 and val > 0:
                h["work_queue"] += (val / h["max_cap"])
                
        # 2. VPP / PID Logic
        if is_vpp_active:
            error = AVERAGE_SETPOINT_KW - average_power_kw
            integral_error += error
            derivative_error = error - previous_error
            previous_error = error
            
            pid_output = (KP * error) + (KI * integral_error) + (KD * derivative_error)
            
            if pid_output < -AVERAGE_DEADBAND_KW:
                total_kw_to_drop = abs(pid_output) * num_homes
                
                # REQUIREMENT MET: Only target active dryers
                active_normal_homes = [
                    h for h in fleet_data 
                    if h["mode"] == "NORMAL" and h["work_queue"] > 1e-4
                ]
                random.shuffle(active_normal_homes)
                
                units_to_shed = int(total_kw_to_drop / ESTIMATED_SHED_KW)
                shed_applied = min(units_to_shed, len(active_normal_homes))
                
                for h in active_normal_homes[:shed_applied]:
                    h["mode"] = "SHED"
                    h["pending_off"] = True  # REQUIREMENT MET: 1-step OFF transition
                    
            elif pid_output > AVERAGE_DEADBAND_KW:
                total_kw_to_add = pid_output * num_homes
                shed_homes = [h for h in fleet_data if h["mode"] == "SHED"]
                random.shuffle(shed_homes)
                
                units_to_restore = int(total_kw_to_add / ESTIMATED_SHED_KW)
                restored_applied = min(units_to_restore, len(shed_homes))
                
                for h in shed_homes[:restored_applied]:
                    h["mode"] = "NORMAL"
                    h["pending_off"] = True  # REQUIREMENT MET: 1-step OFF transition
        else:
            for h in fleet_data:
                if h["mode"] == "SHED":
                    h["mode"] = "NORMAL"
                    h["pending_off"] = True
            integral_error = 0.0
            previous_error = 0.0
            
        # 3. Dispense Energy & Build New Schedule Array
        current_step_aggregate = 0.0
        for h in fleet_data:
            if h["pending_off"]:
                dispense = 0.0
                h["pending_off"] = False
            elif h["work_queue"] > 1e-4:
                if h["mode"] == "SHED":
                    dispense = min(DUTY_CYCLE_FRACTION, h["work_queue"])
                else:
                    dispense = min(1.0, h["work_queue"])
                h["work_queue"] = max(0.0, h["work_queue"] - dispense)
            else:
                dispense = 0.0
                h["work_queue"] = 0.0
                
            val_kw = dispense * h["max_cap"]
            h["new_vals"].append(val_kw)
            current_step_aggregate += val_kw
            
        average_power_kw = current_step_aggregate / num_homes
        
        vpp_state_log.append({
            "Time": current_time,
            "Target Average Power (kW)": AVERAGE_SETPOINT_KW if is_vpp_active else "OFF",
            "Actual Average Power (kW)": average_power_kw,
            "Aggregate Power (kW)": current_step_aggregate,
            "Units in NORMAL": sum(1 for h in fleet_data if h["mode"] == "NORMAL"),
            "Units in SHED": sum(1 for h in fleet_data if h["mode"] == "SHED")
        })

    # 4. Save Finalized Schedules
    valid_schedule_names = set(ALL_SCHEDULE_NAMES.keys())
    for h in fleet_data:
        df = h["df"]
        filtered_cols = [col for col in df.columns if col in valid_schedule_names or col == 'Time']
        
        # Base schedule (Unmodified)
        df_base = df[filtered_cols].copy()
        df_base.to_csv(os.path.join(h["path"], 'filtered_schedules_base.csv'), index=False)
        
        # Control schedule (Dynamically Shifted)
        df_ctrl = df[filtered_cols].copy()
        if h["dryer_col"]:
            df_ctrl[h["dryer_col"]] = h["new_vals"]
        df_ctrl.to_csv(os.path.join(h["path"], 'filtered_schedules_ctrl.csv'), index=False)
        
        # Verification File
        results_dir = os.path.join(h["path"], "Results")
        os.makedirs(results_dir, exist_ok=True)
        pd.DataFrame({
            "Time": time_series,
            "Original_Schedule": h["orig_vals"],
            "Executed_Schedule": h["new_vals"]
        }).to_csv(os.path.join(results_dir, 'dynamic_schedule_executed.csv'), index=False)
        
    print("Pass 1 Complete!")
    return pd.DataFrame(vpp_state_log)

#########################################
# PASS 2: OCHRE CO-SIMULATION
#########################################

def initialize_home(home_path, weather_file_path):
    # Dwellings now simply load the pre-baked schedules we generated in Pass 1
    base_sched_file = os.path.join(home_path, 'filtered_schedules_base.csv')
    ctrl_sched_file = os.path.join(home_path, 'filtered_schedules_ctrl.csv')
    hpxml_file = os.path.join(home_path, XML_ADDRESS)
    
    dwelling_args_base = {
        "start_time": Start,
        "time_res": dt.timedelta(minutes=t_res),
        "duration": dt.timedelta(days=Duration),
        "hpxml_file": hpxml_file,
        "hpxml_schedule_file": base_sched_file,
        "weather_file": weather_file_path,
        "verbosity": 7,
    }
    
    dwelling_args_ctrl = dwelling_args_base.copy()
    dwelling_args_ctrl["hpxml_schedule_file"] = ctrl_sched_file

    base_dwelling = Dwelling(name=f"Base_{os.path.basename(home_path)}", **dwelling_args_base)
    sim_dwelling = Dwelling(name=f"Ctrl_{os.path.basename(home_path)}", **dwelling_args_ctrl)
    return base_dwelling, sim_dwelling

def init_fleet_worker(home):
    """Worker function to initialize dwellings and set up state tracking queues"""
    base_dw, sim_dw = initialize_home(home, WEATHER_FILE)
    return {"base": base_dw, "sim": sim_dw, "path": home}

if __name__ == "__main__":
    # --- Directory Setup ---
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(WEATHER_DIR, exist_ok=True)
    
    for item in os.listdir(DEFAULT_INPUT):
        src = os.path.join(DEFAULT_INPUT, item)
        dst = os.path.join(INPUT_DIR, item)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
        
    # Copy weather file
    if not os.path.exists(WEATHER_FILE):
        shutil.copy(DEFAULT_WEATHER, WEATHER_FILE)

    homes = find_all_homes(INPUT_DIR)
    
    # =========================================================================
    # EXECUTE PASS 1
    # =========================================================================
    df_vpp_log_full = pre_process_schedules(homes)
    
    # =========================================================================
    # EXECUTE PASS 2
    # =========================================================================
    fleet_data = []
    print("--- PASS 2: Initializing OCHRE Dwellings ---")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(init_fleet_worker, home) for home in homes]
        for f in concurrent.futures.as_completed(futures):
            try:
                fleet_data.append(f.result())
            except Exception as e:
                print("Initialization failed:", e)

    if not fleet_data:
        print("No dwellings initialized. Exiting.")
        exit()

    sim_times = fleet_data[0]["base"].sim_times

    print("Starting OCHRE Native Co-Simulation Loop (No Overrides)...")
    for sim_time in sim_times:
        # We completely removed the Python PID logic from here. 
        # OCHRE runs using the pre-shifted schedules
        for home_data in fleet_data:
            home_data["base"].update() 
            home_data["sim"].update() 

    # --- Finalize and Output Data ---
    print("Simulation complete! Finalizing results...")
    
    CTRL_COLS = [
        "Time", "Total Electric Power (kW)", "Total Electric Energy (kWh)",
        "Clothes Dryer Electric Power (kW)"
    ]
    
    for home_data in fleet_data:
        home_path = home_data["path"]
        results_dir = os.path.join(home_path, "Results")
        
        df_base, _, _ = home_data["base"].finalize()
        df_ctrl, _, _ = home_data["sim"].finalize()
        
        df_base = remove_first_day(df_base, Start)
        df_ctrl = remove_first_day(df_ctrl, Start)
        
        df_ctrl = df_ctrl[[c for c in CTRL_COLS if c in df_ctrl.columns]]
        df_base = df_base[[c for c in CTRL_COLS if c in df_base.columns]]

        df_ctrl.to_csv(os.path.join(results_dir, 'dryer_controlled.csv'), index=False)
        df_base.to_csv(os.path.join(results_dir, 'dryer_baseline.csv'), index=False)

    # Aggregate CSVs
    aggregate_results(homes, WORKING_DIR)

    # Export VPP State Log (Filtered to match the OCHRE simulation timeframe)
    print("Saving VPP state log...")
    df_vpp_log_filtered = df_vpp_log_full[df_vpp_log_full["Time"].isin(sim_times)]
    vpp_log_path = os.path.join(WORKING_DIR, filename + "_VPP_Fleet_States.csv")
    df_vpp_log_filtered.to_csv(vpp_log_path, index=False)
    print(f"VPP State Log saved to: {vpp_log_path}")