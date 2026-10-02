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

# Config
AREA_INDIA = "68,8,97,37"
# NRT sensors for daily live updates
LIVE_SENSORS = ["VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"]
LOOKBACK_DAYS = 2  # Fetch past 2 days to cover satellite processing delays

processed_file = os.path.join("data", "processed", "thermwatch_clean.csv")
raw_dir = os.path.join("data", "raw")
os.makedirs(raw_dir, exist_ok=True)

today_str = datetime.now().strftime("%Y-%m-%d")
print(f"=== Running Live NRT Fetcher for India: {today_str} ===")

new_frames = []

for sensor in LIVE_SENSORS:
    # URL format for NRT area fetch
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sensor}/{AREA_INDIA}/{LOOKBACK_DAYS}"
    try:
        res = requests.get(url, timeout=20)
        if res.status_code == 200 and "Invalid MAP_KEY" not in res.text:
            lines = res.text.strip().splitlines()
            if len(lines) > 1:
                # Save raw daily file
                daily_raw_path = os.path.join(raw_dir, f"live_{sensor}_{today_str}.csv")
                with open(daily_raw_path, "w", encoding="utf-8") as f:
                    f.write(res.text)
                
                df_chunk = pd.read_csv(daily_raw_path)
                df_chunk["source_sensor"] = sensor
                new_frames.append(df_chunk)
                print(f"  [LIVE FETCHED] {sensor}: {len(df_chunk)} records.")
            else:
                print(f"  [NO NEW DATA] {sensor}")
        else:
            print(f"  [FAILED] {sensor}: HTTP {res.status_code}")
    except Exception as e:
        print(f"  [ERROR] {sensor}: {e}")
    time.sleep(1)

if not new_frames:
    print("No new NRT detections retrieved today.")
    exit()

# Load incoming live records
live_df = pd.concat(new_frames, ignore_index=True)

# Standardize live data columns
if 'bright_ti4' in live_df.columns and 'brightness' in live_df.columns:
    live_df['brightness_k'] = live_df['bright_ti4'].fillna(live_df['brightness'])
elif 'bright_ti4' in live_df.columns:
    live_df['brightness_k'] = live_df['bright_ti4']
elif 'brightness' in live_df.columns:
    live_df['brightness_k'] = live_df['brightness']

if 'frp' in live_df.columns:
    live_df['frp_mw'] = live_df['frp']

def norm_conf(val):
    v = str(val).lower().strip()
    if v == 'l': return 30.0
    elif v == 'n': return 70.0
    elif v == 'h': return 95.0
    else:
        try: return float(v)
        except ValueError: return 50.0

if 'confidence' in live_df.columns:
    live_df['confidence_score'] = live_df['confidence'].apply(norm_conf)

if 'acq_date' in live_df.columns and 'acq_time' in live_df.columns:
    time_str = live_df['acq_time'].astype(str).str.zfill(4)
    live_df['timestamp'] = pd.to_datetime(
        live_df['acq_date'] + ' ' + time_str.str[:2] + ':' + time_str.str[2:],
        errors='coerce'
    )

cols_to_keep = [
    'latitude', 'longitude', 'timestamp', 'brightness_k', 
    'frp_mw', 'confidence_score', 'satellite', 'instrument', 
    'day_night', 'source_sensor'
]
available_cols = [c for c in cols_to_keep if c in live_df.columns]
live_clean = live_df[available_cols].copy()

# Append to existing master clean CSV
if os.path.exists(processed_file):
    existing_df = pd.read_csv(processed_file)
    existing_df['timestamp'] = pd.to_datetime(existing_df['timestamp'])
    combined_df = pd.concat([existing_df, live_clean], ignore_index=True)
else:
    combined_df = live_clean

# Deduplicate
initial_count = len(combined_df)
combined_df = combined_df.drop_duplicates(subset=['latitude', 'longitude', 'timestamp'])
final_count = len(combined_df)
added_count = final_count - (initial_count - len(live_clean))

combined_df.to_csv(processed_file, index=False)

print("\n==========================================")
print(f"Live Pipeline Update Complete!")
print(f"New Unique Detections Added Today: {added_count}")
print(f"Total Master Dataset Size: {final_count} records")
print(f"Saved To: {processed_file}")
print("==========================================")