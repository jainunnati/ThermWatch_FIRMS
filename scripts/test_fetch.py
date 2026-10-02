import os
import requests
import pandas as pd
from dotenv import load_dotenv

# Load MAP_KEY from .env
load_dotenv()
MAP_KEY = os.getenv("FIRMS_MAP_KEY")

if not MAP_KEY or len(MAP_KEY) < 20:
    raise ValueError("ERROR: FIRMS_MAP_KEY is missing or invalid in your .env file!")

# Configurable Parameters
SENSORS = [
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
    "MODIS_NRT"
]
AREA = "68,8,97,37"  # Bounding box covering India (West, South, East, North)
DAY_RANGE = "1"
TEST_DATE = "2026-09-25"

output_dir = os.path.join("data", "raw")
os.makedirs(output_dir, exist_ok=True)

print(f"--- Starting Multi-Sensor Ingestion for {TEST_DATE} ---")

for source in SENSORS:
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{source}/{AREA}/{DAY_RANGE}/{TEST_DATE}"
    print(f"\nFetching data for {source}...")
    
    response = requests.get(url)
    
    if response.status_code == 200:
        if "Transaction Limit Reached" in response.text or "Invalid MAP_KEY" in response.text:
            print(f"  [ERROR] API Message: {response.text}")
            continue
            
        file_path = os.path.join(output_dir, f"{source}_{TEST_DATE}.csv")
        
        # Save raw CSV
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(response.text)
        
        df = pd.read_csv(file_path)
        print(f"  [SUCCESS] Saved to {file_path}")
        print(f"  Rows Downloaded: {len(df)}")
        print(f"  Columns ({len(df.columns)}): {list(df.columns)}")
    else:
        print(f"  [FAILED] HTTP {response.status_code}: {response.text}")

print("\n--- Multi-Sensor Fetch Complete ---")