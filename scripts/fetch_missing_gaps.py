import os
import time
from datetime import datetime, timedelta
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
MAP_KEY = os.getenv("FIRMS_MAP_KEY")

if not MAP_KEY or len(MAP_KEY) < 20:
    raise ValueError("ERROR: FIRMS_MAP_KEY is missing or invalid in your .env file!")

# Target the two specific missing windows
MISSING_RANGES = [
    {"name": "July Gap", "start": "2026-07-01", "end": "2026-08-02"},
    {"name": "Mid-Sept Gap", "start": "2026-09-12", "end": "2026-09-20"}
]

SENSORS = ["VIIRS_NOAA20_SP", "VIIRS_NOAA21_SP", "MODIS_SP"]
AREA_INDIA = "68,8,97,37"
CHUNK_DAYS = 5

raw_dir = os.path.join("data", "raw")
os.makedirs(raw_dir, exist_ok=True)

gap_frames = []

print("=== Starting Targeted Fetch for Missing Date Windows ===")

for gap in MISSING_RANGES:
    print(f"\n--- Filling {gap['name']} ({gap['start']} to {gap['end']}) ---")
    start_dt = datetime.strptime(gap['start'], "%Y-%m-%d")
    end_dt = datetime.strptime(gap['end'], "%Y-%m-%d")
    
    for sensor in SENSORS:
        curr_dt = start_dt
        while curr_dt <= end_dt:
            date_str = curr_dt.strftime("%Y-%m-%d")
            url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sensor}/{AREA_INDIA}/{CHUNK_DAYS}/{date_str}"
            file_path = os.path.join(raw_dir, f"gap_{sensor}_{date_str}.csv")
            
            try:
                res = requests.get(url, timeout=15)
                if res.status_code == 200 and "Invalid MAP_KEY" not in res.text:
                    lines = res.text.strip().splitlines()
                    if len(lines) > 1:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(res.text)
                        df_chunk = pd.read_csv(file_path)
                        df_chunk["source_sensor"] = sensor
                        gap_frames.append(df_chunk)
                        print(f"  [FETCHED] {sensor} | {date_str}: {len(df_chunk)} records.")
                    else:
                        # Fallback try NRT endpoint if SP is empty for near dates
                        nrt_sensor = sensor.replace("_SP", "_NRT")
                        url_nrt = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{nrt_sensor}/{AREA_INDIA}/{CHUNK_DAYS}/{date_str}"
                        res_nrt = requests.get(url_nrt, timeout=15)
                        if res_nrt.status_code == 200 and len(res_nrt.text.strip().splitlines()) > 1:
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(res_nrt.text)
                            df_chunk = pd.read_csv(file_path)
                            df_chunk["source_sensor"] = nrt_sensor
                            gap_frames.append(df_chunk)
                            print(f"  [FETCHED NRT FALLBACK] {nrt_sensor} | {date_str}: {len(df_chunk)} records.")
                        else:
                            print(f"  [EMPTY] {sensor} | {date_str}")
                else:
                    print(f"  [SKIPPED] {sensor} | {date_str}: HTTP {res.status_code}")
            except Exception as e:
                print(f"  [ERROR] {sensor} | {date_str}: {e}")
                
            time.sleep(1)
            curr_dt += timedelta(days=CHUNK_DAYS)

if gap_frames:
    gap_df = pd.concat(gap_frames, ignore_index=True)
    gap_summary_path = os.path.join("data", "raw", "missing_gaps_retrieved.csv")
    gap_df.to_csv(gap_summary_path, index=False)
    print(f"\n==========================================")
    print(f"SUCCESS: Recovered {len(gap_df)} missing records!")
    print(f"Saved gap data to {gap_summary_path}")
    print(f"==========================================")
else:
    print("\nNo additional gap data found.")