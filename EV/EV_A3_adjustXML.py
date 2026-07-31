"""
Author: Thomas Metzler
Adjusts EV properties in the XML file that OCHRE will read.
Updated to dynamically convert all systems to EV chargers, assign 
metadata-linked vehicles, and configure matching service feeders and branch circuits.
Enforces strict HPXML XSD schema sequence via node sorting.
"""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
import re
import random
import pandas as pd

# ---------------------------------------------------------
# DIRECTORY SETUP
# ---------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
FL_DIR = SCRIPT_DIR.parent 
WORKING_DIR = FL_DIR.parent

INPUT_DIR = WORKING_DIR / "All Portland Input Files"
OUTPUT_DIR = WORKING_DIR / "EV All Portland Input Files"

METADATA_DIR = WORKING_DIR / "Metadata" / "OR_upgrade0.csv"

# ---------------------------------------------------------
# CONFIGURATIONS
# ---------------------------------------------------------

# Load metadata once globally
metadata_df = pd.read_csv(METADATA_DIR, low_memory=False)

# EV Conversion Config to control adoption rates
EV_CONVERSION_CONFIG = {
    # Distribution of charger levels. Should sum to 1.0.
    "ChargerAdoptionRates": {
        "Level1": 1,
        "Level2": 0,
        "None": 0
    },
    
    # Details for the Service Feeders and Branch Circuits for EV chargers
    "ChargerDetails": {
        "1": {
            "ChargingPower": "1600.0",
            "Voltage": "120",
            "MaxCurrentRating": "20.0",
            "OccupiedSpaces": "1.0",
        },
        "2": {
            "ChargingPower": "5690.0",
            "Voltage": "240",
            "MaxCurrentRating": "50.0",
            "OccupiedSpaces": "2.0",
        }
    },

    # Predefined Vehicle Types Specs
    "VehicleSpecs": {
        "SUV, Battery Electric Vehicle, 200 mile range": {
            "NominalCapacity": "66.88", "UsableCapacity": "53.503", "FuelEconomy": "0.267513"
        },
        "Pickup, Battery Electric Vehicle, 300 mile range": {
            "NominalCapacity": "132.43", "UsableCapacity": "105.946", "FuelEconomy": "0.373794"
        },
        "SUV, Battery Electric Vehicle, 300 mile range": {
            "NominalCapacity": "104.6", "UsableCapacity": "83.68", "FuelEconomy": "0.278934"
        },
        "Compact, Battery Electric Vehicle, 300 mile range": {
            "NominalCapacity": "79.29", "UsableCapacity": "63.433", "FuelEconomy": "0.22002"
        },
        "Midsize, Battery Electric Vehicle, 300 mile range": {
            "NominalCapacity": "81.8", "UsableCapacity": "65.441", "FuelEconomy": "0.229449"
        },
        "Compact, Battery Electric Vehicle, 200 mile range": {
            "NominalCapacity": "50.21", "UsableCapacity": "40.168", "FuelEconomy": "0.209901"
        },
        "Midsize, Battery Electric Vehicle, 200 mile range": {
            "NominalCapacity": "52.47", "UsableCapacity": "41.978", "FuelEconomy": "0.219174"
        }
    }
}

# ---------------------------------------------------------
# HPXML SCHEMA SORTING LISTS
# ---------------------------------------------------------
# Ensures elements appended to <Systems> obey exact schema ordering
SYSTEMS_ORDER = [
    "SystemIdentifier",
    "HVAC",
    "MechanicalVentilation",
    "CombustionVentilation",
    "WaterHeating",
    "SolarThermal",
    "Photovoltaics",
    "ElectricPanels",
    "ElectricalLoadCenter",
    "Batteries",
    "Vehicles",
    "ElectricVehicleChargers",
    "Generators",
    "Pools",
    "PermanentSpas",
    "HotTubs",
    "PlugLoads",
    "FuelLoads"
]

ELEC_ORDER = [
    "SystemIdentifier",
    "Voltage",
    "MaximumCurrentRating",
    "Capacity",
    "OccupiedSpaces",
    "TotalSpaces",
    "BranchCircuits",
    "BranchCircuit",
    "ServiceFeeders",
    "ServiceFeeder"
]

# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def sort_hpxml_node(node, order_list):
    """Sorts the children of an XML node based on a standardized schema order."""
    if node is None:
        return
    
    def get_order(child):
        tag_name = child.tag.split('}')[-1]
        try:
            return order_list.index(tag_name)
        except ValueError:
            return len(order_list) # Unknown tags go to the end
            
    # Re-order the elements internally
    node[:] = sorted(node, key=get_order)

def parse_charge_fraction(val):
    if pd.isna(val): return 0.9
    val = str(val).lower()
    if '100' in val: return 1.0
    if '80-99' in val: return 0.9
    if '60-79' in val: return 0.7
    if '40-59' in val: return 0.5
    if '20-39' in val: return 0.3
    if '0-19' in val: return 0.1
    return 0.9 # Default fallback

def get_building_metadata(bldg_id):
    row = metadata_df[metadata_df['bldg_id'] == int(bldg_id)]
    if row.empty:
        return None
    return row.iloc[0]

def add_ev_components(root, ns, ns_bracket, bldg_id, config):
    meta = get_building_metadata(bldg_id)
    if meta is None:
        print(f"[Warning] Bldg {bldg_id}: Metadata row not found. Skipping.")
        return
    
    # 1. Determine Charger Level
    rand_val = random.random()
    rates = config["ChargerAdoptionRates"]
    if rand_val < rates["Level1"]:
        charger_level = "1"
    elif rand_val < rates["Level1"] + rates["Level2"]:
        charger_level = "2"
    else:
        return # No charger chosen

    charger_config = config["ChargerDetails"][charger_level]
    
    # Extract Metadata
    veh_type = meta.get('in.electric_vehicle_battery', None)
    
    # NEW: Clean string to avoid silent mismatches due to hidden spaces in CSV
    if isinstance(veh_type, str):
        veh_type = veh_type.strip()
        
    miles_yr = meta.get('in.electric_vehicle_miles_traveled', 11000.0)
    charge_loc = meta.get('in.electric_vehicle_charge_at_home', '80-99%')
    
    # NEW: Print exactly what is triggering the skip if the vehicle type doesn't match
    if pd.isna(veh_type) or veh_type not in config["VehicleSpecs"]:
        print(f"[Warning] Bldg {bldg_id}: veh_type '{veh_type}' missing or not in config. Skipping.")
        return
    
    veh_specs = config["VehicleSpecs"][veh_type]
    charge_frac = parse_charge_fraction(charge_loc)
    
    # Average driving speed is 22mph (derived from matching hours to miles from sample data)
    hours_week = float(miles_yr) / 365.0 * 7.0 / 22.0

    # --- 2. Find Correct Parent Node (Systems) ---
    # HPXML standard places EV elements inside <Systems>
    parent_node = root.find(f'.//{ns}Systems')
    
    # Fallback to BuildingDetails if Systems somehow doesn't exist
    if parent_node is None:
        parent_node = root.find(f'.//{ns}BuildingDetails')
        
    if parent_node is None:
        print(f"[Warning] Bldg {bldg_id}: Neither <Systems> nor <BuildingDetails> found. Skipping.")
        return

    # --- 3. Create or Locate Elements Independently ---
    vehicles_node = root.find(f'.//{ns}Vehicles')
    if vehicles_node is None:
        vehicles_node = ET.Element(f'{ns}Vehicles')
    else:
        for child in list(vehicles_node):
            vehicles_node.remove(child)

    chargers_node = root.find(f'.//{ns}ElectricVehicleChargers')
    charger_id = 'EVCharger1'
    if chargers_node is None:
        chargers_node = ET.Element(f'{ns}ElectricVehicleChargers')
    else:
        for child in list(chargers_node):
            chargers_node.remove(child)

    # --- 4. Build Charger Properties ---
    charger_elem = ET.SubElement(chargers_node, f'{ns}ElectricVehicleCharger')
    ET.SubElement(charger_elem, f'{ns}SystemIdentifier', id=charger_id)
    ET.SubElement(charger_elem, f'{ns}ChargingLevel').text = charger_level
    ET.SubElement(charger_elem, f'{ns}ChargingPower').text = charger_config["ChargingPower"]

    # --- 5. Build Vehicle Properties ---
    veh_elem = ET.SubElement(vehicles_node, f'{ns}Vehicle')
    ET.SubElement(veh_elem, f'{ns}SystemIdentifier', id='Vehicle1')
    
    veh_type_elem = ET.SubElement(veh_elem, f'{ns}VehicleType')
    bev = ET.SubElement(veh_type_elem, f'{ns}BatteryElectricVehicle')
    
    batt = ET.SubElement(bev, f'{ns}Battery')
    ET.SubElement(batt, f'{ns}BatteryType').text = 'Li-ion'
    
    nom = ET.SubElement(batt, f'{ns}NominalCapacity')
    ET.SubElement(nom, f'{ns}Units').text = 'kWh'
    ET.SubElement(nom, f'{ns}Value').text = veh_specs["NominalCapacity"]
    
    usable = ET.SubElement(batt, f'{ns}UsableCapacity')
    ET.SubElement(usable, f'{ns}Units').text = 'kWh'
    ET.SubElement(usable, f'{ns}Value').text = veh_specs["UsableCapacity"]
    
    ET.SubElement(batt, f'{ns}NominalVoltage').text = '50.0'
    
    fcl = ET.SubElement(bev, f'{ns}FractionChargedLocation')
    ET.SubElement(fcl, f'{ns}Location').text = 'Home'
    ET.SubElement(fcl, f'{ns}Percentage').text = str(charge_frac)
    
    ET.SubElement(bev, f'{ns}ConnectedCharger', idref=charger_id)
    
    ext = ET.SubElement(bev, f'{ns}extension')
    ET.SubElement(ext, f'{ns}WeekdayScheduleFractions').text = "0.0714, 0.0714, 0.0714, 0.0714, 0.0714, 0.0714, 0.0714, -0.3535, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.3221, -0.3244, 0.0714, 0.0714, 0.0714, 0.0714, 0.0714, 0.0714, 0.0714"
    ET.SubElement(ext, f'{ns}WeekendScheduleFractions').text = "0.0588, 0.0588, 0.0588, 0.0588, 0.0588, 0.0588, 0.0588, 0.0588, 0.0588, -0.3334, 0, 0, 0, 0, -0.3293, -0.3372, 0.0588, 0.0588, 0.0588, 0.0588, 0.0588, 0.0588, 0.0588, 0.0588"
    ET.SubElement(ext, f'{ns}MonthlyScheduleMultipliers').text = "1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0"
    
    ET.SubElement(veh_elem, f'{ns}MilesDrivenPerYear').text = str(miles_yr)
    ET.SubElement(veh_elem, f'{ns}HoursDrivenPerWeek').text = str(hours_week)
    
    fec = ET.SubElement(veh_elem, f'{ns}FuelEconomyCombined')
    ET.SubElement(fec, f'{ns}Units').text = 'kWh/mile'
    ET.SubElement(fec, f'{ns}Value').text = veh_specs["FuelEconomy"]

    # --- 6. Append & Enforce Schema Order on Systems Node ---
    if vehicles_node not in list(parent_node):
        parent_node.append(vehicles_node)
    if chargers_node not in list(parent_node):
        parent_node.append(chargers_node)
        
    sort_hpxml_node(parent_node, SYSTEMS_ORDER)

    # --- 7. Service Feeder & Branch Circuit ---
    circuit_parent = root.find(f'.//{ns}ElectricalLoadCenter')
    
    # Fallback for newer HPXML versions utilizing ElectricPanels
    if circuit_parent is None:
        circuit_parent = root.find(f'.//{ns}ElectricPanel')
    
    if circuit_parent is not None:
        # Determine targets (some HPXML versions use wrapper nodes, some don't)
        branch_wrapper = circuit_parent.find(f'{ns}BranchCircuits')
        circuit_target = branch_wrapper if branch_wrapper is not None else circuit_parent
        
        feeder_wrapper = circuit_parent.find(f'{ns}ServiceFeeders')
        feeder_target = feeder_wrapper if feeder_wrapper is not None else circuit_parent

        all_circuits = root.findall(f'.//{ns}BranchCircuit')
        max_c_num = max([int(re.search(r'\d+', c.find(f'{ns}SystemIdentifier').get('id', '0')).group()) for c in all_circuits if c.find(f'{ns}SystemIdentifier') is not None] + [0])
        circuit_exists = any(c.find(f'{ns}AttachedToComponent') is not None and c.find(f'{ns}AttachedToComponent').get('idref') == charger_id for c in all_circuits)
        
        # Insert Branch Circuit first to respect schema load center sequence
        if not circuit_exists:
            new_circuit = ET.SubElement(circuit_target, f'{ns}BranchCircuit')
            ET.SubElement(new_circuit, f'{ns}SystemIdentifier', id=f'BranchCircuit{max_c_num + 1}')
            ET.SubElement(new_circuit, f'{ns}Voltage').text = charger_config["Voltage"]
            ET.SubElement(new_circuit, f'{ns}MaximumCurrentRating').text = charger_config["MaxCurrentRating"]
            ET.SubElement(new_circuit, f'{ns}OccupiedSpaces').text = charger_config["OccupiedSpaces"]
            ET.SubElement(new_circuit, f'{ns}AttachedToComponent', idref=charger_id)

        all_feeders = root.findall(f'.//{ns}ServiceFeeder')
        max_f_num = max([int(re.search(r'\d+', f.find(f'{ns}SystemIdentifier').get('id', '0')).group()) for f in all_feeders if f.find(f'{ns}SystemIdentifier') is not None] + [0])
        feeder_exists = any(f.find(f'{ns}AttachedToComponent') is not None and f.find(f'{ns}AttachedToComponent').get('idref') == charger_id for f in all_feeders)
        
        if not feeder_exists:
            new_feeder = ET.SubElement(feeder_target, f'{ns}ServiceFeeder')
            ET.SubElement(new_feeder, f'{ns}SystemIdentifier', id=f'ServiceFeeder{max_f_num + 1}')
            ET.SubElement(new_feeder, f'{ns}LoadType').text = 'electric vehicle charging'
            ET.SubElement(new_feeder, f'{ns}PowerRating').text = charger_config["ChargingPower"]
            ET.SubElement(new_feeder, f'{ns}IsNewLoad').text = "false"
            ET.SubElement(new_feeder, f'{ns}AttachedToComponent', idref=charger_id)

        # Enforce exact XML child sequence on the Electric Panel/Load Center 
        sort_hpxml_node(circuit_parent, ELEC_ORDER)

def convert_to_ev_from_metadata(root, xml_filename, config):
    """Parses bldg_id from filename and routes to ev component adder"""
    ns_match = re.match(r'\{.*\}', root.tag)
    ns_bracket = ns_match.group(0) if ns_match else ''
    
    # Assumes filename contains the building ID (e.g. bldg000030.xml -> 30)
    match = re.search(r'\d+', xml_filename.stem)
    if match:
        bldg_id = match.group()
        add_ev_components(root, ns_bracket, ns_bracket, bldg_id, config)

# ---------------------------------------------------------
# DUPLICATION LOGIC
# ---------------------------------------------------------
def duplicate_directories(input_dir, output_dir):
    """Safely copies the entire directory structure over."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    if not input_path.exists():
        print(f"Error: Could not find input directory at {input_path.resolve()}")
        return False

    print(f"Copying files from '{input_path.name}' to '{output_path.name}'...")
    if output_path.exists():
        shutil.copytree(input_path, output_path, dirs_exist_ok=True)
    else:
        shutil.copytree(input_path, output_path)
    return True

# ---------------------------------------------------------
# MAIN EXECUTION BLOCK
# ---------------------------------------------------------
if __name__ == "__main__":
    print("Starting OCHRE HPXML batch update...")
    
    # 1. Duplicate the directory once
    success = duplicate_directories(INPUT_DIR, OUTPUT_DIR)
    
    if success:
        # 2. Iterate through the newly created output directory
        output_path = Path(OUTPUT_DIR)
        
        for xml_file in output_path.rglob('*.xml'):
            try:
                for event, (prefix, uri) in ET.iterparse(xml_file, events=['start-ns']):
                    ET.register_namespace(prefix, uri)
                
                tree = ET.parse(xml_file)
                root = tree.getroot()
                
                # ==========================================
                # TURN YOUR UPDATES ON OR OFF HERE
                # ==========================================
                
                
                # convert_to_electric_dryer(root, DRYER_CONVERSION_CONFIG)
                
                # NEW EV CONVERSION FUNCTION
                convert_to_ev_from_metadata(root, xml_file, EV_CONVERSION_CONFIG)
                
                # ==========================================
                
                if hasattr(ET, 'indent'):
                    ET.indent(tree, space="  ", level=0)

                tree.write(xml_file, encoding='UTF-8', xml_declaration=True)
                
            except ET.ParseError as e:
                print(f"Failed to parse XML for {xml_file}: {e}")
            except Exception as e:
                print(f"An error occurred while processing {xml_file}: {e}")

        print("Batch update complete.")