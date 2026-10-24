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

# SWITCH AT THE TOP: Choose "IMPULSE", "RAMPED", or "BOTH"
PLOT = "BOTH"
# PLOT = "IMPULSE"
# PLOT = "RAMPED"

script_dir = os.path.dirname(os.path.abspath(__file__))
fl_dir = os.path.dirname(script_dir)
working_dir = os.path.dirname(fl_dir)

excel_file = os.path.join(working_dir, "Ready_data", "! PES PAPER", "Combined", "Combined Data.xlsx")

# Determine output file path, title, and Excel sheet based on the PLOT switch
if PLOT.upper() == "IMPULSE":
    sheet_name = 'Sheet1'
    output_photo_file = os.path.join(working_dir, "Ready_data", "! PES PAPER", "Combined", "Impulse_10_All_Devices_Plot.pdf")
    plot_title = 'Average Impulse Response Across All Devices per Household (n=468)'
elif PLOT.upper() == "RAMPED":
    sheet_name = 'Sheet2'
    output_photo_file = os.path.join(working_dir, "Ready_data", "! PES PAPER", "Combined", "Ramped_23_All_Devices_Plot.pdf")
    plot_title = 'Average Ramped Response Across All Devices per Household (n=468)'
elif PLOT.upper() == "BOTH":
    output_photo_file = os.path.join(working_dir, "Ready_data", "! PES PAPER", "Combined", "Impulse_and_Ramped_All_Devices_Plot.pdf")
    plot_title_impulse = 'Average Impulse Response Across All Devices per Household (n=468)'
    plot_title_ramped = 'Average Ramped Response Across All Devices per Household (n=468)'
else:
    raise ValueError(f"Invalid PLOT option: '{PLOT}'. Must be 'IMPULSE', 'RAMPED', or 'BOTH'.")

# ---------------------------------------------------------
# COMMAND SCHEDULE PARSER (C2 STYLE)
# ---------------------------------------------------------
def get_active_commands(plot_type="IMPULSE"):
    """Reads command schedule to extract Load Up, Shed, and other DR event timings."""
    commands = []
    
    # Hardcoded constant DR event timings determined from B0 Commands Schedule
    if plot_type.upper() == "IMPULSE":
        # Impulse Event Timings (Step Functions)
        # Load Up Impulse: 13:00 to 16:00
        t0_lu = pd.to_datetime('13:00', format='%H:%M')
        t1_lu = pd.to_datetime('13:00', format='%H:%M')
        t2_lu = pd.to_datetime('16:00', format='%H:%M')
        t3_lu = pd.to_datetime('16:00', format='%H:%M')
        commands.append({'type': 'Load Up', 'color': "#0077FF85", 'times': [t0_lu, t1_lu, t2_lu, t3_lu]})

        # Shed Impulse: 16:00 to 21:00
        t0_s = pd.to_datetime('16:00', format='%H:%M')
        t1_s = pd.to_datetime('16:00', format='%H:%M')
        t2_s = pd.to_datetime('21:00', format='%H:%M')
        t3_s = pd.to_datetime('21:00', format='%H:%M')
        commands.append({'type': 'Shed', 'color': "#FF00DD8D", 'times': [t0_s, t1_s, t2_s, t3_s]})

    elif plot_type.upper() == "RAMPED":
        # Ramped Event Timings
        # Load Up Ramped: 07:00 to 19:00 with ramp durations
        t0_lu = pd.to_datetime('07:00', format='%H:%M')
        t1_lu = pd.to_datetime('10:00', format='%H:%M')  # 07:00 + 3 hrs ramp in
        t2_lu = pd.to_datetime('11:00', format='%H:%M')
        t3_lu = pd.to_datetime('19:00', format='%H:%M')  # 11:00 + 8 hrs ramp out
        commands.append({'type': 'Load Up', 'color': "#0077FF85", 'times': [t0_lu, t1_lu, t2_lu, t3_lu]})

        # Shed Ramped: 11:00 to 23:00 with ramp durations
        t0_s = pd.to_datetime('11:00', format='%H:%M')
        t1_s = pd.to_datetime('19:00', format='%H:%M')  # 11:00 + 8 hrs ramp in
        t2_s = pd.to_datetime('19:00', format='%H:%M')
        t3_s = pd.to_datetime('23:00', format='%H:%M')  # 19:00 + 4 hrs ramp out
        commands.append({'type': 'Shed', 'color': "#FF00DD8D", 'times': [t0_s, t1_s, t2_s, t3_s]})

    return commands


# ---------------------------------------------------------
# LOAD DATA FROM EXCEL
# ---------------------------------------------------------
def load_impulse10_data(excel_path, target_sheet='Sheet1'):
    """Parses specified sheet of 'Combined Data.xlsx' for device consumption series."""
    df_raw = pd.read_excel(excel_path, sheet_name=target_sheet, header=None)
    
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
        8: 'Battery'
    }
    
    for row_idx, col_name in row_mapping.items():
        df[col_name] = pd.to_numeric(df_raw.iloc[row_idx, 1:].values, errors='coerce')
        
    return df


# ---------------------------------------------------------
# PANEL PLOTTING HELPER
# ---------------------------------------------------------
def plot_panel(ax1, df, schedule_commands, title, show_legend=True, show_xticklabels=True):
    """Plots a single panel (Primary Power axis + Secondary Command Ramping axis)."""
    styles = {
        'Baseline':     {'color': '#000000', 'linestyle': '--', 'linewidth': 3.0, 'alpha': 1.0, 'zorder': 5},
        'All Devices':  {'color': '#E26D28', 'linestyle': '-',  'linewidth': 3.0, 'alpha': 1.0, 'zorder': 6},
        'Water Heater': {'color': '#1F77B4', 'linestyle': '-',  'linewidth': 2.0, 'alpha': 0.5},
        'HVAC':         {'color': '#2CA02C', 'linestyle': '-',  'linewidth': 2.0, 'alpha': 0.5},
        'Dryer':        {'color': '#9467BD', 'linestyle': '-',  'linewidth': 2.0, 'alpha': 0.5},
        'EV':           {'color': '#D62728', 'linestyle': '-',  'linewidth': 2.0, 'alpha': 0.5},
        'Battery':      {'color': '#17BECF', 'linestyle': '-',  'linewidth': 2.0, 'alpha': 0.5},
    }

    # --- PRIMARY AXIS: Power Consumption ---
    for device, style in styles.items():
        if device in df.columns:
            ax1.plot(df['Time'], df[device], label=device, **style)

    ax1.set_ylabel('Power (kW)', fontsize=13, fontweight='bold')
    ax1.set_title(title, fontsize=13, fontweight='bold', pad=12)
    ax1.grid(True, alpha=0.35, linestyle=':')
    ax1.set_ylim(0, 4.5)
    ax1.tick_params(axis='both', which='major', labelsize=11)

    # Set X-Axis limits (04:00 to 23:45 / Midnight)
    xmin = pd.to_datetime('04:00:00', format='%H:%M:%S')
    xmax = df['Time'].max()  # Automatically sets to the last time step (23:45:00)
    ax1.set_xlim(xmin, xmax)

    # --- SECONDARY AXIS: Command Ramping (Load Up / Shed) ---
    ax2 = ax1.twinx()
    ax2.set_ylabel('Fraction of units given command', fontsize=13, fontweight='bold')
    ax2.set_ylim(0, 1.0)
    ax2.tick_params(axis='y', which='major', labelsize=11)

    added_labels = set()
    for cmd in schedule_commands:
        y_vals = [0, 1, 1, 0]  # Trapezoid profile
        label = cmd['type'] if cmd['type'] not in added_labels else ""
        if label:
            added_labels.add(label)

        ax2.plot(cmd['times'], y_vals, color=cmd['color'], linewidth=1.5)
        ax2.fill_between(cmd['times'], y_vals, color=cmd['color'], alpha=0.20, label=label)

    # --- FORMATTING & LEGEND ---
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    
    if show_xticklabels:
        plt.setp(ax1.get_xticklabels(), rotation=35, ha='right')
    else:
        plt.setp(ax1.get_xticklabels(), visible=False)

    if show_legend:
        # Combine legends cleanly at the bottom
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        
        ax1.legend(
            lines1 + lines2, 
            labels1 + labels2, 
            loc='upper center', 
            bbox_to_anchor=(0.5, -0.22), 
            ncol=3, 
            frameon=True,
            facecolor='#F9F9F9',
            edgecolor='#E0E0E0',
            fontsize=11
        )


# ---------------------------------------------------------
# HIGH-READABILITY PLOTTING FUNCTION
# ---------------------------------------------------------
def plot_impulse_data(excel_path, mode, save_path):
    if mode.upper() in ["IMPULSE", "RAMPED"]:
        # Single Plot Mode
        fig, ax1 = plt.subplots(figsize=(8.5, 5.0), dpi=300)
        
        active_commands = get_active_commands(plot_type=mode)
        target_sheet = 'Sheet1' if mode.upper() == "IMPULSE" else 'Sheet2'
        df_data = load_impulse10_data(excel_path, target_sheet=target_sheet)
        
        plot_panel(ax1, df_data, active_commands, plot_title, show_legend=True, show_xticklabels=True)
        
    elif mode.upper() == "BOTH":
        # Subplot Mode: Impulse (Top) above Ramped (Bottom)
        fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(8.5, 9.5), dpi=300)
        
        # Top Subplot: Impulse
        df_impulse = load_impulse10_data(excel_path, target_sheet='Sheet1')
        commands_impulse = get_active_commands(plot_type="IMPULSE")
        plot_panel(ax_top, df_impulse, commands_impulse, plot_title_impulse, show_legend=False, show_xticklabels=True)
        
        # Bottom Subplot: Ramped
        df_ramped = load_impulse10_data(excel_path, target_sheet='Sheet2')
        commands_ramped = get_active_commands(plot_type="RAMPED")
        plot_panel(ax_bot, df_ramped, commands_ramped, plot_title_ramped, show_legend=True, show_xticklabels=True)

    plt.tight_layout()
    
    # Save both vector PDF (for LaTeX/Word sharp rendering) and high-DPI PNG
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    png_path = save_path.replace('.pdf', '.png')
    plt.savefig(png_path, dpi=300, bbox_inches='tight')
    
    print(f"[INFO] Saved high-readability PDF to {save_path}")
    print(f"[INFO] Saved high-readability PNG to {png_path}")


# ---------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------
if __name__ == "__main__":
    # Parse Excel data and plot based on selected PLOT mode
    if os.path.exists(excel_file):
        plot_impulse_data(
            excel_path=excel_file,
            mode=PLOT,
            save_path=output_photo_file
        )
        
        plt.show()
    else:
        print(f"[ERROR] Excel file not found at: {excel_file}")