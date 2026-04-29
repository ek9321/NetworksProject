"""
Phase 1: Gold Book Extraction

Extracts generator data from the NY Gold Book PDF.

Input: GoldBook.pdf
Output: NY_Generators_Full.csv
"""

import os
import pandas as pd
import pdfplumber

from . import config


def extract_gold_book_generators(pdf_path):
    """Extract generator data from NY Gold Book PDF (basic extraction)."""
    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(83, 103):
            page = pdf.pages[i]
            table = page.extract_table()
            if table:
                start_row = 1 if i == 83 else 2
                all_rows.extend(table[start_row:])
    
    columns = ["Owner", "Station_Unit", "Zone", "PTID", "Town", "County", "State",
               "In_Service", "Nameplate_MW", "CRIS_MW", "Summer_MW", "Winter_MW",
               "Dual_Fuel", "Unit_Type", "Fuel_1", "Fuel_2", "2023_Net_Energy", "Notes"]
    df = pd.DataFrame(all_rows, columns=columns)
    return df


def extract_gold_book_full(pdf_path, output_path):
    """Full Gold Book extraction with dynamic column handling."""
    if not os.path.exists(pdf_path):
        print(f"ERROR: The file was not found at: {pdf_path}")
        return None
    
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 4,
    }

    all_data = []
    valid_zones = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]

    print("Starting Gold Book extraction...")

    with pdfplumber.open(pdf_path) as pdf:
        for i in range(83, 105):
            page = pdf.pages[i]
            table = page.extract_table(table_settings)
            if table:
                for row in table:
                    if len(row) > 3 and row[2] in valid_zones:
                        clean_row = [str(cell).replace("\n", " ") if cell else "" for cell in row]
                        all_data.append(clean_row)
            if i % 5 == 0:
                print(f"  Processed page index {i}...")

    if not all_data:
        print("Error: No data found.")
        return None
    
    max_cols = max(len(row) for row in all_data)
    print(f"  Max columns found: {max_cols}")

    headers = [
        "Owner", "Station_Unit", "Zone", "PTID", "Town", "County", "State",
        "In_Service", "Nameplate_MW", "CRIS_MW", "Summer_MW", "Winter_MW",
        "Dual_Fuel", "Unit_Type", "Fuel_1", "Fuel_2", "Net_Energy_GWh", "Notes"
    ]

    if max_cols > len(headers):
        for i in range(len(headers), max_cols):
            headers.append(f"Extra_Col_{i}")

    padded_data = [row + [""] * (max_cols - len(row)) for row in all_data]
    df_full = pd.DataFrame(padded_data, columns=headers)

    cols_to_numeric = ["Nameplate_MW", "Summer_MW", "Winter_MW", "Net_Energy_GWh"]
    for col in cols_to_numeric:
        if col in df_full.columns:
            df_full[col] = pd.to_numeric(df_full[col].str.replace(",", ""), errors="coerce")

    df_full.to_csv(output_path, index=False)
    print(f"Success! Saved {len(df_full)} rows to {output_path}")
    return df_full


def run(skip_if_exists=False):
    """Run Phase 1: Gold Book extraction."""
    print("\n" + "=" * 60)
    print("Phase 1: Gold Book Extraction")
    print("=" * 60)
    
    config.ensure_directories()
    
    if skip_if_exists and os.path.exists(config.NY_GENERATORS_PATH):
        print(f"Skipping: {config.NY_GENERATORS_PATH} already exists")
        return pd.read_csv(config.NY_GENERATORS_PATH)
    
    if not os.path.exists(config.PDF_PATH):
        print(f"WARNING: Gold Book PDF not found at {config.PDF_PATH}")
        print("Skipping Gold Book extraction.")
        return None
    
    df = extract_gold_book_full(config.PDF_PATH, config.NY_GENERATORS_PATH)
    return df


if __name__ == "__main__":
    run()
