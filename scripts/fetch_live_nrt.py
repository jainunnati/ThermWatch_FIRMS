import os
import io
import requests
import pandas as pd
from datetime import datetime, timezone
import subprocess
from dotenv import load_dotenv

# Base Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_FILE = os.path.join(BASE_DIR, "data", "processed", "thermwatch_clean.csv")

# Explicitly load .env from project root
load_dotenv(dotenv_path=ENV_PATH)

# Clean white spaces/quotes from API key
raw_key = os.getenv("MAP_KEY") or os.getenv("FIRMS_MAP_KEY") or ""
MAP_KEY = raw_key.strip().strip("'").strip('"')

if not MAP_KEY:
    print(f"Error: Neither MAP_KEY nor FIRMS_MAP_KEY environment variable found in {ENV_PATH}.")
    exit(1)

os.makedirs(RAW_DIR, exist_ok=True)

# Fetch rolling 3-day window
DAY_RANGE = 3
SATELLITE_SOURCES = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "MODIS_NRT"]

# Bounding box for India: [west_lon, south_lat, east_lon, north_lat]
INDIA_BBOX = "68.0,6.0,97.5,37.5"

print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting daily NRT ingestion...")

fetched_dfs = []
today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

for source in SATELLITE_SOURCES:
    # Area endpoint with India bounding box to prevent Status 400
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{source}/{INDIA_BBOX}/{DAY_RANGE}"
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200 and len(response.text.strip()) > 50 and "latitude" in response.text.lower():
            # Save raw copy to disk
            raw_filename = os.path.join(RAW_DIR, f"{today_str}_{source}_raw.csv")
            with open(raw_filename, "w", encoding="utf-8") as f:
                f.write(response.text)
            
            # Read into Pandas
            df = pd.read_csv(io.StringIO(response.text))
            df['satellite_source'] = source
            fetched_dfs.append(df)
            print(f"Successfully fetched {len(df)} rows from {source}. Raw saved to {raw_filename}")
        else:
            print(f"Warning: No valid CSV returned for {source} (Status: {response.status_code})")
            if response.status_code != 200:
                print(f"Response snippet: {response.text[:150]}")
    except Exception as e:
        print(f"Error fetching from {source}: {e}")

if not fetched_dfs:
    print("No new data fetched today. Exiting without updating clean dataset.")
    exit(0)

# Merge fetched data
new_data = pd.concat(fetched_dfs, ignore_index=True)

# Align columns and deduplicate
if os.path.exists(PROCESSED_FILE):
    existing_df = pd.read_csv(PROCESSED_FILE)
    
    combined_df = pd.concat([existing_df, new_data], ignore_index=True)
    dedup_cols = [c for c in ['latitude', 'longitude', 'acq_date', 'acq_time', 'satellite'] if c in combined_df.columns]
    clean_df = combined_df.drop_duplicates(subset=dedup_cols, keep='first')
    
    added_rows = len(clean_df) - len(existing_df)
    print(f"Merge Complete: {added_rows} new unique observations added.")
else:
    clean_df = new_data.drop_duplicates()
    print(f"Created new master clean file with {len(clean_df)} observations.")

# Save master processed dataset
clean_df.to_csv(PROCESSED_FILE, index=False)

# Auto-push to GitHub
try:
    print("Pushing updated master CSV to GitHub...")
    subprocess.run(["git", "add", PROCESSED_FILE], check=True, cwd=BASE_DIR)
    
    commit_msg = f"Auto-update NRT thermal dataset: {today_str}"
    subprocess.run(["git", "commit", "-m", commit_msg], check=True, cwd=BASE_DIR)
    subprocess.run(["git", "push", "origin", "main"], check=True, cwd=BASE_DIR)
    print("Successfully pushed latest dataset to GitHub!")
except subprocess.CalledProcessError as e:
    print(f"Git Auto-Push Notice: {e}")

print("NRT Pipeline completed successfully.")