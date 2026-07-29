from pathlib import Path
import re
import numpy as np
import pandas as pd

# ============================================================
# CONFIG
# ============================================================

DATASET_DIR = Path("datasets")

# Pastikan nama file Excel sesuai dengan file asli Anda
INPUT_FILE = DATASET_DIR / "20200326_PhantomInfo.xlsx" 
OUTPUT_FILE = DATASET_DIR / "phantom_database.csv"

# ============================================================
# LOAD EXCEL
# ============================================================

print(f"Loading: {INPUT_FILE}")

# Header=None karena struktur excel tidak standar (merged cells)
df_raw = pd.read_excel(
    INPUT_FILE,
    sheet_name=0,
    header=None
)

print(f"Original Shape : {df_raw.shape}")

# ============================================================
# PARSING LOGIC (Custom for Merged Cells Structure)
# ============================================================

# Berdasarkan sampel data:
# Kolom 4: Shell Volume
# Kolom 5: Breast Length
# Kolom 6: Mean Shell Radius
# Kolom 7: Shell Radius at Antenna Plane
# Kolom 8: Fibroglandular Model (F1, F2, etc)
# Kolom 9: Fibroglandular Volume
# Kolom 10: Fibroglandular %

# Kita perlu mengidentifikasi baris mana yang merupakan "Header Shell" 
# dan baris mana yang merupakan detail "Fibroglandular".
# Biasanya baris Shell memiliki nilai di kolom Volume/Radius tapi kosong di kolom Fib Model.

data_list = []

# Iterasi melalui dataframe
for index, row in df_raw.iterrows():
    # Ambil nilai dari kolom-kolom kunci
    # Index kolom berdasarkan sampel: 
    # 1: Shell Name (A1, A2...) - sering merged atau di kolom ke-1/2
    # 2: Density Class (C1, C2...)
    # 4: Shell Volume
    # 5: Breast Length
    # 6: Mean Radius
    # 7: Shell Radius at Antenna
    # 8: Fib Model (F1, F2...)
    # 9: Fib Volume
    # 10: Fib Percent
    
    shell_name = row.iloc[1] if pd.notna(row.iloc[1]) else None
    density_class = row.iloc[2] if pd.notna(row.iloc[2]) else None
    
    shell_vol = row.iloc[4]
    breast_len = row.iloc[5]
    mean_rad = row.iloc[6]
    shell_rad_ant = row.iloc[7]
    
    fib_model = row.iloc[8]
    fib_vol = row.iloc[9]
    fib_pct = row.iloc[10]
    
    # Logika: Jika ada Fib Model, maka ini adalah baris detail yang valid untuk digabungkan
    # dengan informasi Shell sebelumnya.
    if pd.notna(fib_model):
        # Konversi fib_model ke string untuk memastikan format F\d+
        fib_model_str = str(fib_model).strip()
        
        # Validasi format Fib Model (harus F diikuti angka)
        if re.match(r"^F\d+$", fib_model_str):
            
            # Handle Shell Name: Jika kosong di baris ini, ambil dari baris sebelumnya (logic sederhana)
            # Atau lebih baik, kita asumsikan shell_name sudah ter-fill jika struktur excelnya benar.
            # Namun, karena merged cells sering kali hanya ada di baris pertama grup,
            # kita perlu mekanisme 'last known shell'.
            
            # Untuk simplifikasi, kita akan melakukan ffill pada shell_name nanti, 
            # tapi sekarang kita simpan raw datanya dulu.
            
            entry = {
                "shell_raw": shell_name,
                "density_class": density_class,
                "shell_volume": shell_vol,
                "breast_length": breast_len,
                "mean_radius": mean_rad,
                "shell_radius": shell_rad_ant, # Ini yang biasanya dipakai sebagai breast_radius_mm referensi
                "fib_model": fib_model_str,
                "fib_volume": fib_vol,
                "fib_percent_raw": fib_pct
            }
            data_list.append(entry)

df = pd.DataFrame(data_list)

if df.empty:
    raise ValueError("No valid data parsed. Check column indices in the script.")

print(f"Parsed Entries: {len(df)}")

# ============================================================
# CLEANING & FORWARD FILL
# ============================================================

# Karena Shell Name (dan mungkin geometry) hanya ada di baris pertama setiap grup,
# kita lakukan forward fill untuk mengisi baris-detail di bawahnya.
cols_to_ffill = ["shell_raw", "shell_volume", "breast_length", "mean_radius", "shell_radius", "density_class"]
for col in cols_to_ffill:
    df[col] = df[col].ffill()

# Hapus baris yang masih NaN di kolom kritis setelah ffill
df.dropna(subset=["shell_raw", "fib_model"], inplace=True)

# ============================================================
# TYPE CONVERSION & CLEANING
# ============================================================

# Bersihkan persen sign jika ada (misal "4.353%" menjadi 4.353)
if df["fib_percent_raw"].dtype == object:
    df["fib_percent"] = df["fib_percent_raw"].astype(str).str.replace("%", "", regex=False)
else:
    df["fib_percent"] = df["fib_percent_raw"]

df["fib_percent"] = pd.to_numeric(df["fib_percent"], errors="coerce")

# Konversi kolom numerik lainnya
numeric_cols = ["shell_volume", "breast_length", "mean_radius", "shell_radius", "fib_volume"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# ============================================================
# BUILD PHANTOM ID
# ============================================================

# Format ID: Shell + FibModel (Contoh: A1F1)
# Pastikan shell_raw adalah string dan bersih
df["shell"] = df["shell_raw"].astype(str).str.strip()
df["phantom_id"] = df["shell"] + df["fib_model"]

# ============================================================
# FINAL COLUMN SELECTION
# ============================================================

# Sesuaikan dengan kebutuhan merge ke metadata
df_final = df[[
    "phantom_id",
    "shell",
    "density_class",
    "fib_model",
    "shell_volume",
    "breast_length",
    "mean_radius",
    "shell_radius",
    "fib_volume",
    "fib_percent"
]].copy()

# Hapus duplikat jika ada
df_final = df_final.drop_duplicates(subset="phantom_id").reset_index(drop=True)

# ============================================================
# VALIDATION & MISSING VALUE HANDLING
# ============================================================

print("\n" + "="*50)
print("VALIDATION REPORT")
print("="*50)

print(f"\nDatabase Shape : {df_final.shape}")
print(f"Unique Phantoms: {df_final['phantom_id'].nunique()}")

# Cek Missing Values
missing_vals = df_final.isna().sum()
print("\nMissing Values per Column:")
print(missing_vals[missing_vals > 0])

if missing_vals.sum() > 0:
    print("\n WARNING: Missing values detected!")
    print("Rows with missing critical data:")
    # Tampilkan baris yang memiliki missing value di kolom penting
    critical_cols = ["shell_radius", "fib_volume", "fib_percent"]
    mask_missing = df_final[critical_cols].isna().any(axis=1)
    if mask_missing.any():
        print(df_final[mask_missing][["phantom_id", "shell_radius", "fib_volume", "fib_percent"]])
        
        # Opsi: Drop baris dengan missing value kritis agar database bersih
        print("\nDropping rows with missing critical values...")
        df_final.dropna(subset=critical_cols, inplace=True)
        df_final.reset_index(drop=True, inplace=True)
        print(f"Shape after dropping: {df_final.shape}")
    else:
        print("Missing values are in non-critical columns.")

# Cek Duplikat ID
duplicates = df_final["phantom_id"].duplicated().sum()
if duplicates > 0:
    print(f"\n Found {duplicates} duplicate Phantom IDs. Dropping them...")
    df_final = df_final.drop_duplicates(subset="phantom_id").reset_index(drop=True)

print("\nUnique Shells :", sorted(df_final["shell"].unique()))
print("\nSample Data:")
print(df_final.head(10))

# ============================================================
# SAVE
# ============================================================

df_final.to_csv(OUTPUT_FILE, index=False)
print(f"\nSaved to : {OUTPUT_FILE}")