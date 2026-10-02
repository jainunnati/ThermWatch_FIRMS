import os
import pandas as pd

raw_dir = os.path.join("data", "raw")
hist_dir = os.path.join("data", "historical")
processed_dir = os.path.join("data", "processed")
os.makedirs(processed_dir, exist_ok=True)

all_dfs = []

# 1. Load historical combined file if present
hist_combined_path = os.path.join(hist_dir, "historical_nrt_combined.csv")
if os.path.exists(hist_combined_path):
    print(f"Loading historical master dataset from {hist_combined_path}...")
    all_dfs.append(pd.read_csv(hist_combined_path))

# 2. Load all raw files (including gap retrieved CSVs)
if os.path.exists(raw_dir):
    for f in os.listdir(raw_dir):
        if f.endswith(".csv"):
            fpath = os.path.join(raw_dir, f)
            try:
                df = pd.read_csv(fpath)
                if not df.empty and "latitude" in df.columns:
                    all_dfs.append(df)
            except Exception as e:
                print(f"Skipping file {f}: {e}")

if not all_dfs:
    raise FileNotFoundError("No input CSV files found to process!")

combined_df = pd.concat(all_dfs, ignore_index=True)
initial_count = len(combined_df)
print(f"Initial Total Records (Historical + Gaps): {initial_count}")

# 3. Standardize Columns
if 'bright_ti4' in combined_df.columns and 'brightness' in combined_df.columns:
    combined_df['brightness_k'] = combined_df['bright_ti4'].fillna(combined_df['brightness'])
elif 'bright_ti4' in combined_df.columns:
    combined_df['brightness_k'] = combined_df['bright_ti4']
elif 'brightness' in combined_df.columns:
    combined_df['brightness_k'] = combined_df['brightness']

if 'frp' in combined_df.columns:
    combined_df['frp_mw'] = combined_df['frp']

def norm_conf(val):
    v = str(val).lower().strip()
    if v == 'l': return 30.0
    elif v == 'n': return 70.0
    elif v == 'h': return 95.0
    else:
        try: return float(v)
        except ValueError: return 50.0

if 'confidence' in combined_df.columns:
    combined_df['confidence_score'] = combined_df['confidence'].apply(norm_conf)

if 'acq_date' in combined_df.columns and 'acq_time' in combined_df.columns:
    time_str = combined_df['acq_time'].astype(str).str.zfill(4)
    combined_df['timestamp'] = pd.to_datetime(
        combined_df['acq_date'] + ' ' + time_str.str[:2] + ':' + time_str.str[2:],
        errors='coerce'
    )

cols_to_keep = [
    'latitude', 'longitude', 'timestamp', 'brightness_k', 
    'frp_mw', 'confidence_score', 'satellite', 'instrument', 
    'day_night', 'source_sensor'
]
available_cols = [c for c in cols_to_keep if c in combined_df.columns]
clean_df = combined_df[available_cols].copy()

# 4. Remove Duplicates
clean_df = clean_df.drop_duplicates(subset=['latitude', 'longitude', 'timestamp'])
duplicates_removed = initial_count - len(clean_df)

output_file = os.path.join(processed_dir, "thermwatch_clean.csv")
clean_df.to_csv(output_file, index=False)

print(f"\n==========================================")
print(f"Duplicates Removed: {duplicates_removed}")
print(f"Clean Records Saved: {len(clean_df)}")
print(f"Output Saved To: {output_file}")
print(f"==========================================")