import os
import datetime as dt
from pathlib import Path
from ochre import Dwelling

root_path = root = Path (__file__).resolve().parent
default_path = os.path.join(root_path, ".venv\Lib\site-packages\ochre\defaults\Input Files")
building_ID = '0000960'
building_path_str = str.join("", ["bldg", building_ID, "-up06"])
building_path = os.path.join(default_path, building_path_str)

house = Dwelling(
    start_time=dt.datetime(2018, 5, 1, 0, 0),
    time_res=dt.timedelta(minutes=10),
    duration=dt.timedelta(days=3),
    hpxml_file=os.path.join(building_path, "in.xml"),
    hpxml_schedule_file=os.path.join(building_path, "schedule.csv"),
    weather_file=os.path.join(default_path, "Weather", "USA_OR_Portland.Intl.AP.726980_TMY3.epw"),
)

house.simulate()