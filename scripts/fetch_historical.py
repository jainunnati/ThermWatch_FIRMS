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

# Use Standard Processing (_SP) endpoints for historical data (>10 days old)
SENSORS_SP = [
    "VIIRS_NOAA20_SP",
    "MODIS_SP"
]

AREA_INDIA = "68,8,97,37"

# 6 months (~180 days back)
END_DATE = datetime.now() - timedelta(days=10)  # SP data has ~10-day latency
START_DATE = END_DATE - timedelta(days=170)
CHUNK_DAYS = 5  # NASA API limit is 5 days max per request

raw_dir = os.path.join("data", "raw")
hist_dir = os.path.join("data", "historical")
os.makedirs(raw_dir, exist_ok=True)
os.makedirs(hist_dir, exist_ok=True)

all_frames = []

print(f"=== Fetching Historical Data ({START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}) ===")

for sensor in SENSORS_SP:
    print(f"\n--- Processing Sensor: {sensor} ---")
    current_date = START_DATE
    
    while current_date <= END_DATE:
        date_str = current_date.strftime("%Y-%m-%d")
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sensor}/{AREA_INDIA}/{CHUNK_DAYS}/{date_str}"
        file_path = os.path.join(raw_dir, f"{sensor}_{date_str}_chunk.csv")
        
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200 and "Invalid MAP_KEY" not in response.text:
                lines = response.text.strip().splitlines()
                if len(lines) > 1:  # Contains actual records
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(response.text)
                    df_chunk = pd.read_csv(file_path)
                    df_chunk["source_sensor"] = sensor
                    all_frames.append(df_chunk)
                    print(f"  [SUCCESS] {date_str} ({CHUNK_DAYS}d): Downloaded {len(df_chunk)} rows.")
                else:
                    print(f"  [EMPTY] {date_str}: 0 detections.")
            else:
                print(f"  [SKIPPED] {date_str}: HTTP {response.status_code}")
        except Exception as e:
            print(f"  [ERROR] {date_str}: {e}")
            
        time.sleep(1)  # Respect API rate limits
        current_date += timedelta(days=CHUNK_DAYS)

if all_frames:
    master_df = pd.concat(all_frames, ignore_index=True)
    master_file = os.path.join(hist_dir, "historical_nrt_combined.csv")
    master_df.to_csv(master_file, index=False)
    print(f"\n==========================================")
    print(f"SUCCESS: Master historical dataset saved to {master_file}")
    print(f"Total Combined Records: {len(master_df)}")
    print(f"==========================================")
else:
    print("\nNo data retrieved.")