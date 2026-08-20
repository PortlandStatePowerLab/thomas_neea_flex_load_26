"""
Author: Thomas Metzler
Amended: Dynamic Duty-Cycle Schedule Shifting with 1-Step Transition Delays
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
import random

#########################################
# USER SETTINGS
#########################################

filename = 'Dryer_test_Loadshape_6'
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
# Define the time window for active load shaping
VPP_START_TIME = dt.time(12, 0)
VPP_END_TIME = dt.time(23, 0)

# Fleet-agnostic average power targets
AVERAGE_SETPOINT_KW = 1.5     
AVERAGE_DEADBAND_KW = 0.1     
ESTIMATED_SHED_KW = 1.5  # Typical dryer demand in kW when active     

# Duty cycle power fraction during SHED mode (e.g., 0.5 = 50% power)
DUTY_CYCLE_FRACTION = 0.5

# --- PID CONTROLLER GAINS ---
KP = 1.0                      
KI = 0.8                      
KD = 1.0                      

count = 0

#########################################
# HELPER FUNCTIONS
#########################################

def filter_schedules(home_path, is_control=False):
    orig_sched_file = os.path.join(home_path, CSV_ADDRESS)
    file_suffix = 'ctrl' if is_control else 'base'
    filtered_sched_file = os.path.join(home_path, f'filtered_schedules_{file_suffix}.csv')

    df_sched = pd.read_csv(orig_sched_file)
    valid_schedule_names = set(ALL_SCHEDULE_NAMES.keys())
    
    # Ensure 'Time' is kept to allow datetime parsing
    filtered_columns = [col for col in df_sched.columns if col in valid_schedule_names or col == 'Time']
    dropped_columns = [col for col in df_sched.columns if col not in filtered_columns]
    
    if dropped_columns and not is_control:
        print(f"Dropped invalid schedules for {home_path}: {dropped_columns}")

    df_sched_filtered = df_sched[filtered_columns].copy()
    
    # --- PRE-PROCESS CONTROL SCHEDULE ---
    if is_control and 'Time' in df_sched_filtered.columns:
        dt_times = pd.to_datetime(df_sched_filtered['Time'])
        time_of_day = dt_times.dt.time
        
        # Identify rows inside the global VPP window
        in_window = (time_of_day >= VPP_START_TIME) & (time_of_day < VPP_END_TIME)
        
        dryer_cols = [c for c in df_sched_filtered.columns if 'dryer' in c.lower()]
        if dryer_cols:
            dryer_col = dryer_cols[0]
            
            # Find the start and end boundaries of the shed block
            window_shifted = in_window.shift(1, fill_value=False)
            start_of_sheds = in_window & ~window_shifted
            end_of_sheds = in_window & ~in_window.shift(-1, fill_value=False)
            
            # 1. Adjust the schedule to 0.5 for the duty cycle during the shed
            df_sched_filtered.loc[in_window, dryer_col] *= DUTY_CYCLE_FRACTION
            
            # 2. Assign 0 for a timestep at the start and end of each shed event
            df_sched_filtered.loc[start_of_sheds, dryer_col] = 0.0
            df_sched_filtered.loc[end_of_sheds, dryer_col] = 0.0

    df_sched_filtered.to_csv(filtered_sched_file, index=False)
    return filtered_sched_file

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
# HPWH / HVAC CONTROL & INITIALIZATION
#########################################

def initialize_home(home_path, weather_file_path):
    # Pass separate arguments so the base dwelling remains unshedded
    base_sched_file = filter_schedules(home_path, is_control=False)
    ctrl_sched_file = filter_schedules(home_path, is_control=True)
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
    
    # Read original schedule to drive work queue inputs
    orig_sched_file = os.path.join(home, CSV_ADDRESS)
    df_sched = pd.read_csv(orig_sched_file)
    dryer_cols = [c for c in df_sched.columns if 'dryer' in c.lower()]
    dryer_col = dryer_cols[0] if dryer_cols else None
    
    if dryer_col:
        orig_vals = df_sched[dryer_col].values
        max_cap = orig_vals.max() if orig_vals.max() > 0 else 1.0
    else:
        orig_vals = []
        max_cap = 1.0

    # Calculate starting index to align with OCHRE's Start time
    start_of_year = dt.datetime(Start.year, 1, 1, 0, 0)
    time_diff = Start - start_of_year
    start_idx = int(time_diff.total_seconds() / (t_res * 60))
        
    return {
        "base": base_dw, 
        "sim": sim_dw, 
        "path": home,
        "mode": "NORMAL",             # State: 'NORMAL' or 'SHED'
        "pending_off": False,          # Flag for 1-step OFF transition delay
        "work_queue": 0.0,             # Accumulates active drying workload (in steps)
        "orig_vals": orig_vals,
        "new_vals": [], 
        "max_cap": max_cap,
        "dryer_col": dryer_col,
        "schedule_idx": start_idx
    }

#########################################
# MAIN EXECUTION
#########################################

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
    print(f"Found {len(homes)} homes")

    # --- 1. Parallel Fleet Initialization ---
    fleet_data = []
    print("Initializing dwellings...")
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

    num_homes = len(fleet_data)
    
    # --- 2. Co-Simulation Time Loop Setup ---
    sim_times = fleet_data[0]["base"].sim_times
    average_power_kw = 0.0

    vpp_state_log = []

    # PID State tracking variables
    integral_error = 0.0
    previous_error = 0.0

    print("Starting Co-Simulation Loop...")
    for sim_time in sim_times:
        current_time_of_day = sim_time.time()
        
        # Check if we are inside the VPP event window
        is_vpp_active = VPP_START_TIME <= current_time_of_day < VPP_END_TIME

        if is_vpp_active:
            # --- Active Load Shaping Dispatch Logic (Bidirectional & Asymmetrical) ---
            # PID error calculation: Error = Setpoint - Actual
            error = AVERAGE_SETPOINT_KW - average_power_kw
            
            # Discrete-time tracking transformations
            integral_error += error
            derivative_error = error - previous_error
            previous_error = error
            
            # Compute PID output value
            pid_output = (KP * error) + (KI * integral_error) + (KD * derivative_error)
            
            if pid_output < -AVERAGE_DEADBAND_KW:
                # OVER setpoint -> Issue SHED commands
                total_kw_to_drop = abs(pid_output) * num_homes
                
                # ONLY target active dryers (work_queue > 0) currently in NORMAL mode
                active_normal_homes = [
                    h for h in fleet_data 
                    if h["mode"] == "NORMAL" and h["work_queue"] > 1e-4
                ]
                random.shuffle(active_normal_homes)
                
                units_to_shed = int(total_kw_to_drop / ESTIMATED_SHED_KW)
                shed_applied = min(units_to_shed, len(active_normal_homes))
                
                for h in active_normal_homes[:shed_applied]:
                    h["mode"] = "SHED"
                    h["pending_off"] = True  # Enforce 1-step OFF transition
                        
            elif pid_output > AVERAGE_DEADBAND_KW:
                # UNDER setpoint -> Restore SHED commands to NORMAL (No LOAD commands)
                total_kw_to_add = pid_output * num_homes
                
                shed_homes = [h for h in fleet_data if h["mode"] == "SHED"]
                random.shuffle(shed_homes)
                
                units_to_restore = int(total_kw_to_add / ESTIMATED_SHED_KW)
                restored_applied = min(units_to_restore, len(shed_homes))
                
                for h in shed_homes[:restored_applied]:
                    h["mode"] = "NORMAL"
                    h["pending_off"] = True  # Enforce 1-step OFF transition
        else:
            for h in fleet_data:
                if h["mode"] == "SHED":
                    h["mode"] = "NORMAL"
                    h["pending_off"] = True
            
            # Reset PID memory tracking to prevent baseline distortion at next event start
            integral_error = 0.0
            previous_error = 0.0

        #Initialize 
        current_step_aggregate_power = 0.0
        
        for home_data in fleet_data:
            base_dw = home_data["base"]
            sim_dw = home_data["sim"]
            
            # 1. Dynamic Load Accumulation & Shift Logic
            idx = home_data["schedule_idx"]
            orig_val = home_data["orig_vals"][idx] if idx < len(home_data["orig_vals"]) else 0.0
            home_data["schedule_idx"] += 1
            
            # Accumulate active drying demand from schedule into the work queue
            if home_data["max_cap"] > 0 and orig_val > 0:
                home_data["work_queue"] += (orig_val / home_data["max_cap"])
            
            # --- State Machine & Queue Processing ---
            if home_data["pending_off"]:
                # Step 1 after state transition: turn off for 1 time step
                lf = 1.0  # Force to 1.0 per static preprocessing strategy
                home_data["pending_off"] = False
            else:
                if home_data["work_queue"] > 1e-4:
                    if home_data["mode"] == "SHED":
                        # Run at reduced duty cycle power consumption
                        lf = 1.0  # Force to 1.0
                        home_data["work_queue"] = max(0.0, home_data["work_queue"] - DUTY_CYCLE_FRACTION)
                    else:
                        # Run at normal power consumption
                        lf = 1.0  # Force to 1.0
                        home_data["work_queue"] = max(0.0, home_data["work_queue"] - 1.0)
                else:
                    lf = 1.0  # Force to 1.0
                    home_data["work_queue"] = 0.0

            home_data["new_vals"].append(lf * home_data["max_cap"])
            
            # Send control commands to OCHRE
            base_ctrl = {"Clothes Dryer": {"Load Fraction": 1}}
            base_dw.update(control_signal=base_ctrl) 

            # The Load Fraction calculation dynamically matches the duty cycle queue
            ctrl_cmd = {"Clothes Dryer": {"Load Fraction": 1}}
            metrics = sim_dw.update(control_signal=ctrl_cmd) 
            
            # 3. Read back real-time power
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

        shed_count = sum(1 for h in fleet_data if h["mode"] == "SHED")
        normal_count = sum(1 for h in fleet_data if h["mode"] == "NORMAL")
        
        vpp_state_log.append({
            "Time": sim_time,
            "Target Average Power (kW)": AVERAGE_SETPOINT_KW if is_vpp_active else "OFF",
            "Actual Average Power (kW)": average_power_kw,
            "Aggregate Power (kW)": aggregate_power_kw,
            "Units in NORMAL": normal_count,
            "Units in SHED": shed_count
        })

    # --- 3. Finalize and Output Data ---
    print("Simulation complete! Finalizing results...")
    
    CTRL_COLS = [
        "Time", "Total Electric Power (kW)", "Total Electric Energy (kWh)",
        "Clothes Dryer Electric Power (kW)"
    ]
    
    for home_data in fleet_data:
        home_path = home_data["path"]
        results_dir = os.path.join(home_path, "Results")
        os.makedirs(results_dir, exist_ok=True)
        
        # Output dynamically generated schedule file for verification
        shifted_df = pd.DataFrame({
            "Time": sim_times,
            "Original_Schedule": home_data["orig_vals"][:len(sim_times)],
            "Executed_Schedule": home_data["new_vals"]
        })
        shifted_df.to_csv(os.path.join(results_dir, 'dynamic_schedule_executed.csv'), index=False)
        
        df_base, _, _ = home_data["base"].finalize()
        df_ctrl, _, _ = home_data["sim"].finalize()
        
        df_base = remove_first_day(df_base, Start)
        df_ctrl = remove_first_day(df_ctrl, Start)
        
        df_ctrl = df_ctrl[[c for c in CTRL_COLS if c in df_ctrl.columns]]
        df_base = df_base[[c for c in CTRL_COLS if c in df_base.columns]]

        df_ctrl.to_csv(os.path.join(results_dir, 'dryer_controlled.csv'), index=False)
        df_base.to_csv(os.path.join(results_dir, 'dryer_baseline.csv'), index=False)

    # --- 4. Aggregate ---
    aggregate_results(homes, WORKING_DIR)

    # --- 5. Export VPP State Log ---
    print("Saving VPP state log...")
    df_vpp_log = pd.DataFrame(vpp_state_log)
    vpp_log_path = os.path.join(WORKING_DIR, filename + "_VPP_Fleet_States.csv")
    df_vpp_log.to_csv(vpp_log_path, index=False)
    print(f"VPP State Log saved to: {vpp_log_path}")