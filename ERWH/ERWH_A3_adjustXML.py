"""
Author: Thomas Metzler
6/28/2026

Adjusts ERWH properties in the XML file that OCHRE will read.
Updated to assign ERWH sizes based on a requested percentage distribution,
and handle conversion of HPWH, Gas, and Tankless heaters to standard ERWH.
"""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
import re
import random  # Added for the distribution function

# ---------------------------------------------------------
# DIRECTORY SETUP
# ---------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
FL_DIR = SCRIPT_DIR.parent 
WORKING_DIR = FL_DIR.parent

INPUT_DIR = WORKING_DIR / "All Portland Input Files"
OUTPUT_DIR = WORKING_DIR / "ERWH All Portland Input Files"

# ---------------------------------------------------------
# CONFIGURATIONS
# ---------------------------------------------------------
ERWH_SIZE_CONFIG = {
    "ERWH_size": {
        # Current Volume : {"TankVolume": New Volume, "HeatingCapacity": New Capacity (BTU/hr)}
        30.0: {"TankVolume": 50.0, "HeatingCapacity": 18767.0, "EnergyFactor": 0.92},
        50.0: {"TankVolume": 66.0, "HeatingCapacity": 18767.0, "EnergyFactor": 0.92},
        66.0: {"TankVolume": 80.0, "HeatingCapacity": 18767.0, "EnergyFactor": 0.92}
    },
}

ERWH_CONVERSION_CONFIG = {
    "ERWH_Conversion": {
        "NewType": "storage water heater",
        "NewFuelType": "electricity",
        "DefaultTankVolume": "50.0", # Used if converting from Tankless
        "HeatingCapacity": "18767.0",
        "EnergyFactor": "0.92",
        "RecoveryEfficiency": "0.98",
        # Tags that exist in other heaters but break the schema for standard ERWH
        "ElementsToRemove": [
            "BackupHeatingCapacity", 
            "UniformEnergyFactor", 
            "HPWHOperatingMode", 
            "UsageBin",
            "EnergyFactor",       # Cleared to prevent duplicates if converting from Gas
            "RecoveryEfficiency", # Cleared to prevent duplicates if converting from Gas
            "FirstHourRating"
        ]
    }
}

#Adjust weights for each size to be randomly distributed
ERWH_SIZE_DISTRIB_CONFIG = {
    "ERWH_size_distrib": [
        {"weight": 0.50, "TankVolume": 50.0, "HeatingCapacity": 18767.0, "EnergyFactor": 0.92},
        {"weight": 0.20, "TankVolume": 66.0, "HeatingCapacity": 18767.0, "EnergyFactor": 0.92},
        {"weight": 0.30, "TankVolume": 80.0, "HeatingCapacity": 18767.0, "EnergyFactor": 0.92}
    ]
}

ERWH_MODEL_CONFIG = {
    "ERWH_model": [
        # RHEEM PROE50 T2
        {"TankVolume": 45.0, "HeatingCapacity": 15354.0, "EnergyFactor": 0.93}
    ]
}


# ---------------------------------------------------------
# MODIFIER FUNCTIONS
# ---------------------------------------------------------
def update_ERWH_size(root, config):
    """Updates the size of existing ERWH systems based on original size."""
    ns_match = re.match(r'\{.*\}', root.tag)
    ns_bracket = ns_match.group(0) if ns_match else ''

    for elem in root.iter():
        if elem.tag.endswith('WaterHeatingSystem'):
            vol_elem = None
            cap_elem = None
            ef_elem = None
            
            for child in elem:
                if child.tag.endswith('TankVolume'):
                    vol_elem = child
                elif child.tag.endswith('HeatingCapacity'):
                    cap_elem = child
                elif child.tag.endswith('EnergyFactor'):
                    ef_elem = child
            
            if vol_elem is not None and vol_elem.text:
                try:
                    current_vol = float(vol_elem.text.strip())
                except ValueError:
                    continue
                
                if current_vol in config["ERWH_size"]:
                    updates = config["ERWH_size"][current_vol]
                    
                    # 1. Update Tank Volume
                    vol_elem.text = str(updates["TankVolume"])
                    
                    # 2. Update Heating Capacity
                    if cap_elem is not None:
                        cap_elem.text = str(updates["HeatingCapacity"])
                    else:
                        new_cap_elem = ET.Element(f'{ns_bracket}HeatingCapacity')
                        new_cap_elem.text = str(updates["HeatingCapacity"])
                        idx = list(elem).index(vol_elem)
                        elem.insert(idx + 1, new_cap_elem)

                    # 3. Update Energy Factor
                    if ef_elem is not None:
                        ef_elem.text = str(updates["EnergyFactor"])
                    else:
                        new_ef_elem = ET.Element(f'{ns_bracket}EnergyFactor')
                        new_ef_elem.text = str(updates["EnergyFactor"])
                        idx = list(elem).index(vol_elem)
                        elem.insert(idx + 2, new_ef_elem)

def distribute_ERWH_size(root, config):
    """Updates ERWH size based on a weighted random distribution."""
    ns_match = re.match(r'\{.*\}', root.tag)
    ns_bracket = ns_match.group(0) if ns_match else ''

    dist_data = config["ERWH_size_distrib"]
    # Extract the weights to feed into the random choice
    weights = [item["weight"] for item in dist_data]

    for elem in root.iter():
        if elem.tag.endswith('WaterHeatingSystem'):
            vol_elem = None
            cap_elem = None
            ef_elem = None
            
            for child in elem:
                if child.tag.endswith('TankVolume'):
                    vol_elem = child
                elif child.tag.endswith('HeatingCapacity'):
                    cap_elem = child
                elif child.tag.endswith('EnergyFactor'):
                    ef_elem = child
            
            # As long as there is an existing water heater to update
            if vol_elem is not None and vol_elem.text:
                # Select a new configuration based on the defined weights
                chosen_update = random.choices(dist_data, weights=weights, k=1)[0]
                
                # 1. Update Tank Volume
                vol_elem.text = str(chosen_update["TankVolume"])
                
                # 2. Update Heating Capacity
                if cap_elem is not None:
                    cap_elem.text = str(chosen_update["HeatingCapacity"])
                else:
                    new_cap_elem = ET.Element(f'{ns_bracket}HeatingCapacity')
                    new_cap_elem.text = str(chosen_update["HeatingCapacity"])
                    idx = list(elem).index(vol_elem)
                    elem.insert(idx + 1, new_cap_elem)
                
                # 3. Update Energy Factor
                if ef_elem is not None:
                    ef_elem.text = str(chosen_update["EnergyFactor"])
                else:
                    new_ef_elem = ET.Element(f'{ns_bracket}EnergyFactor')
                    new_ef_elem.text = str(chosen_update["EnergyFactor"])
                    idx = list(elem).index(vol_elem)
                    elem.insert(idx + 2, new_ef_elem)

def convert_to_ERWH(root, config):
    """Converts a HPWH, Gas, or Tankless heater to an ERWH by swapping types, fuels, and capacities."""
    ns_match = re.match(r'\{.*\}', root.tag)
    ns_bracket = ns_match.group(0) if ns_match else ''
    
    conv_data = config["ERWH_Conversion"]

    for elem in root.iter():
        if elem.tag.endswith('WaterHeatingSystem'):
            type_elem = None
            fuel_elem = None
            cap_elem = None
            vol_elem = None
            
            # Locate identifying elements
            for child in elem:
                if child.tag.endswith('WaterHeaterType'):
                    type_elem = child
                elif child.tag.endswith('FuelType'):
                    fuel_elem = child
                elif child.tag.endswith('HeatingCapacity'):
                    cap_elem = child
                elif child.tag.endswith('TankVolume'):
                    vol_elem = child
            
            # Identify if the system is HPWH, Tankless, or a non-electric Storage heater (like Gas)
            is_hpwh = (type_elem is not None and type_elem.text == 'heat pump water heater')
            is_tankless = (type_elem is not None and type_elem.text == 'tankless water heater')
            is_gas_storage = (type_elem is not None and type_elem.text == 'storage water heater' and fuel_elem is not None and fuel_elem.text != 'electricity')
            
            if is_hpwh or is_tankless or is_gas_storage:
                
                # 1. Change the water heater type
                if type_elem is not None:
                    type_elem.text = conv_data["NewType"]
                
                # 2. Update the Fuel Type to Electricity
                if fuel_elem is not None:
                    fuel_elem.text = conv_data["NewFuelType"]
                else:
                    new_fuel = ET.Element(f'{ns_bracket}FuelType')
                    new_fuel.text = conv_data["NewFuelType"]
                    # Insert safely at the top of the elements
                    elem.insert(0, new_fuel)

                # 3. Ensure Tank Volume exists
                if vol_elem is None:
                    vol_elem = ET.Element(f'{ns_bracket}TankVolume')
                    vol_elem.text = conv_data["DefaultTankVolume"]
                    # Insert before HeatingCapacity if possible
                    if cap_elem is not None:
                        idx = list(elem).index(cap_elem)
                        elem.insert(idx, vol_elem)
                    else:
                        elem.append(vol_elem)
                
                # 4. Update the primary heating capacity
                if cap_elem is not None:
                    cap_elem.text = conv_data["HeatingCapacity"]
                else:
                    cap_elem = ET.Element(f'{ns_bracket}HeatingCapacity')
                    cap_elem.text = conv_data["HeatingCapacity"]
                    idx = list(elem).index(vol_elem)
                    elem.insert(idx + 1, cap_elem)
                
                # 5. Remove incompatible HPWH, Gas, or Tankless specific elements
                to_remove = []
                for child in elem:
                    # If the child's tag ends with any of the blacklisted tags, mark it for removal
                    if any(child.tag.endswith(tag) for tag in conv_data["ElementsToRemove"]):
                        to_remove.append(child)
                
                for child in to_remove:
                    elem.remove(child)
                
                # 6. Insert ERWH-specific elements (EnergyFactor, RecoveryEfficiency)
                # We place them after HeatingCapacity to keep the HPXML schema ordered properly
                idx = list(elem).index(cap_elem)
                
                ef_elem = ET.Element(f'{ns_bracket}EnergyFactor')
                ef_elem.text = conv_data["EnergyFactor"]
                elem.insert(idx + 1, ef_elem)
                
                re_elem = ET.Element(f'{ns_bracket}RecoveryEfficiency')
                re_elem.text = conv_data["RecoveryEfficiency"]
                elem.insert(idx + 2, re_elem)


def convert_single_model(root, config):
    """Converts all ERWH to a single model."""
    ns_match = re.match(r'\{.*\}', root.tag)
    ns_bracket = ns_match.group(0) if ns_match else ''
    
    # Access the first item in the list
    model_data = config["ERWH_model"][0]

    for elem in root.iter():
        if elem.tag.endswith('WaterHeatingSystem'):
            type_elem = None
            cap_elem = None
            ef_elem = None
            
            # Locate identifying elements
            for child in elem:
                if child.tag.endswith('TankVolume'):
                    vol_elem = child
                elif child.tag.endswith('HeatingCapacity'):
                    cap_elem = child
                elif child.tag.endswith('EnergyFactor'):
                    ef_elem = child
            
            if vol_elem is not None and vol_elem.text:
                try:
                    current_vol = float(vol_elem.text.strip())
                except ValueError:
                    continue
                
                # 1. Update Tank Volume
                vol_elem.text = str(model_data["TankVolume"])
                    
                # 2. Update Heating Capacity
                if cap_elem is not None:
                    cap_elem.text = str(model_data["HeatingCapacity"])
                else:
                    new_cap_elem = ET.Element(f'{ns_bracket}HeatingCapacity')
                    new_cap_elem.text = str(model_data["HeatingCapacity"])
                    idx = list(elem).index(vol_elem)
                    elem.insert(idx + 1, new_cap_elem)

                # 3. Update Energy Factor
                if ef_elem is not None:
                    ef_elem.text = str(model_data["EnergyFactor"])
                else:
                    new_ef_elem = ET.Element(f'{ns_bracket}EnergyFactor')
                    new_ef_elem.text = str(model_data["EnergyFactor"])
                    idx = list(elem).index(vol_elem)
                    elem.insert(idx + 2, new_ef_elem)

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
            # print(f"Processing: {xml_file.name} in {xml_file.parent.name}")
            
            try:
                # Dynamically register namespaces
                for event, (prefix, uri) in ET.iterparse(xml_file, events=['start-ns']):
                    ET.register_namespace(prefix, uri)
                
                tree = ET.parse(xml_file)
                root = tree.getroot()
                
                # ==========================================
                # TURN YOUR UPDATES ON OR OFF HERE
                # ==========================================
                
                # update_ERWH_size(root, ERWH_SIZE_CONFIG)
                convert_to_ERWH(root, ERWH_CONVERSION_CONFIG)
                # distribute_ERWH_size(root, ERWH_SIZE_DISTRIB_CONFIG)
                # convert_single_model(root, ERWH_MODEL_CONFIG)
                
                # ==========================================
                
                # Apply pretty-print formatting to the tree so it avoids single-line outputs
                if hasattr(ET, 'indent'):
                    ET.indent(tree, space="  ", level=0)
                
                # Write changes back to the duplicated file
                tree.write(xml_file, encoding='UTF-8', xml_declaration=True)
                
            except ET.ParseError as e:
                print(f"Failed to parse XML for {xml_file}: {e}")
            except Exception as e:
                print(f"An error occurred while processing {xml_file}: {e}")

        print("Batch update complete.")