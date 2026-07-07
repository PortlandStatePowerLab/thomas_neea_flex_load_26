# Flex_Load

OCHRE simulation based testing for the 005 NEEA flex load project, investigating behaviors of smart-grid appliances under various commands and grid service conditions.

# Contributors
Alex: https://github.com/PortlandStatePowerLab/Alex-NEEA-Flex-Load-Calculator  
Othman: https://github.com/PortlandStatePowerLab/othman_neea_flex_load_calculator_26

# Short Description

This code will run simulations in OCHRE for Portland houses, on the appliances:  
Heat Pump Water Heater (HPWH)  
Electric Resistance Water Heater (ERWH)  
Air Conditioning (AC)  
  
And will compare baseline power usage to controlled power usage using load up and shed commands, for a variety of grid service conditions

# Tech Stack

Language: Python  
Tool: OCHRE

# Repository Contents

HPWH: code for simulating heat pump water heaters  
ERWH: code for simulating electric resistance water heaters  
AC: code for simulating air conditioning  

    
# Getting Started

Follow these steps to set up the project locally.
# Prerequisites

List any software, tools, or global packages needed:  
  Python 3.9-3.12  
  ochre-nrel  
  
# Installation

Clone the repository:  

  git clone 

Install OCHRE:  
    
  pip install ochre-nrel

# If I want to work on this project, where should I start from?

Clone the repository, download the ResStock metadata (OR_upgrade0.csv) to a folder named "Metadata" one directory above the flex load repository and weather file (USA_OR_Portland.Intl.AP.726980_TMY3) to a folder named "Weather" one directory above the flex load repository. All code is appliance specific, so enter the flex load folder for the appliance you wish to simulate. Run the codes in order, editing input and output file names as necessary.  
(A: pre simulation)  
A1 code will filter the metadata csv files to only the homes you need to run  
A2 code will save XML input files and schedules that OCHRE will read  
A3 code will adjust XML files if you need to change appliance properties  
(B: simulation)  
B code will simulate, you only need to run one of these, the numbers are just to keep them in order 
(C: post simulation)  
C1 code will parse the raw data and reorganize it to home rows and time columns for a specific data series  
C2 code will average the data for each time step and plot  
