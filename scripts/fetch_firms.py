import os
import requests
import pandas as pd
from dotenv import load_dotenv

# Load MAP_KEY from .env
load_dotenv()
MAP_KEY = os.getenv("FIRMS_MAP_KEY")

def fetch_firms_window(sensor: str, area: str, date_str: str, day_range: int = 5) -> pd.DataFrame:
    """
    Fetches FIRMS observation data for a specific sensor, area, start date, and day range (1-5).
    Saves raw CSV to data/raw/ and returns a pandas DataFrame.
    """
    if not MAP_KEY or len(MAP_KEY) < 20:
        raise ValueError("FIRMS_MAP_KEY is missing or invalid in your .env file.")
    
    if day_range < 1 or day_range > 5:
        raise ValueError("NASA FIRMS Area API only supports day_range values from 1 to 5.")
        
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{sensor}/{area}/{day_range}/{date_str}"
    print(f"Requesting {sensor} | Date: {date_str} | Days: {day_range}...")
    
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"  [ERROR] HTTP {response.status_code}: {response.text}")
        return pd.DataFrame()
        
    if "Transaction Limit Reached" in response.text or "Invalid MAP_KEY" in response.text:
        print(f"  [API ERROR] {response.text}")
        return pd.DataFrame()
        
    output_dir = os.path.join("data", "raw")
    os.makedirs(output_dir, exist_ok=True)
    
    file_path = os.path.join(output_dir, f"{sensor}_{date_str}_range{day_range}.csv")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(response.text)
        
    df = pd.read_csv(file_path)
    print(f"  [SUCCESS] Downloaded {len(df)} rows -> Saved: {file_path}")
    return df

if __name__ == "__main__":
    AREA_INDIA = "68,8,97,37"
    TEST_START_DATE = "2026-09-20"
    
    print("=== Testing 5-Day FIRMS Window Fetch ===")
    df_5day = fetch_firms_window("VIIRS_NOAA20_NRT", AREA_INDIA, TEST_START_DATE, day_range=5)
    print(f"\n5-Day Fetch Summary: Total Records = {len(df_5day)}")