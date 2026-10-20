"""
Author: Thomas Metzler 
Date: 10/18/2026

Description:
Reads 'Impulse (10)' data from 'Combined Data.xlsx' (rows 2-9) and plots power consumption
for all devices against time. Integrates demand response event schedules (Load Up, Shed, etc.)
from 'B0_Commands_Schedule.csv' as trapezoidal overlays on a secondary y-axis in the C2 plotting style.
"""

import os
import datetime as dt
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

# ---------------------------------------------------------
# DIRECTORY & FILE SETUP
# ---------------------------------------------------------
script_dir = os.path.dirname(os.path.abspath(__file__))
fl_dir = os.path.dirname(script_dir)
working_dir = os.path.dirname(fl_dir)

excel_file = os.path.join(working_dir, "Ready_data","! PES PAPER", "Combined", "Combined Data.xlsx")
output_photo_file = os.path.join(working_dir, "Ready_data", "! PES PAPER", "Combined", "Impulse_10_All_Devices_Plot.png")


# ---------------------------------------------------------
# COMMAND SCHEDULE PARSER (C2 STYLE)
# ---------------------------------------------------------
def get_active_commands():
    """Reads command schedule to extract Load Up, Shed, and other DR event timings."""
    schedule_file = os.path.join(script_dir, "B0_Commands_Schedule.csv")
    commands = []
    
    try:
        df_sched = pd.read_csv(schedule_file)
        for _, row in df_sched.iterrows():
            if str(row.get('OnOff', '')).strip().upper() == 'ON':
                cmd_name = str(row['Command']).strip()
                
                # Calculate trapezoid time coordinates
                t0 = pd.to_datetime(str(row['START RAMP IN']).strip(), format='%H:%M')
                t1 = t0 + pd.Timedelta(hours=float(row['DURATION RAMP IN']))
                t2 = pd.to_datetime(str(row['START RAMP OUT']).strip(), format='%H:%M')
                t3 = t2 + pd.Timedelta(hours=float(row['DURATION RAMP OUT']))
                
                print(f"[{cmd_name}] Ramp In: {t0.strftime('%H:%M')} to {t1.strftime('%H:%M')} | "
                      f"Ramp Out: {t2.strftime('%H:%M')} to {t3.strftime('%H:%M')}")
                
                # Assign colors and labels based on command type
                if 'ALU' in cmd_name:
                    c_type, color = 'Advanced Load Up', "#00FF087C"
                elif 'LU' in cmd_name:
                    c_type, color = 'Load Up', "#0077FF85"
                elif 'CP' in cmd_name:
                    c_type, color = 'Critical Peak', "#FF660083"
                elif 'GE' in cmd_name:
                    c_type, color = 'Grid Emergency', "#FF00008F"
                elif 'S' in cmd_name:
                    c_type, color = 'Shed', "#FF00DD8D"
                else:
                    c_type, color = 'Other', '#9E9E9E'
                    
                commands.append({'type': c_type, 'color': color, 'times': [t0, t1, t2, t3]})
                
    except FileNotFoundError:
        print(f"[WARNING] Schedule file ({schedule_file}) not found. Proceeding without event overlays.")
    except Exception as e:
        print(f"[WARNING] Error reading schedule file: {e}")
        
    return commands


# ---------------------------------------------------------
# LOAD IMPULSE (10) DATA FROM EXCEL (ROWS 2-9)
# ---------------------------------------------------------
def load_impulse10_data(excel_path):
    """
    Parses Sheet1 of 'Combined Data.xlsx' for Impulse (10) rows 2 to 9:
    Row 2: Time
    Row 3: Baseline
    Row 4: All Devices
    Row 5: Water Heater
    Row 6: HVAC
    Row 7: Dryer
    Row 8: EV
    Row 9: Batteries
    """
    # Read raw headerless excel sheet
    df_raw = pd.read_excel(excel_path, sheet_name='Sheet1', header=None)
    
    # Extract rows 1 to 8 (Excel rows 2 to 9)
    # Row index 1 = Time, Row index 2..8 = Device consumption series
    time_series = df_raw.iloc[1, 1:].values
    
    # Create DataFrame with timestamps
    df = pd.DataFrame({'Time_Raw': time_series})
    df['Time'] = pd.to_datetime(df['Time_Raw'].astype(str), format='%H:%M:%S', errors='coerce')
    
    # Map row labels to DataFrame columns
    row_mapping = {
        2: 'Baseline',
        3: 'All Devices',
        4: 'Water Heater',
        5: 'HVAC',
        6: 'Dryer',
        7: 'EV',
        8: 'Batteries'
    }
    
    for row_idx, col_name in row_mapping.items():
        df[col_name] = pd.to_numeric(df_raw.iloc[row_idx, 1:].values, errors='coerce')
        
    return df


# ---------------------------------------------------------
# PLOTTING FUNCTION (C2 STYLE)
# ---------------------------------------------------------
def plot_impulse_data(df, schedule_commands, title, save_path):
    fig, ax1 = plt.subplots(figsize=(12, 6))

    # Line styling for primary axis (Device Consumption)
    styles = {
        'Baseline':     {'color': '#000000', 'linestyle': '--', 'linewidth': 2.5},
        'All Devices':  {'color': '#E26D28', 'linestyle': '-',  'linewidth': 2.5},
        'Water Heater': {'color': '#1F77B4', 'linestyle': '-',  'linewidth': 1.5},
        'HVAC':         {'color': '#2CA02C', 'linestyle': '-',  'linewidth': 1.5},
        'Dryer':        {'color': '#9467BD', 'linestyle': '-',  'linewidth': 1.5},
        'EV':           {'color': '#D62728', 'linestyle': '-',  'linewidth': 1.5},
        'Batteries':    {'color': '#17BECF', 'linestyle': '-',  'linewidth': 1.5},
    }

    # --- PRIMARY AXIS: Power Consumption ---
    for device, style in styles.items():
        if device in df.columns:
            ax1.plot(df['Time'], df[device], label=device, **style)

    ax1.set_ylabel('Power (kW)', fontsize=11)
    ax1.set_title(title, fontsize=13, fontweight='bold', pad=12)
    ax1.grid(True, alpha=0.3)

    # --- SECONDARY AXIS: Command Ramping (Load Up / Shed Overlays) ---
    ax2 = ax1.twinx()
    ax2.set_ylabel('Fraction of units given command', fontsize=11)
    ax2.set_ylim(0, 1)

    added_labels = set()
    for cmd in schedule_commands:
        y_vals = [0, 1, 1, 0]  # Trapezoid profile
        label = cmd['type'] if cmd['type'] not in added_labels else ""
        if label:
            added_labels.add(label)

        ax2.plot(cmd['times'], y_vals, color=cmd['color'], linewidth=1)
        ax2.fill_between(cmd['times'], y_vals, color=cmd['color'], alpha=0.15, label=label)

    # --- FORMATTING & LEGEND ---
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    plt.setp(ax1.get_xticklabels(), rotation=45, ha='right')

    # Combine legends from both axes at the bottom
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    
    ax1.legend(
        lines1 + lines2, 
        labels1 + labels2, 
        loc='upper center', 
        bbox_to_anchor=(0.5, -0.18), 
        ncol=4, 
        frameon=False,
        fontsize=10
    )

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"[INFO] Plot successfully saved to {save_path}")


# ---------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------
if __name__ == "__main__":
    # Load commands schedule for Load Up & Shed shading
    active_commands = get_active_commands()
    
    # Parse Excel data
    if os.path.exists(excel_file):
        df_impulse = load_impulse10_data(excel_file)
        
        # Plot Impulse (10) results across all devices
        plot_impulse_data(
            df=df_impulse, 
            schedule_commands=active_commands, 
            title='Average Impulse Response Across All Devices per Household (n=468)', 
            save_path=output_photo_file
        )
        
        plt.show()
    else:
        print(f"[ERROR] Excel file not found at: {excel_file}")