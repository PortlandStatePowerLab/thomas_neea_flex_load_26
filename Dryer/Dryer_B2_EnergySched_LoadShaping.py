"""
Author: Thomas Metzler
Created: 8/19/26

Adjusts load up and shed commands to keep dryer fleet power consumption at a constant level.
Modified to account for dryer constraints (managing load via SHED and NORMAL restoration only).
Runs the BASELINE OCHRE first, calculates whole-home power PID logic, shifts schedules, 
and runs the CONTROLLED OCHRE simulation.
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

filename = 'Dryer_test_Loadshape_17'
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
AVERAGE_SETPOINT_KW = 2.0     
AVERAGE_DEADBAND_KW = 0.1     
ESTIMATED_SHED_KW = 1.5  

# Duty cycle power fraction during SHED mode
DUTY_CYCLE_FRACTION = 0.25

# --- PID CONTROLLER GAINS ---
KP = 1.0                      
KI = 0.1                      
KD = 0.5                      

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
# MAIN EXECUTION
#########################################

if __name__ == "__main__":
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(WEATHER_DIR, exist_ok=True)
    
    for item in os.listdir(DEFAULT_INPUT):
        src = os.path.join(DEFAULT_INPUT, item)
        dst = os.path.join(INPUT_DIR, item)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
            
    if not os.path.exists(WEATHER_FILE):
        shutil.copy(DEFAULT_WEATHER, WEATHER_FILE)

    homes = find_all_homes(INPUT_DIR)
    if not homes:
        print("No homes found. Exiting.")
        exit()

    # =========================================================================
    # PASS 1: OCHRE BASELINE RUN
    # =========================================================================
    print(f"--- PASS 1: Running Baseline OCHRE for {len(homes)} homes ---")
    baseline_dwellings = []
    successful_homes = [] # Track which homes actually survived initialization
    
    def init_base(home_path):
        hpxml_file = os.path.join(home_path, XML_ADDRESS)
        orig_sched_file = os.path.join(home_path, CSV_ADDRESS)
        dw = Dwelling(name=f"Base_{os.path.basename(home_path)}",
                      start_time=Start, time_res=dt.timedelta(minutes=t_res),
                      duration=dt.timedelta(days=Duration),
                      hpxml_file=hpxml_file, hpxml_schedule_file=orig_sched_file,
                      weather_file=WEATHER_FILE, verbosity=7)
        return {"path": home_path, "dw": dw}
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        # Use a dictionary to map the future back to the home path for logging
        futures = {executor.submit(init_base, h): h for h in homes}
        for f in concurrent.futures.as_completed(futures):
            home_path = futures[f]
            try:
                baseline_dwellings.append(f.result())
                successful_homes.append(home_path)
            except Exception as e:
                # Catch the error, print a warning, and move on
                print(f"Skipping {os.path.basename(home_path)} due to init error: {e}")
                
    # Reassign the main homes list so Passes 2 and 3 completely ignore the broken homes
    homes = successful_homes
            
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
    # PASS 2: PYTHON VPP CONTROLLER & SCHEDULE SHIFTING
    # =========================================================================
    print("--- PASS 2: Calculating Shifted Schedules with PID ---")
    fleet_data = []
    
    # Assume the schedule CSV represents a full year starting on Jan 1 of the simulation year
    start_of_year = dt.datetime(Start.year, 1, 1, 0, 0)
    
    for home in homes:
        orig_sched_file = os.path.join(home, CSV_ADDRESS)
        df_sched = pd.read_csv(orig_sched_file)
        
        # Generate the full time series to map CSV rows to real timestamps
        full_time_series = pd.date_range(
            start=start_of_year, 
            periods=len(df_sched), 
            freq=pd.Timedelta(minutes=t_res)
        )
        
        # Create a fast lookup dictionary for mapping timestamps to CSV row indexes
        time_to_idx = {time: i for i, time in enumerate(full_time_series)}
        
        df_base_out = baseline_data[home]
        
        dryer_cols = [c for c in df_sched.columns if 'dryer' in c.lower()]
        dryer_col = dryer_cols[0] if dryer_cols else None
        
        orig_vals = df_sched[dryer_col].values if dryer_col else np.zeros(len(df_sched))
        max_cap = orig_vals.max() if orig_vals.max() > 0 else 1.0
        
        fleet_data.append({
            "path": home,
            "df_sched": df_sched,
            "df_base_out": df_base_out,
            "dryer_col": dryer_col,
            "orig_vals": orig_vals,
            "new_vals": list(orig_vals), # Copy to preserve data outside simulation bounds
            "max_cap": max_cap,
            "mode": "NORMAL",
            "pending_off": False,
            "work_queue": 0.0,
            "time_to_idx": time_to_idx # Store the lookup dict here for convenience
        })

    average_power_kw = 0.0 
    previous_average_power_kw = 0.0 
    integral_error = 0.0
    previous_error = 0.0
    num_homes = len(fleet_data)
    vpp_state_log = []

    for current_time in sim_times:
        current_time_of_day = current_time.time()
        is_vpp_active = VPP_START_TIME <= current_time_of_day < VPP_END_TIME
        
        # 1. Update Energy Queues
        for h in fleet_data:
            csv_idx = h["time_to_idx"][current_time] # Find the true row for this timestamp
            val = h["orig_vals"][csv_idx]
            if h["max_cap"] > 0 and val > 0:
                h["work_queue"] += (val / h["max_cap"])
                
        # 2. VPP / PID Logic
        if is_vpp_active:
            error = AVERAGE_SETPOINT_KW - previous_average_power_kw
            integral_error += error

            # --- ANTI-WINDUP CLAMPING ---
            # Prevent the integral from building up a massive "memory" when error stays positive or negative for hours
            MAX_INTEGRAL = 0.1
            MIN_INTEGRAL = -0.5
            integral_error = max(min(integral_error, MAX_INTEGRAL), MIN_INTEGRAL)

            derivative_error = error - previous_error
            previous_error = error
            
            pid_output = (KP * error) + (KI * integral_error) + (KD * derivative_error)
            
            if pid_output < -AVERAGE_DEADBAND_KW:
                total_kw_to_drop = abs(pid_output) * num_homes
                active_normal_homes = [h for h in fleet_data if h["mode"] == "NORMAL" and h["work_queue"] > 1e-4]
                random.shuffle(active_normal_homes)
                
                units_to_shed = int(total_kw_to_drop / ESTIMATED_SHED_KW)
                shed_applied = min(units_to_shed, len(active_normal_homes))
                for h in active_normal_homes[:shed_applied]:
                    h["mode"] = "SHED"
                    h["pending_off"] = True
                    
            elif pid_output > AVERAGE_DEADBAND_KW:
                total_kw_to_add = pid_output * num_homes
                shed_homes = [h for h in fleet_data if h["mode"] == "SHED"]
                random.shuffle(shed_homes)
                
                units_to_restore = int(total_kw_to_add / ESTIMATED_SHED_KW)
                restored_applied = min(units_to_restore, len(shed_homes))
                for h in shed_homes[:restored_applied]:
                    h["mode"] = "NORMAL"
                    h["pending_off"] = True
        else:
            for h in fleet_data:
                if h["mode"] == "SHED":
                    h["mode"] = "NORMAL"
                    h["pending_off"] = True
            integral_error = 0.0
            previous_error = 0.0
            
        # 3. Dispense Energy & Build New Schedule
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
            h["new_vals"][csv_idx] = val_kw

            # For the baseline extraction, you still need an index that starts at 0 
            # since df_base_out only contains the 2 simulation days
            sim_idx = list(sim_times).index(current_time) 
            
            # Calculate True Whole-Home Power for PID feedback
            base_total_kw = h["df_base_out"]['Total Electric Power (kW)'].iloc[sim_idx]
            base_dryer_kw = h["df_base_out"].get('Clothes Dryer Electric Power (kW)', pd.Series([0]*len(sim_times))).iloc[sim_idx]
            
            estimated_ctrl_total = (base_total_kw - base_dryer_kw) + val_kw
            current_step_aggregate += estimated_ctrl_total

        previous_average_power_kw = current_step_aggregate / num_homes
        
        vpp_state_log.append({
            "Time": current_time,
            "Target Average Power (kW)": AVERAGE_SETPOINT_KW if is_vpp_active else "OFF",
            "Actual Average Power (kW)": previous_average_power_kw, 
            "Aggregate Power (kW)": current_step_aggregate,
            "Units in NORMAL": sum(1 for h in fleet_data if h["mode"] == "NORMAL"),
            "Units in SHED": sum(1 for h in fleet_data if h["mode"] == "SHED")
        })

    # Save Shifted Schedules
    valid_schedule_names = set(ALL_SCHEDULE_NAMES.keys())
    for h in fleet_data:
        df = h["df_sched"]
        filtered_cols = [col for col in df.columns if col in valid_schedule_names or col == 'Time']
        
        df_ctrl = df[filtered_cols].copy()
        if h["dryer_col"]:
            df_ctrl[h["dryer_col"]] = h["new_vals"]
        df_ctrl.to_csv(os.path.join(h["path"], 'filtered_schedules_ctrl.csv'), index=False)

    # =========================================================================
    # PASS 3: OCHRE CONTROL RUN
    # =========================================================================
    print("--- PASS 3: Running Controlled OCHRE Simulation ---")
    control_dwellings = []
    
    def init_ctrl(home_path):
        hpxml_file = os.path.join(home_path, XML_ADDRESS)
        ctrl_sched_file = os.path.join(home_path, 'filtered_schedules_ctrl.csv')
        dw = Dwelling(name=f"Ctrl_{os.path.basename(home_path)}",
                      start_time=Start, time_res=dt.timedelta(minutes=t_res),
                      duration=dt.timedelta(days=Duration),
                      hpxml_file=hpxml_file, hpxml_schedule_file=ctrl_sched_file,
                      weather_file=WEATHER_FILE, verbosity=7)
        return {"path": home_path, "dw": dw}
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(init_ctrl, h) for h in homes]
        for f in concurrent.futures.as_completed(futures):
            control_dwellings.append(f.result())
            
    for t in sim_times:
        for c in control_dwellings:
            c["dw"].update()

    print("Simulation complete! Finalizing results...")
    
    CTRL_COLS = ["Time", "Total Electric Power (kW)", "Total Electric Energy (kWh)", "Clothes Dryer Electric Power (kW)"]
    
    for c in control_dwellings:
        home_path = c["path"]
        results_dir = os.path.join(home_path, "Results")
        os.makedirs(results_dir, exist_ok=True)
        
        # Save Control
        df_ctrl, _, _ = c["dw"].finalize()
        df_ctrl = remove_first_day(df_ctrl, Start)
        df_ctrl = df_ctrl[[col for col in CTRL_COLS if col in df_ctrl.columns]]
        df_ctrl.to_csv(os.path.join(results_dir, 'dryer_controlled.csv'), index=False)
        
        # Save Baseline (Calculated in Pass 1)
        df_base = baseline_data[home_path]
        df_base = remove_first_day(df_base, Start)
        df_base = df_base[[col for col in CTRL_COLS if col in df_base.columns]]
        df_base.to_csv(os.path.join(results_dir, 'dryer_baseline.csv'), index=False)

    # Aggregate CSVs
    aggregate_results(homes, WORKING_DIR)

    # Export VPP State Log (Filtered to match the OCHRE simulation timeframe)
    df_vpp_log = pd.DataFrame(vpp_state_log)
    vpp_log_path = os.path.join(WORKING_DIR, filename + "_VPP_Fleet_States.csv")
    df_vpp_log.to_csv(vpp_log_path, index=False)
    print(f"VPP State Log saved to: {vpp_log_path}")