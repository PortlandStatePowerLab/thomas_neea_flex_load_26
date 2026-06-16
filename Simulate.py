import os
import datetime as dt
from ochre import Dwelling
from ochre.utils import default_input_path  # for using sample files

house = Dwelling(
    start_time=dt.datetime(2018, 5, 1, 0, 0),
    time_res=dt.timedelta(minutes=10),
    duration=dt.timedelta(days=3),
    hpxml_file=os.path.join(default_input_path, "Input Files", "bldg0325720-up06.xml"),
    hpxml_schedule_file=os.path.join(default_input_path, "Input Files", "bldg0325720_schedule.csv"),
    weather_file=os.path.join(default_input_path, "Weather", "USA_OR_Portland.Intl.AP.726980_TMY3.epw"),
)

house.simulate()