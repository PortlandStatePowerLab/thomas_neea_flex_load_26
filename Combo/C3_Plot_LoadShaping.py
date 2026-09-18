#Author: Thomas Metzler
#9/10/2026

#Creates plots for the average device and total household power consumption, comparing baseline and controlled in load shaping

import pandas as pd
import os
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.dates as mdates
import datetime as dt

script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else '.'
fl_dir = os.path.dirname(script_dir)
working_dir = os.path.dirname(fl_dir)   

input_file_root = 'COMBO_Loadshape_WH_HVAC_Dryer_2'

PLOT_COMMAND_FRACTIONS = "ON"  # Set to "ON" or "OFF"

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

# Fleet States CSV path determination
fleet_states_file = os.path.join(folder_path, f"{input_file_root}_VPP_Fleet_States.csv")
if not os.path.exists(fleet_states_file):
    fleet_states_file = os.path.join(working_dir, f"{input_file_root}_VPP_Fleet_States.csv")

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

# ---------------------------------------------------------
# COMMAND STYLE & COLOR CONFIGURATION
# ---------------------------------------------------------
COMMAND_STYLES = {
    'ALU':    {'label': 'Advanced Load Up', 'color': '#00FF08', 'linestyle': '--', 'linewidth': 1.5},
    'LOAD':   {'label': 'Load Up',          'color': '#0077FF', 'linestyle': '-.', 'linewidth': 1.5},
    'LU':     {'label': 'Load Up',          'color': '#0077FF', 'linestyle': '-.', 'linewidth': 1.5},
    'CP':     {'label': 'Critical Peak',    'color': '#FF6600', 'linestyle': ':',  'linewidth': 1.5},
    'GE':     {'label': 'Grid Emergency',   'color': '#FF0000', 'linestyle': '--', 'linewidth': 1.5},
    'SHED':   {'label': 'Shed',             'color': '#FF00DD', 'linestyle': '-.', 'linewidth': 1.5},
    'S':      {'label': 'Shed',             'color': '#FF00DD', 'linestyle': '-.', 'linewidth': 1.5},
    'NORMAL': {'label': 'Normal',           'color': '#888888', 'linestyle': ':',  'linewidth': 1.0},
}

def get_command_style(col_name):
    col_upper = str(col_name).upper()
    for key, cfg in COMMAND_STYLES.items():
        if f" {key}" in col_upper or f"_{key}" in col_upper or col_upper.endswith(key):
            return cfg['label'], cfg['color'], cfg['linestyle'], cfg['linewidth']
    return col_name, '#9E9E9E', '-', 1.2

# Saves the average of each column as a new row, avoiding duplicates
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

# Plot the data and save the plot
def plot_data(baseline_file, controlled_file, title, photo_file, setpoint_csv=None, fleet_csv=None, device_tag=None):
    df_base = pd.read_csv(baseline_file, index_col=0)
    df_con = pd.read_csv(controlled_file, index_col=0)

    # Calculate the number of homes
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
    
    # --- Setpoint Power Line & Shaded Deadband ---
    if setpoint_csv and os.path.exists(setpoint_csv):
        try:
            df_sp = pd.read_csv(setpoint_csv)
            
            # Extract the actual header names for the first two columns to avoid hidden character errors
            time_col = df_sp.columns[0]
            val_col = df_sp.columns[1]
            
            # 1. Filter out metadata rows
            df_sp_times = df_sp[df_sp[time_col].astype(str).str.contains(':', na=False)].copy()
            
            # 2. Parse time column
            df_sp_times['Time'] = pd.to_datetime(df_sp_times[time_col], format='%H:%M', errors='coerce')
            
            # 3. Coerce setpoint values to numeric
            df_sp_times['Setpoint'] = pd.to_numeric(df_sp_times[val_col], errors='coerce')
            
            # 4. Plot setpoint line
            ax1.plot(df_sp_times['Time'], df_sp_times['Setpoint'], label='Setpoint', color='#2ca02c', linestyle='--', linewidth=2)
            
            # 5. Extract deadband and shade region if third column exists
            if len(df_sp.columns) >= 3:
                db_col = df_sp.columns[2]
                df_sp_times['Deadband'] = pd.to_numeric(df_sp_times[db_col], errors='coerce')

            # Append 00:00 value offset by +1 day (24:00) to bridge 23:00 to 00:00 end-of-day loop
            if not df_sp_times.empty:
                loop_row = df_sp_times.iloc[0].copy()
                loop_row['Time'] = loop_row['Time'] + pd.Timedelta(days=1)
                df_sp_times = pd.concat([df_sp_times, pd.DataFrame([loop_row])], ignore_index=True)

            ax1.plot(df_sp_times['Time'], df_sp_times['Setpoint'], label='Setpoint', color='#2ca02c', linestyle='--', linewidth=2)
            
            if 'Deadband' in df_sp_times.columns:
                upper_bound = df_sp_times['Setpoint'] + df_sp_times['Deadband']
                lower_bound = df_sp_times['Setpoint'] - df_sp_times['Deadband']
                
                ax1.fill_between(
                    df_sp_times['Time'], 
                    lower_bound, 
                    upper_bound, 
                    color='#2ca02c', 
                    alpha=0.2, 
                    label='Deadband'
                )
            print(f"[SUCCESS] Setpoint and deadband plotted for {title}")
            
        except Exception as e:
            print(f"[WARNING] Could not plot setpoint/deadband: {e}")

    ax1.set_ylabel('Power (kW)')

    # Update title to include n=... indicator
    ax1.set_title(f"{title} (n={num_homes})")
    ax1.grid(True, alpha=0.3)

    # Secondary axis initialized outside IF block to prevent UnboundLocalError
    ax2 = None
    if str(PLOT_COMMAND_FRACTIONS).strip().upper() in ["ON", "TRUE", "1"]:
        # --- SECONDARY AXIS: Command State Fractions ---
        if fleet_csv and os.path.exists(fleet_csv) and device_tag:
            try:
                df_fleet = pd.read_csv(fleet_csv)
                time_col = df_fleet.columns[0]

                df_fleet_times = df_fleet[df_fleet[time_col].astype(str).str.contains(':', na=False)].copy()

                # Align timestamps to match baseline dates (1900-01-01)
                raw_times = pd.to_datetime(df_fleet_times[time_col], errors='coerce')
                df_fleet_times['Time'] = pd.to_datetime(raw_times.dt.strftime('%H:%M'), format='%H:%M', errors='coerce')

                # Map device tags to CSV column prefix conventions
                tag_map = {'HEAT': 'HVAC', 'AC': 'HVAC', 'DRYER': 'DRY', 'DRY': 'DRY'}
                search_prefix = tag_map.get(device_tag.upper(), device_tag.upper())

                # Filter relevant columns for the target device
                relevant_cols = [
                    c for c in df_fleet.columns 
                    if c != time_col and search_prefix in c.upper()
                ]

                if relevant_cols:
                    ax2 = ax1.twinx()
                    ax2.set_ylabel('Fraction of units given command')
                    ax2.set_ylim(0, 1)

                    for col in relevant_cols:
                        vals = pd.to_numeric(df_fleet_times[col], errors='coerce')
                        
                        # Normalize device counts to fractions (0 to 1)
                        if vals.max() > 1.0:
                            vals = vals / num_homes

                        cmd_label, color, linestyle, linewidth = get_command_style(col)

                        ax2.plot(
                            df_fleet_times['Time'], 
                            vals, 
                            label=f"Cmd: {cmd_label}", 
                            color=color, 
                            linestyle=linestyle, 
                            linewidth=linewidth, 
                            alpha=0.5
                        )
                    print(f"[SUCCESS] Fleet command states plotted for {title}")

            except Exception as e:
                print(f"[WARNING] Could not plot fleet state commands: {e}")

    # --- FORMATTING & LEGEND ---
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    plt.setp(ax1.get_xticklabels(), rotation=45)

    # Combine legends
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    if ax2:
        lines_2, labels_2 = ax2.get_legend_handles_labels()
        lines_1 += lines_2
        labels_1 += labels_2

    ax1.legend(lines_1, labels_1, loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=4, frameon=False)

    plt.tight_layout()
    plt.savefig(photo_file, dpi=300, bbox_inches='tight')
    plt.close()


if WH_SIMULATION == "ON":
    save_avg(output_file_base_WH)
    save_avg(output_file_ctrl_WH)
    plot_data(output_file_base_WH, output_file_ctrl_WH, 'Average Power Consumption per Water Heater', photo_file_WH, fleet_csv=fleet_states_file, device_tag='WH')

if HVAC_SIMULATION == "ON":
    save_avg(output_file_base_AC)
    save_avg(output_file_ctrl_AC)
    plot_data(output_file_base_AC, output_file_ctrl_AC, 'Average Power Consumption per AC System', photo_file_AC, fleet_csv=fleet_states_file, device_tag='AC')
    save_avg(output_file_base_HEAT)
    save_avg(output_file_ctrl_HEAT)
    plot_data(output_file_base_HEAT, output_file_ctrl_HEAT, 'Average Power Consumption per Heating System', photo_file_HEAT, fleet_csv=fleet_states_file, device_tag='HEAT')

if DRYER_SIMULATION == "ON":
    save_avg(output_file_base_Dryer)
    save_avg(output_file_ctrl_Dryer)
    plot_data(output_file_base_Dryer, output_file_ctrl_Dryer, 'Average Power Consumption per Dryer', photo_file_Dryer, fleet_csv=fleet_states_file, device_tag='Dryer')

if EV_SIMULATION == "ON":
    save_avg(output_file_base_EV)
    save_avg(output_file_ctrl_EV)
    plot_data(output_file_base_EV, output_file_ctrl_EV, 'Average Power Consumption per Electric Vehicle', photo_file_EV, fleet_csv=fleet_states_file, device_tag='EV')
    save_avg(output_file_base_EVSOC)
    save_avg(output_file_ctrl_EVSOC)
    plot_data(output_file_base_EVSOC, output_file_ctrl_EVSOC, 'Average State of Charge per Electric Vehicle', photo_file_EVSOC, fleet_csv=fleet_states_file, device_tag='EV')

if BATTERY_SIMULATION == "ON":
    save_avg(output_file_base_BATT)
    save_avg(output_file_ctrl_BATT)
    plot_data(output_file_base_BATT, output_file_ctrl_BATT, 'Average Power Consumption per Battery', photo_file_BATT, fleet_csv=fleet_states_file, device_tag='BATT')
    save_avg(output_file_base_BATTSOC)
    save_avg(output_file_ctrl_BATTSOC)
    plot_data(output_file_base_BATTSOC, output_file_ctrl_BATTSOC, 'Average State of Charge per Battery', photo_file_BATTSOC, fleet_csv=fleet_states_file, device_tag='BATT')

# Passing setpoint CSV path to the total power plot
save_avg(output_file_base_total)
save_avg(output_file_ctrl_total)
plot_data(output_file_base_total, output_file_ctrl_total, 'Average Total Power Consumption per Household', photo_file_total, setpoint_csv=setpoint_file_path)

#Show plot at the end so it doesn't overwrite the previous plot
plt.show()