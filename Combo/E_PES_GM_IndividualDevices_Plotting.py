"""
Author: Thomas Metzler (Updated)
Date: 10/23/2026

Description:
Reads Baseline vs. Controlled power consumption CSV files from individual device subfolders
within 'Ready_data/! PES PAPER/IEEE_PES_GM_27_[Device]_2/' (2 directories above script location).
Aggregates end-uses into 'All Devices' for an Impulse Command scenario (n=468 households).

Plots each device (and All Devices) comparing Baseline (black dashed line) vs. Controlled 
(colored solid line) alongside secondary y-axis Demand Response overlays (Load Up & Shed)
in the C2 plotting format.
"""

import os
import datetime as dt
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

# ---------------------------------------------------------
# DIRECTORY & FILE SETUP
# ---------------------------------------------------------

# CHOOSE PLOT MODE:
# "GRID"        : 3x2 grid showing 'All Devices' + 5 individual end-uses
# "ALL_DEVICES" : Single panel plot for aggregated 'All Devices' only
# "INDIVIDUAL"  : Generates separate individual plot files for each device
PLOT_MODE = "INDIVIDUAL"  

script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()

# Navigate 2 directories up to project root
fl_dir = os.path.dirname(script_dir)
working_dir = os.path.dirname(fl_dir)

# Base PES Paper directory
pes_paper_dir = os.path.join(working_dir, "Ready_data", "! PES PAPER")
output_dir = os.path.join(pes_paper_dir, "Combined")

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

# Device configuration: subfolder names, file names, colors, and Y-axis limits
DEVICE_CONFIG = {
    'Water Heater': {
        'folder': 'IEEE_PES_GM_27_WH_Impulse_2',
        'baseline': 'IEEE_PES_GM_27_WH_Impulse_2_baseline_WH_power.csv',
        'controlled': 'IEEE_PES_GM_27_WH_Impulse_2_controlled_WH_power.csv',
        'color': '#1F77B4',  # Blue
        'ylim': (0, 0.5)
    },
    'HVAC': {
        'folder': 'IEEE_PES_GM_27_HVAC_Impulse_2',
        'baseline': 'IEEE_PES_GM_27_HVAC_Impulse_2_baseline_AC_power.csv',
        'controlled': 'IEEE_PES_GM_27_HVAC_Impulse_2_controlled_AC_power.csv',
        'color': '#2CA02C',  # Green
        'ylim': (0, 2.0)
    },
    'Dryer': {
        'folder': 'IEEE_PES_GM_27_Dryer_Impulse_2',
        'baseline': 'IEEE_PES_GM_27_Dryer_Impulse_2_baseline_Dryer_power.csv',
        'controlled': 'IEEE_PES_GM_27_Dryer_Impulse_2_controlled_Dryer_power.csv',
        'color': '#9467BD',  # Purple
        'ylim': (0, 0.45)
    },
    'EV': {
        'folder': 'IEEE_PES_GM_27_EV_Impulse_2',
        'baseline': 'IEEE_PES_GM_27_EV_Impulse_2_baseline_EV_power.csv',
        'controlled': 'IEEE_PES_GM_27_EV_Impulse_2_controlled_EV_power.csv',
        'color': '#D62728',  # Red
        'ylim': (0, 1.1)
    },
    'Battery': {
        'folder': 'IEEE_PES_GM_27_Battery_Impulse_2',
        'baseline': 'IEEE_PES_GM_27_Battery_Impulse_2_baseline_BATT_power.csv',
        'controlled': 'IEEE_PES_GM_27_Battery_Impulse_2_controlled_BATT_power.csv',
        'color': '#E6AB02',  # Yellow
        'ylim': (-0.35, 0.35)
    }
}


# ---------------------------------------------------------
# COMMAND SCHEDULE PARSER (C2 STYLE)
# ---------------------------------------------------------
def get_active_commands():
    """Reads command schedule to extract Load Up and Shed Impulse DR event timings."""
    commands = []
    
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

    return commands


# ---------------------------------------------------------
# LOAD DATA FROM DEVICE SUBDIRECTORIES
# ---------------------------------------------------------
def load_all_impulse_data(base_path):
    """
    Loads baseline and controlled CSV files from each device folder.
    Computes household averages (n=468) and constructs aggregate 'All Devices'.
    """
    processed_data = {}
    time_series = None

    for dev_name, config in DEVICE_CONFIG.items():
        dev_folder = os.path.join(base_path, config['folder'])
        base_csv = os.path.join(dev_folder, config['baseline'])
        ctrl_csv = os.path.join(dev_folder, config['controlled'])
        
        if not os.path.exists(base_csv):
            raise FileNotFoundError(f"[ERROR] Could not find baseline CSV file at: {base_csv}")
        if not os.path.exists(ctrl_csv):
            raise FileNotFoundError(f"[ERROR] Could not find controlled CSV file at: {ctrl_csv}")

        df_base = pd.read_csv(base_csv)
        df_ctrl = pd.read_csv(ctrl_csv)

        # Get time columns (excluding 'Home' column)
        time_cols = [col for col in df_base.columns if col.upper() != 'HOME']
        
        if time_series is None:
            time_series = pd.to_datetime(time_cols, format='%H:%M')

        # Calculate average across households (n=468)
        mean_base = df_base[time_cols].mean(axis=0).values
        mean_ctrl = df_ctrl[time_cols].mean(axis=0).values

        processed_data[dev_name] = {
            'baseline': mean_base,
            'controlled': mean_ctrl
        }

    # Sum all 5 end-uses to construct aggregate 'All Devices'
    all_base = np.sum([processed_data[dev]['baseline'] for dev in DEVICE_CONFIG], axis=0)
    all_ctrl = np.sum([processed_data[dev]['controlled'] for dev in DEVICE_CONFIG], axis=0)

    processed_data['All Devices'] = {
        'baseline': all_base,
        'controlled': all_ctrl
    }

    df_out = pd.DataFrame({'Time': time_series})
    for dev, vals in processed_data.items():
        df_out[f'{dev}_Baseline'] = vals['baseline']
        df_out[f'{dev}_Controlled'] = vals['controlled']

    return df_out


# ---------------------------------------------------------
# PANEL PLOTTING HELPER
# ---------------------------------------------------------
def plot_panel(ax1, df, dev_name, line_color, ylim=None, title=None, show_legend=True, show_xticklabels=True):
    """
    Plots a single panel: Primary axis for Baseline vs Controlled power + Secondary axis for DR Commands.
    """
    schedule_commands = get_active_commands()

    # --- PRIMARY AXIS: Power Consumption ---
    baseline_col = f'{dev_name}_Baseline'
    controlled_col = f'{dev_name}_Controlled'

    ax1.plot(df['Time'], df[baseline_col], label='Baseline', color='#000000', 
             linestyle='--', linewidth=2.5, alpha=0.95, zorder=5)
    ax1.plot(df['Time'], df[controlled_col], label='Controlled', color=line_color, 
             linestyle='-', linewidth=2.5, alpha=0.95, zorder=6)

    ax1.set_ylabel('Power (kW)', fontsize=11, fontweight='bold')
    panel_title = title if title else f'{dev_name} Impulse Response (n=468)'
    ax1.set_title(panel_title, fontsize=12, fontweight='bold', pad=10)
    ax1.grid(True, alpha=0.35, linestyle=':')
    
    if ylim:
        ax1.set_ylim(ylim)

    ax1.tick_params(axis='both', which='major', labelsize=10)

    xmin = pd.to_datetime('04:00:00', format='%H:%M:%S')
    xmax = df['Time'].max()  # Automatically sets to the last time step (23:45:00)
    ax1.set_xlim(xmin, xmax)


    # # --- SECONDARY AXIS: Command Ramping (Load Up / Shed) ---
    ax2 = ax1.twinx()
    # ax2.set_ylabel('Fraction of units commanded', fontsize=10, fontweight='bold', color='#555555')
    ax2.set_ylim(0, 1)
    ax2.set_yticks([])
    # ax2.tick_params(axis='y', which='major', labelsize=9, colors='#555555')

    added_labels = set()
    for cmd in schedule_commands:
        y_vals = [0, 1, 1, 0]  # Step profile
        label = cmd['type'] if cmd['type'] not in added_labels else ""
        if label:
            added_labels.add(label)

        ax2.plot(cmd['times'], y_vals, color=cmd['color'], linewidth=1.2, linestyle=':')
        ax2.fill_between(cmd['times'], y_vals, color=cmd['color'], alpha=0.18, label=label)

    # --- FORMATTING & LEGEND ---
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))

    if show_xticklabels:
        plt.setp(ax1.get_xticklabels(), rotation=35, ha='right')
    else:
        plt.setp(ax1.get_xticklabels(), visible=False)

    if show_legend:
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        
        ax1.legend(
            lines1 + lines2, 
            labels1 + labels2, 
            loc='upper center', 
            bbox_to_anchor=(0.5, -0.28 if show_xticklabels else -0.15), 
            ncol=4, 
            frameon=True,
            facecolor='#F9F9F9',
            edgecolor='#E0E0E0',
            fontsize=10
        )


# ---------------------------------------------------------
# MAIN EXECUTION & RENDERER
# ---------------------------------------------------------
def generate_impulse_plots(base_pes_dir, save_dir, mode="GRID"):
    df_data = load_all_impulse_data(base_pes_dir)

    if mode.upper() == "GRID":
        # 3 Rows x 2 Columns Grid Plot
        fig, axes = plt.subplots(3, 2, figsize=(8.5, 5), dpi=300)
        axes = axes.flatten()

        panels = [
            ('All Devices', '#E26D28', (0, 3.3)),
            ('Water Heater', DEVICE_CONFIG['Water Heater']['color'], DEVICE_CONFIG['Water Heater']['ylim']),
            ('HVAC', DEVICE_CONFIG['HVAC']['color'], DEVICE_CONFIG['HVAC']['ylim']),
            ('Dryer', DEVICE_CONFIG['Dryer']['color'], DEVICE_CONFIG['Dryer']['ylim']),
            ('EV', DEVICE_CONFIG['EV']['color'], DEVICE_CONFIG['EV']['ylim']),
            ('Battery', DEVICE_CONFIG['Battery']['color'], DEVICE_CONFIG['Battery']['ylim']),
        ]

        for idx, (dev_name, color, ylim) in enumerate(panels):
            ax = axes[idx]
            plot_panel(
                ax, df_data, dev_name, line_color=color, ylim=ylim,
                title=f"{dev_name}: Baseline vs. Controlled",
                show_legend=(idx == 0),
                show_xticklabels=True
            )

        fig.suptitle('Impulse Response Scenario (10) — Baseline vs. Controlled Across All Devices (n=468)', 
                     fontsize=14, fontweight='bold', y=0.995)
        plt.tight_layout()
        
        pdf_path = os.path.join(save_dir, "Impulse_Baseline_vs_Controlled_Grid.pdf")
        png_path = os.path.join(save_dir, "Impulse_Baseline_vs_Controlled_Grid.png")
        plt.savefig(pdf_path, dpi=300, bbox_inches='tight')
        plt.savefig(png_path, dpi=300, bbox_inches='tight')
        print(f"[INFO] Saved Grid Plot PDF: {pdf_path}")
        print(f"[INFO] Saved Grid Plot PNG: {png_path}")

    elif mode.upper() == "ALL_DEVICES":
        fig, ax = plt.subplots(figsize=(9.0, 5.5), dpi=300)
        plot_panel(ax, df_data, 'All Devices', line_color='#E26D28', ylim=(0, 3.3),
                   title='Average Impulse Response: All Devices per Household (n=468)',
                   show_legend=True, show_xticklabels=True)
        
        plt.tight_layout()
        pdf_path = os.path.join(save_dir, "Impulse_Baseline_vs_Controlled_All_Devices.pdf")
        png_path = os.path.join(save_dir, "Impulse_Baseline_vs_Controlled_All_Devices.png")
        plt.savefig(pdf_path, dpi=300, bbox_inches='tight')
        plt.savefig(png_path, dpi=300, bbox_inches='tight')
        print(f"[INFO] Saved All Devices PDF: {pdf_path}")
        print(f"[INFO] Saved All Devices PNG: {png_path}")

    elif mode.upper() == "INDIVIDUAL":
        devices_to_plot = [('All Devices', '#E26D28', (0, 3.3))] + [
            (dev, cfg['color'], cfg['ylim']) for dev, cfg in DEVICE_CONFIG.items()
        ]

        for dev_name, color, ylim in devices_to_plot:
            fig, ax = plt.subplots(figsize=(6.5, 3.0), dpi=300)
            plot_panel(ax, df_data, dev_name, line_color=color, ylim=ylim,
                       title=f'{dev_name} Average Impulse Response (n=468)',
                       show_legend=True, show_xticklabels=True)
            
            plt.tight_layout()
            clean_name = dev_name.replace(' ', '_')
            pdf_path = os.path.join(save_dir, f"Impulse_Baseline_vs_Controlled_{clean_name}.pdf")
            png_path = os.path.join(save_dir, f"Impulse_Baseline_vs_Controlled_{clean_name}.png")
            plt.savefig(pdf_path, dpi=300, bbox_inches='tight')
            plt.savefig(png_path, dpi=300, bbox_inches='tight')
            plt.close(fig)
            print(f"[INFO] Saved {dev_name} Plot: {pdf_path}")


if __name__ == "__main__":
    generate_impulse_plots(
        base_pes_dir=pes_paper_dir,
        save_dir=output_dir,
        mode=PLOT_MODE  # Options: "GRID", "ALL_DEVICES", or "INDIVIDUAL"
    )
    plt.show()