import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
import re

# ---------------------------------------------------------
# DIRECTORY SETUP
# ---------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PARENT_DIR = SCRIPT_DIR.parent 

INPUT_DIR = PARENT_DIR / "ERWH All Input Files"
OUTPUT_DIR = PARENT_DIR / "ERWH All AdjustedSize Input Files"

# ---------------------------------------------------------
# CONFIGURATIONS
# ---------------------------------------------------------
ERWH_SIZE_CONFIG = {
    "ERWH_size": {
        # Current Volume : {"TankVolume": New Volume, "HeatingCapacity": New Capacity}
        30.0: {"TankVolume": 50.0, "HeatingCapacity": 18767.0},
        50.0: {"TankVolume": 66.0, "HeatingCapacity": 18767.0},
        66.0: {"TankVolume": 80.0, "HeatingCapacity": 18767.0}
    },
}

ERWH_CONVERSION_CONFIG = {
    "ERWH_Conversion": {
        "NewType": "storage water heater",
        "HeatingCapacity": "18767.0",
        "EnergyFactor": "0.92",
        "RecoveryEfficiency": "0.98",
        # Tags that exist in HPWH but break the schema for standard ERWH
        "ElementsToRemove": [
            "BackupHeatingCapacity", 
            "UniformEnergyFactor", 
            "HPWHOperatingMode", 
            "UsageBin"
        ]
    }
}



# ---------------------------------------------------------
# MODIFIER FUNCTIONS
# ---------------------------------------------------------
def update_ERWH_size(root, config):
    """Updates the size of existing ERWH systems."""
    ns_match = re.match(r'\{.*\}', root.tag)
    ns_bracket = ns_match.group(0) if ns_match else ''

    for elem in root.iter():
        if elem.tag.endswith('WaterHeatingSystem'):
            vol_elem = None
            cap_elem = None
            
            for child in elem:
                if child.tag.endswith('TankVolume'):
                    vol_elem = child
                elif child.tag.endswith('HeatingCapacity'):
                    cap_elem = child
            
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

def convert_HPWH_to_ERWH(root, config):
    """Converts a HPWH to an ERWH by swapping types, capacities, and schema tags."""
    ns_match = re.match(r'\{.*\}', root.tag)
    ns_bracket = ns_match.group(0) if ns_match else ''
    
    conv_data = config["ERWH_Conversion"]

    for elem in root.iter():
        if elem.tag.endswith('WaterHeatingSystem'):
            type_elem = None
            cap_elem = None
            
            # Locate identifying elements
            for child in elem:
                if child.tag.endswith('WaterHeaterType'):
                    type_elem = child
                elif child.tag.endswith('HeatingCapacity'):
                    cap_elem = child
            
            # Check if it is actually a Heat Pump Water Heater
            if type_elem is not None and type_elem.text == 'heat pump water heater':
                
                # 1. Change the water heater type
                type_elem.text = conv_data["NewType"]
                
                # 2. Update the primary heating capacity
                if cap_elem is not None:
                    cap_elem.text = conv_data["HeatingCapacity"]
                
                # 3. Remove HPWH-specific elements
                to_remove = []
                for child in elem:
                    # If the child's tag ends with any of the blacklisted tags, mark it for removal
                    if any(child.tag.endswith(tag) for tag in conv_data["ElementsToRemove"]):
                        to_remove.append(child)
                
                for child in to_remove:
                    elem.remove(child)
                
                # 4. Insert ERWH-specific elements (EnergyFactor, RecoveryEfficiency)
                # We insert them directly after HeatingCapacity to keep the HPXML schema ordered properly
                if cap_elem is not None:
                    idx = list(elem).index(cap_elem)
                    
                    ef_elem = ET.Element(f'{ns_bracket}EnergyFactor')
                    ef_elem.text = conv_data["EnergyFactor"]
                    elem.insert(idx + 1, ef_elem)
                    
                    re_elem = ET.Element(f'{ns_bracket}RecoveryEfficiency')
                    re_elem.text = conv_data["RecoveryEfficiency"]
                    elem.insert(idx + 2, re_elem)

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
                
                update_ERWH_size(root, ERWH_SIZE_CONFIG)
                convert_HPWH_to_ERWH(root, ERWH_CONVERSION_CONFIG)
                
                # ==========================================
                
                # Write changes back to the duplicated file
                tree.write(xml_file, encoding='UTF-8', xml_declaration=True)
                
            except ET.ParseError as e:
                print(f"Failed to parse XML for {xml_file}: {e}")
            except Exception as e:
                print(f"An error occurred while processing {xml_file}: {e}")

        print("Batch update complete.")