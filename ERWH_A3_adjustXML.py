import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
import re


SCRIPT_DIR = Path(__file__).resolve().parent
PARENT_DIR = SCRIPT_DIR.parent 

#Directory of files we are copying and adjusting    
INPUT_DIR = PARENT_DIR / "ERWH All Input Files"
#Directory we write the adjusted files to
OUTPUT_DIR = PARENT_DIR / "ERWH All AdjustedSize Input Files"


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
UPGRADE_CONFIG = {
    "WH_size": {
        # Current Volume : {"TankVolume": New Volume, "HeatingCapacity": New Capacity}
        30.0: {"TankVolume": 50.0, "HeatingCapacity": 18767.0},
        50.0: {"TankVolume": 66.0, "HeatingCapacity": 18767.0},
        66.0: {"TankVolume": 80.0, "HeatingCapacity": 18767.0}
    },

    "hvac": {
        # Placeholder for future HVAC configurations
    }
}

def update_WH_size(root, config):
    """
    Finds water heaters by checking the end of the tag string, bypassing all namespace 
    mismatches. Extracts the exact namespace from the root to safely create new elements.
    """
    # Extract the namespace bracket dynamically from the root (e.g., '{http://hpxmlonline.com/2019/10}')
    ns_match = re.match(r'\{.*\}', root.tag)
    ns_bracket = ns_match.group(0) if ns_match else ''

    # Iterate through ALL elements and match by local tag name
    for elem in root.iter():
        if elem.tag.endswith('WaterHeatingSystem'):
            vol_elem = None
            cap_elem = None
            
            # Locate child elements manually to guarantee we find them
            for child in elem:
                if child.tag.endswith('TankVolume'):
                    vol_elem = child
                elif child.tag.endswith('HeatingCapacity'):
                    cap_elem = child
            
            if vol_elem is not None and vol_elem.text:
                try:
                    # .strip() removes any hidden spaces or linebreaks
                    current_vol = float(vol_elem.text.strip())
                except ValueError:
                    continue
                
                if current_vol in config["WH_size"]:
                    updates = config["WH_size"][current_vol]
                    
                    # 1. Update Tank Volume
                    vol_elem.text = str(updates["TankVolume"])
                    
                    # 2. Update Heating Capacity
                    if cap_elem is not None:
                        cap_elem.text = str(updates["HeatingCapacity"])
                    else:
                        # Create new element with the EXACT same namespace as the root
                        new_cap_elem = ET.Element(f'{ns_bracket}HeatingCapacity')
                        new_cap_elem.text = str(updates["HeatingCapacity"])
                        
                        # Insert directly after TankVolume to maintain schema order
                        idx = list(elem).index(vol_elem)
                        elem.insert(idx + 1, new_cap_elem)

def process_and_copy_buildings(input_dir, output_dir, config):
    """
    Duplicates the directory, dynamically registers all namespaces to prevent 'ns0:',
    and modifies the XML files.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    if not input_path.exists():
        print(f"Error: Could not find input directory at {input_path.resolve()}")
        return

    # 1. Duplicate the directory structure
    print(f"Copying files from '{input_path.name}' to '{output_path.name}'...")
    if output_path.exists():
        shutil.copytree(input_path, output_path, dirs_exist_ok=True)
    else:
        shutil.copytree(input_path, output_path)

    # 2. Process XML files
    for xml_file in output_path.rglob('*.xml'):
        print(f"Processing: {xml_file.name} in {xml_file.parent.name}")
        
        try:
            # DYNAMICALLY REGISTER NAMESPACES
            # This completely stops Python from generating 'ns0:' or 'ns1:'
            for event, (prefix, uri) in ET.iterparse(xml_file, events=['start-ns']):
                ET.register_namespace(prefix, uri)
            
            # Now parse the tree normally
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Apply modifications
            update_WH_size(root, config)
            
            # Write changes
            tree.write(xml_file, encoding='UTF-8', xml_declaration=True)
            
        except ET.ParseError as e:
            print(f"Failed to parse XML for {xml_file}: {e}")
        except Exception as e:
            print(f"An error occurred while processing {xml_file}: {e}")

if __name__ == "__main__":
    
    print("Starting OCHRE HPXML batch update...")
    process_and_copy_buildings(INPUT_DIR, OUTPUT_DIR, UPGRADE_CONFIG)
    print("Batch update complete.")