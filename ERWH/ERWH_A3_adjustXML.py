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
        "TankVolume": "80.0",         # Controls the size for ALL water heaters
        "HeatingCapacity": "18767.0", # Controls the capacity for ALL water heaters
        "EnergyFactor": "0.93",
        "RecoveryEfficiency": "0.98",
        "ElementsToRemove": [
            "BackupHeatingCapacity", 
            "UniformEnergyFactor", 
            "HPWHOperatingMode", 
            "UsageBin",
            "FirstHourRating"
            # EnergyFactor and RecoveryEfficiency handled safely below
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
    """
    Standardizes ALL water heaters in the XML to standard 
    ERWHs using the parameters defined in the conversion config.
    """
    ns_match = re.match(r'\{.*\}', root.tag)
    ns_bracket = ns_match.group(0) if ns_match else ''
    
    conv_data = config["ERWH_Conversion"]

    for elem in root.iter():
        if elem.tag.split('}')[-1] == 'WaterHeatingSystem':
            type_elem = None
            fuel_elem = None
            cap_elem = None
            vol_elem = None
            
            # Locate existing identifying elements
            for child in elem:
                tag_name = child.tag.split('}')[-1]
                if tag_name == 'WaterHeaterType':
                    type_elem = child
                elif tag_name == 'FuelType':
                    fuel_elem = child
                elif tag_name == 'HeatingCapacity':
                    cap_elem = child
                elif tag_name == 'TankVolume':
                    vol_elem = child
            
            # 1. Force Water Heater Type
            if type_elem is not None:
                type_elem.text = conv_data["NewType"]
            else:
                type_elem = ET.Element(f'{ns_bracket}WaterHeaterType')
                type_elem.text = conv_data["NewType"]
                elem.insert(0, type_elem)
            
            # 2. Force Fuel Type to Electricity
            if fuel_elem is not None:
                fuel_elem.text = conv_data["NewFuelType"]
            else:
                new_fuel = ET.Element(f'{ns_bracket}FuelType')
                new_fuel.text = conv_data["NewFuelType"]
                # Insert right after WaterHeaterType
                idx = list(elem).index(type_elem)
                elem.insert(idx + 1, new_fuel)

            # 3. Force Tank Volume Override
            if vol_elem is not None:
                vol_elem.text = conv_data["TankVolume"]
            else:
                vol_elem = ET.Element(f'{ns_bracket}TankVolume')
                vol_elem.text = conv_data["TankVolume"]
                # Try to insert before heating capacity if it exists
                if cap_elem is not None:
                    idx = list(elem).index(cap_elem)
                    elem.insert(idx, vol_elem)
                else:
                    elem.append(vol_elem)
            
            # 4. Force Heating Capacity Override
            if cap_elem is not None:
                cap_elem.text = conv_data["HeatingCapacity"]
            else:
                cap_elem = ET.Element(f'{ns_bracket}HeatingCapacity')
                cap_elem.text = conv_data["HeatingCapacity"]
                idx = list(elem).index(vol_elem)
                elem.insert(idx + 1, cap_elem)
            
            # 5. Remove incompatible tags (from HPWH, Gas, or Tankless)
            to_remove = []
            for child in elem:
                tag_name = child.tag.split('}')[-1]
                if tag_name in conv_data["ElementsToRemove"]:
                    to_remove.append(child)
            
            for child in to_remove:
                elem.remove(child)
            
            # 6. Apply or Override ERWH-specific elements
            ef_elem = None
            re_elem = None
            for child in elem:
                tag_name = child.tag.split('}')[-1]
                if tag_name == 'EnergyFactor':
                    ef_elem = child
                elif tag_name == 'RecoveryEfficiency':
                    re_elem = child

            idx = list(elem).index(cap_elem)
            
            if ef_elem is not None:
                ef_elem.text = conv_data["EnergyFactor"]
            else:
                ef_elem = ET.Element(f'{ns_bracket}EnergyFactor')
                ef_elem.text = conv_data["EnergyFactor"]
                elem.insert(idx + 1, ef_elem)
            
            if re_elem is not None:
                re_elem.text = conv_data["RecoveryEfficiency"]
            else:
                re_elem = ET.Element(f'{ns_bracket}RecoveryEfficiency')
                re_elem.text = conv_data["RecoveryEfficiency"]
                # Insert immediately after EnergyFactor
                idx_ef = list(elem).index(ef_elem)
                elem.insert(idx_ef + 1, re_elem)


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