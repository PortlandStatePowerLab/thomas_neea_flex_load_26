"""
#Author: Thomas Metzler
#9/10/2026

#Creates plots for the average device and total household power consumption, comparing baseline and controlled in load shaping
"""


import pandas as pd
import os
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.dates as mdates
import datetime as dt

script_dir = os.path.dirname(os.path.abspath(__file__))
fl_dir = os.path.dirname(script_dir)
working_dir = os.path.dirname(fl_dir)   

input_file_root = 'COMBO_Loadshape_WH_HVAC_3'

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

input_file_name_base = input_file_root + "_baseline"
input_file_name_ctrl = input_file_root + "_controlled"
input_file_base  = os.path.join(working_dir, input_file_name_base +".csv")
input_file_ctrl  = os.path.join(working_dir, input_file_name_ctrl +".csv")

folder_path = os.path.join(working_dir, "Ready_data", input_file_root)

if WH_SIMULATION == "ON":
    output_append_WHpower = "_WH_power"
    output_file_name_base_WH = input_file_name_base + output_append_WHpower + ".csv"
    output_file_name_ctrl_WH = input_file_name_ctrl + output_append_WHpower + ".csv"
    output_file_base_WH = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_base_WH)
    output_file_ctrl_WH = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_ctrl_WH)

if HVAC_SIMULATION == "ON":
    output_append_ACpower = "_AC_power"
    output_file_name_base_AC = input_file_name_base + output_append_ACpower + ".csv"
    output_file_name_ctrl_AC = input_file_name_ctrl + output_append_ACpower + ".csv"
    output_file_base_AC = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_base_AC)
    output_file_ctrl_AC = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_ctrl_AC)

    output_append_HEATpower = "_HEAT_power"
    output_file_name_base_HEAT = input_file_name_base + output_append_HEATpower + ".csv"
    output_file_name_ctrl_HEAT = input_file_name_ctrl + output_append_HEATpower + ".csv"
    output_file_base_HEAT = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_base_HEAT)
    output_file_ctrl_HEAT = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_ctrl_HEAT)

if DRYER_SIMULATION == "ON":
    output_append_Dryerpower = "_Dryer_power"
    output_file_name_base_Dryer = input_file_name_base + output_append_Dryerpower + ".csv"
    output_file_name_ctrl_Dryer = input_file_name_ctrl + output_append_Dryerpower + ".csv"
    output_file_base_Dryer = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_base_Dryer)
    output_file_ctrl_Dryer = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_ctrl_Dryer)

if EV_SIMULATION == "ON":
    output_append_EVpower = "_EV_power"
    output_file_name_base_EV = input_file_name_base + output_append_EVpower + ".csv"
    output_file_name_ctrl_EV = input_file_name_ctrl + output_append_EVpower + ".csv"
    output_file_base_EV = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_base_EV)
    output_file_ctrl_EV = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_ctrl_EV)

    output_append_EVSOC = "_EV_SOC"
    output_file_name_base_EVSOC = input_file_name_base + output_append_EVSOC + ".csv"
    output_file_name_ctrl_EVSOC = input_file_name_ctrl + output_append_EVSOC + ".csv"
    output_file_base_EVSOC = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_base_EVSOC)
    output_file_ctrl_EVSOC = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_ctrl_EVSOC)

if BATTERY_SIMULATION == "ON":
    output_append_BATTpower = "_BATT_power"
    output_file_name_base_BATT = input_file_name_base + output_append_BATTpower + ".csv"
    output_file_name_ctrl_BATT = input_file_name_ctrl + output_append_BATTpower + ".csv"
    output_file_base_BATT = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_base_BATT)
    output_file_ctrl_BATT = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_ctrl_BATT)

    output_append_BATTSOC = "_BATT_SOC"
    output_file_name_base_BATTSOC = input_file_name_base + output_append_BATTSOC + ".csv"
    output_file_name_ctrl_BATTSOC = input_file_name_ctrl + output_append_BATTSOC + ".csv"
    output_file_base_BATTSOC = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_base_BATTSOC)
    output_file_ctrl_BATTSOC = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_ctrl_BATTSOC)

output_append_totpower = "_total_power"
output_file_name_base_total = input_file_name_base + output_append_totpower + ".csv"
output_file_name_ctrl_total = input_file_name_ctrl + output_append_totpower + ".csv"
output_file_base_total = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_base_total)
output_file_ctrl_total = os.path.join(working_dir, "Ready_data", input_file_root, output_file_name_ctrl_total)

photo_file_WH = os.path.join(working_dir, "Ready_data", input_file_root, input_file_root + "_WH_power_plot.png")
photo_file_AC = os.path.join(working_dir, "Ready_data", input_file_root, input_file_root + "_AC_power_plot.png")
photo_file_HEAT = os.path.join(working_dir, "Ready_data", input_file_root, input_file_root + "_HEAT_power_plot.png")
photo_file_Dryer = os.path.join(working_dir, "Ready_data", input_file_root, input_file_root + "_Dryer_power_plot.png")
photo_file_EV = os.path.join(working_dir, "Ready_data", input_file_root, input_file_root + "_EV_power_plot.png")
photo_file_EVSOC = os.path.join(working_dir, "Ready_data", input_file_root, input_file_root + "_EV_SOC_plot.png")
photo_file_BATT = os.path.join(working_dir, "Ready_data", input_file_root, input_file_root + "_BATT_power_plot.png")
photo_file_BATTSOC = os.path.join(working_dir, "Ready_data", input_file_root, input_file_root + "_BATT_SOC_plot.png")
photo_file_total = os.path.join(working_dir, "Ready_data", input_file_root, input_file_root + "_total_power_plot.png")

# Setpoint file definition
setpoint_file_path = os.path.join(script_dir, "B0_Load_Shaping_Controls.csv")

#Saves the average of each column as a new row, avoiding duplicates
def save_avg(file):
    # 1. Read the CSV file into a DataFrame
    df = pd.read_csv(file)

    # 2. Check if the average row already exists
    # We look at the first column of the very last row to see if it says 'Average'
    if str(df.iloc[-1, 0]) == 'Average':
        return  # Skip appending if it's already there

    # 3. Calculate the mean for numeric columns
    averages = df.mean(numeric_only=True)

    # 4. Append the averages as a new row
    # We place 'Average' explicitly in the first column so it saves correctly
    df.loc[len(df)] = averages
    df.iloc[-1, 0] = 'Average'

    # 5. Save back to a CSV file
    df.to_csv(file, index=False)


#plot the data and save the plot
def plot_data(baseline_file, controlled_file, title, photo_file, setpoint_csv=None):
    df_base = pd.read_csv(baseline_file, index_col=0)
    df_con = pd.read_csv(controlled_file, index_col=0)

    # Calculate the number of homes (total rows minus the 'Average' row added prior)
    num_homes = len(df_base) - 1

    # Extract averages and transpose 
    df_base = pd.DataFrame(df_base.iloc[[0, -1]].iloc[1, :]).reset_index()
    df_con = pd.DataFrame(df_con.iloc[[0, -1]].iloc[1, :]).reset_index()
    
    df_base.columns = ['Time', 'baseline']
    df_con.columns = ['Time', 'controlled']

    # Convert to actual datetime objects for smooth plotting
    df_base['Time'] = pd.to_datetime(df_base['Time'], format='%H:%M', errors='coerce')
    df_con['Time'] = pd.to_datetime(df_con['Time'], format='%H:%M', errors='coerce')

    fig, ax1 = plt.subplots(figsize=(10, 5))

    # --- PRIMARY AXIS: Power ---
    ax1.plot(df_base['Time'], df_base['baseline'], label='Baseline', color='#004C6D', linewidth=2)
    ax1.plot(df_con['Time'], df_con['controlled'], label='Controlled', color='#E26D28', linewidth=2)
    
    # Setpoint Power Line from B0_Load_Shaping_Controls.csv ---
    if setpoint_csv and os.path.exists(setpoint_csv):
        try:
            df_sp = pd.read_csv(setpoint_csv)
            
            # Extract the actual header names for the first two columns to avoid hidden character errors
            time_col = df_sp.columns[0]
            val_col = df_sp.columns[1]
            
            # 1. Filter out metadata rows (isolate rows where the first column contains a colon)
            df_sp_times = df_sp[df_sp[time_col].astype(str).str.contains(':', na=False)].copy()
            
            # 2. Parse time column
            parsed_times = pd.to_datetime(df_sp_times[time_col], errors='coerce')
            df_sp_times['Time'] = pd.to_datetime(parsed_times.dt.strftime('%H:%M'), format='%H:%M', errors='coerce')
            
            # 3. Coerce values to numeric (turns 'OFF' into NaN)
            df_sp_times['Setpoint'] = pd.to_numeric(df_sp_times[val_col], errors='coerce')
            
            # 4. Plot the setpoint line
            ax1.plot(df_sp_times['Time'], df_sp_times['Setpoint'], label='Setpoint', color='#2ca02c', linestyle='--', linewidth=2)
            print(f"[SUCCESS] Setpoint line plotted for {title}")
            
        except Exception as e:
            print(f"[WARNING] Could not plot setpoint: {e}")

    ax1.set_ylabel('Power (kW)')

    # Update title to include n=... indicator
    ax1.set_title(f"{title} (n={num_homes})")
    ax1.grid(True, alpha=0.3)
    
    added_labels = set()

    # --- FORMATTING & LEGEND ---
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    plt.setp(ax1.get_xticklabels(), rotation=45)

    # Cleaned up legend call 
    ax1.legend(loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=3, frameon=False)

    plt.tight_layout()
    plt.savefig(photo_file, dpi=300, bbox_inches='tight')
    plt.close()


if WH_SIMULATION == "ON":
    save_avg(output_file_base_WH)
    save_avg(output_file_ctrl_WH)
    plot_data(output_file_base_WH, output_file_ctrl_WH, 'Average Power Consumption per Water Heater', photo_file_WH)

if HVAC_SIMULATION == "ON":
    save_avg(output_file_base_AC)
    save_avg(output_file_ctrl_AC)
    plot_data(output_file_base_AC, output_file_ctrl_AC, 'Average Power Consumption per AC System', photo_file_AC)
    save_avg(output_file_base_HEAT)
    save_avg(output_file_ctrl_HEAT)
    plot_data(output_file_base_HEAT, output_file_ctrl_HEAT, 'Average Power Consumption per Heating System', photo_file_HEAT)

if DRYER_SIMULATION == "ON":
    save_avg(output_file_base_Dryer)
    save_avg(output_file_ctrl_Dryer)
    plot_data(output_file_base_Dryer, output_file_ctrl_Dryer, 'Average Power Consumption per Dryer', photo_file_Dryer)

if EV_SIMULATION == "ON":
    save_avg(output_file_base_EV)
    save_avg(output_file_ctrl_EV)
    plot_data(output_file_base_EV, output_file_ctrl_EV, 'Average Power Consumption per Electric Vehicle', photo_file_EV)
    save_avg(output_file_base_EVSOC)
    save_avg(output_file_ctrl_EVSOC)
    plot_data(output_file_base_EVSOC, output_file_ctrl_EVSOC, 'Average State of Charge per Electric Vehicle', photo_file_EVSOC)

if BATTERY_SIMULATION == "ON":
    save_avg(output_file_base_BATT)
    save_avg(output_file_ctrl_BATT)
    plot_data(output_file_base_BATT, output_file_ctrl_BATT, 'Average Power Consumption per Battery', photo_file_BATT)
    save_avg(output_file_base_BATTSOC)
    save_avg(output_file_ctrl_BATTSOC)
    plot_data(output_file_base_BATTSOC, output_file_ctrl_BATTSOC, 'Average State of Charge per Battery', photo_file_BATTSOC)

# Passing the setpoint CSV path only to the total power plot so it doesn't try to draw a household setpoint on individual device loads
save_avg(output_file_base_total)
save_avg(output_file_ctrl_total)
plot_data(output_file_base_total, output_file_ctrl_total, 'Average Total Power Consumption per Household', photo_file_total, setpoint_csv=setpoint_file_path)

#Show plot at the end so it doesn't overwrite the previous plot
plt.show()