#!/usr/bin/env python3
"""
Step 3b (OSM-native) — Build storage.csv from MORA April 2026 (storage rows).

Bus assignment uses the same 4-stage pipeline as build_gen_table.py:

  Stage 1 — V6 osm_id bridge (exact):
    unit_code → SP RESOURCE_NODE → SP SUBSTATION name
    → V6 ercot_substation (with osm_id set) → NODES array → OSM Bus ID
    Also tried with unit_code underscore-prefix candidates.

  Stage 2 — V6 eia_plant_code bridge:
    unit_code candidates → V6 ercot_substation → eia_plant_code
    → EIA-860 plant lat/lon → nearest OSM substation node (10 km, fallback 20 km).

  Stage 3 — County + tech → EIA plant → OSM snap:
    For units with no V6 link, find EIA-860 storage plants in the same Texas
    county; snap the nearest such plant's lat/lon to the nearest OSM substation
    node (10 km).

  Stage 4 — County centroid → nearest OSM substation (last resort):
    Uses MORA county centroid (Census 2020) and snaps within 50 km.

Energy capacity:
  - If EIA-860 Form 3_4 has a record for this unit (matched by Plant Code from
    V6 bridge, or by Plant Name fuzzy match), use Nameplate Energy Capacity (MWh).
  - Fallback: installed_mw >= 100 → 4× MW; installed_mw < 100 → 2× MW.

Output: sced_inputs/SourceData/storage.csv
  Columns:
    STORAGE UID, Bus ID, Discharge Rate MW, Charge Rate MW, Energy Capacity MWh,
    Initial SOC MWh, Charge Efficiency, Discharge Efficiency

EIA-860 storage schedule: Realist/grid_data/3_4_Energy_Storage_Y2024.xlsx
MORA: Realist/grid_data/MORA_April2026_unit_capacities.csv
"""

import json
import math
import os
import re
from pathlib import Path
from collections import defaultdict

import pandas as pd

# ---------------------------------------------------------------------------
# Paths — cluster-aware (DARTBOARD_SCRATCH env var mirrors run_sced.py)
# ---------------------------------------------------------------------------
if os.environ.get("DARTBOARD_SCRATCH"):
    _SCRATCH = Path(os.environ["DARTBOARD_SCRATCH"])
    DATA     = _SCRATCH / "grid_data"
    SCED_DIR = _SCRATCH / "sced_inputs"
    HTML_FILE = _SCRATCH / "grid_data" / "grid_visualizer.html"
    EIA_CSV   = _SCRATCH / "grid_data" / "eia860_generators.csv"
else:
    REPO     = Path(__file__).resolve().parents[2]
    DATA     = REPO / "Realist" / "grid_data"
    SCED_DIR = Path(os.environ["SCED_DIR_OVERRIDE"]) if os.environ.get("SCED_DIR_OVERRIDE") else DATA / "sced_inputs"
    HTML_FILE = Path(os.environ["VIZ_HTML"]) if os.environ.get("VIZ_HTML") else REPO / "Realist" / "grid_visualizer.html"
    EIA_CSV   = REPO / "Birchfield" / "data" / "processed" / "eia860_generators.csv"

SRC_DIR  = SCED_DIR / "SourceData"
SRC_DIR.mkdir(parents=True, exist_ok=True)

MORA_CSV    = DATA / "MORA_April2026_unit_capacities.csv"
SP_CSV      = DATA / "SP_List_EB_Mapping" / "Settlement_Points_01292026_104938.csv"
V6_CSV      = DATA / "matching_results" / "texas_matched_substations_v6.csv"
EIA_STOR_XLSX = DATA / "3_4_Energy_Storage_Y2024.xlsx"
EIA_STOR_CSV  = DATA / "3_4_Energy_Storage_Y2024_operable.csv"

# ---------------------------------------------------------------------------
# Storage-specific constants
# ---------------------------------------------------------------------------
# One-way Li-ion efficiency (charge or discharge).  The round-trip efficiency
# implied by the pair is 0.96 * 0.96 = 0.9216, consistent with current BESS.
BESS_EFFICIENCY = 0.96

# Energy-to-power ratio fallback when EIA-860 does not have a record:
#   >=100 MW BESS → 4-hour duration (utility scale)
#   < 100 MW BESS → 2-hour duration (smaller / co-located units)
E2P_LARGE = 4.0   # hours
E2P_SMALL = 2.0   # hours
MW_THRESHOLD_LARGE = 100.0   # MW; >= this → use 4h ratio

# Initial state of charge: 50% of energy capacity (neutral starting point)
INITIAL_SOC_FRAC = 0.5

# ---------------------------------------------------------------------------
# County centroids (Census 2020) — Stage 4 last-resort fallback
# Copied from build_gen_table.py so this script is self-contained.
# ---------------------------------------------------------------------------
TEXAS_COUNTY_POP = {
    "Anderson":      (31.82,  -95.65,   57_863),
    "Andrews":       (32.31, -102.64,   18_705),
    "Angelina":      (31.37,  -94.62,   86_771),
    "Aransas":       (28.12,  -97.05,   23_510),
    "Archer":        (33.62,  -98.69,    8_474),
    "Armstrong":     (34.97, -101.36,    1_848),
    "Atascosa":      (28.89,  -98.53,   48_781),
    "Austin":        (29.89,  -96.28,   30_167),
    "Bailey":        (34.07, -102.83,    6_985),
    "Bandera":       (29.75,  -99.25,   21_941),
    "Bastrop":       (30.10,  -97.31,   97_216),
    "Baylor":        (33.62,  -99.22,    3_530),
    "Bee":           (28.42,  -97.74,   32_691),
    "Bell":          (31.05,  -97.48,  362_924),
    "Bexar":         (29.45,  -98.52, 2_009_324),
    "Blanco":        (30.26,  -98.41,   11_279),
    "Borden":        (32.74, -101.43,      641),
    "Bosque":        (31.90,  -97.64,   18_685),
    "Bowie":         (33.44,  -94.16,   94_090),
    "Brazoria":      (29.17,  -95.49,  372_031),
    "Brazos":        (30.66,  -96.30,  229_211),
    "Brewster":      (29.79, -103.25,    9_203),
    "Briscoe":       (34.53, -101.20,    1_546),
    "Brooks":        (27.03,  -98.22,    7_076),
    "Brown":         (31.77,  -99.00,   37_864),
    "Burleson":      (30.49,  -96.61,   18_443),
    "Burnet":        (30.79,  -98.23,   47_597),
    "Caldwell":      (29.83,  -97.62,   45_883),
    "Calhoun":       (28.44,  -96.61,   21_290),
    "Callahan":      (32.30,  -99.37,   13_943),
    "Cameron":       (26.15,  -97.58,  423_163),
    "Camp":          (33.00,  -94.98,   13_094),
    "Carson":        (35.40, -101.35,    5_926),
    "Cass":          (33.07,  -94.34,   30_016),
    "Castro":        (34.53, -102.26,    7_530),
    "Chambers":      (29.71,  -94.63,   45_689),
    "Cherokee":      (31.83,  -95.17,   52_646),
    "Childress":     (34.53, -100.21,    7_306),
    "Clay":          (33.78,  -98.20,   10_303),
    "Cochran":       (33.60, -102.84,    2_547),
    "Coke":          (31.89, -100.52,    3_009),
    "Coleman":       (31.77,  -99.43,    8_547),
    "Collin":        (33.19,  -96.57, 1_064_465),
    "Collingsworth": (34.96, -100.27,    2_920),
    "Colorado":      (29.62,  -96.53,   21_493),
    "Comal":         (29.82,  -98.27,  156_209),
    "Comanche":      (31.95,  -98.56,   13_635),
    "Concho":        (31.32,  -99.74,    2_726),
    "Cooke":         (33.64,  -97.21,   41_071),
    "Coryell":       (31.39,  -97.79,   80_766),
    "Cottle":        (34.08, -100.28,    1_398),
    "Crane":         (31.43, -102.35,    4_797),
    "Crockett":      (30.72, -101.42,    3_405),
    "Crosby":        (33.61, -101.30,    5_737),
    "Culberson":     (31.44, -104.52,    2_163),
    "Dallam":        (36.28, -102.60,    6_703),
    "Dallas":        (32.77,  -96.80, 2_613_539),
    "Dawson":        (32.74, -101.95,   12_547),
    "Deaf Smith":    (34.96, -102.60,   18_546),
    "Delta":         (33.39,  -95.68,    5_331),
    "Denton":        (33.21,  -97.13,  906_422),
    "DeWitt":        (29.09,  -97.35,   20_097),
    "Dickens":       (33.62, -100.79,    2_211),
    "Dimmit":        (28.43,  -99.75,   10_124),
    "Donley":        (34.96, -100.81,    3_278),
    "Duval":         (27.68,  -98.49,   11_157),
    "Eastland":      (32.31,  -98.82,   18_583),
    "Ector":         (31.87, -102.53,  166_223),
    "Edwards":       (29.98, -100.30,    1_932),
    "El Paso":       (31.77, -106.49,  865_657),
    "Ellis":         (32.35,  -96.76,  185_141),
    "Erath":         (32.23,  -98.20,   43_564),
    "Falls":         (31.27,  -96.93,   17_297),
    "Fannin":        (33.59,  -96.11,   36_496),
    "Fayette":       (29.88,  -96.92,   25_066),
    "Fisher":        (32.74, -100.40,    3_848),
    "Floyd":         (33.97, -101.30,    5_728),
    "Foard":         (33.98,  -99.78,    1_186),
    "Fort Bend":     (29.53,  -95.77,  811_688),
    "Franklin":      (33.17,  -95.22,   10_720),
    "Freestone":     (31.70,  -96.15,   19_717),
    "Frio":          (28.87,  -99.11,   20_306),
    "Gaines":        (32.74, -102.63,   22_010),
    "Galveston":     (29.37,  -94.85,  342_139),
    "Garza":         (33.18, -101.30,    6_229),
    "Gillespie":     (30.32,  -98.94,   26_208),
    "Glasscock":     (31.87, -101.52,    1_408),
    "Goliad":        (28.66,  -97.45,    7_658),
    "Gonzales":      (29.46,  -97.49,   20_837),
    "Gray":          (35.40, -100.81,   21_886),
    "Grayson":       (33.62,  -96.68,  136_212),
    "Gregg":         (32.47,  -94.82,  123_945),
    "Grimes":        (30.54,  -95.93,   28_880),
    "Guadalupe":     (29.61,  -97.96,  166_847),
    "Hale":          (34.07, -101.82,   33_406),
    "Hall":          (34.53, -100.68,    2_964),
    "Hamilton":      (31.69,  -98.11,    8_461),
    "Hansford":      (36.28, -101.35,    5_399),
    "Hardeman":      (34.29,  -99.75,    3_801),
    "Hardin":        (30.27,  -94.36,   57_602),
    "Harris":        (29.85,  -95.40, 4_731_145),
    "Harrison":      (32.55,  -94.38,   66_553),
    "Hartley":       (35.84, -102.60,    5_576),
    "Haskell":       (33.18,  -99.73,    5_336),
    "Hays":          (30.06,  -98.03,  246_521),
    "Hemphill":      (35.84, -100.27,    3_819),
    "Henderson":     (32.22,  -95.85,   82_737),
    "Hidalgo":       (26.40,  -98.10,  870_781),
    "Hill":          (31.99,  -97.13,   35_399),
    "Hockley":       (33.61, -102.35,   23_006),
    "Hood":          (32.44,  -97.82,   64_099),
    "Hopkins":       (33.15,  -95.56,   37_084),
    "Houston":       (31.32,  -95.42,   22_968),
    "Howard":        (32.31, -101.44,   36_664),
    "Hudspeth":      (31.46, -105.38,    4_886),
    "Hunt":          (33.13,  -96.09,   99_630),
    "Hutchinson":    (35.84, -101.35,   21_061),
    "Irion":         (31.32, -100.98,    1_536),
    "Jack":          (33.23,  -98.17,    9_003),
    "Jackson":       (28.96,  -96.58,   14_591),
    "Jasper":        (30.72,  -93.99,   35_710),
    "Jeff Davis":    (30.72, -104.12,    2_274),
    "Jefferson":     (30.04,  -94.17,  252_358),
    "Jim Hogg":      (27.06,  -99.08,    5_300),
    "Jim Wells":     (27.73,  -98.08,   40_128),
    "Johnson":       (32.38,  -97.37,  179_685),
    "Jones":         (32.74,  -99.87,   19_891),
    "Karnes":        (28.89,  -97.86,   15_505),
    "Kaufman":       (32.60,  -96.28,  136_154),
    "Kendall":       (29.95,  -98.70,   46_687),
    "Kenedy":        (26.93,  -97.65,      404),
    "Kent":          (33.18, -100.77,      762),
    "Kerr":          (30.06,  -99.34,   53_635),
    "Kimble":        (30.50,  -99.74,    4_472),
    "King":          (33.62, -100.26,      272),
    "Kinney":        (29.35, -100.42,    3_667),
    "Kleberg":       (27.43,  -97.81,   31_549),
    "Knox":          (33.60,  -99.76,    3_664),
    "La Salle":      (28.34,  -99.10,    7_430),
    "Lamar":         (33.67,  -95.54,   49_532),
    "Lamb":          (34.07, -102.35,   13_262),
    "Lampasas":      (31.19,  -98.24,   21_281),
    "Lavaca":        (29.38,  -96.92,   20_154),
    "Lee":           (30.32,  -97.04,   17_239),
    "Leon":          (31.29,  -95.97,   17_151),
    "Liberty":       (30.17,  -94.82,   90_697),
    "Limestone":     (31.54,  -96.59,   23_437),
    "Lipscomb":      (36.28, -100.27,    3_233),
    "Live Oak":      (28.35,  -98.12,   12_207),
    "Llano":         (30.71,  -98.69,   20_860),
    "Loving":        (31.85, -103.59,       64),
    "Lubbock":       (33.61, -101.82,  310_569),
    "Lynn":          (33.18, -101.82,    5_808),
    "Madison":       (30.97,  -95.92,   14_218),
    "Marion":        (33.00,  -94.36,   10_083),
    "Martin":        (32.31, -101.95,    5_771),
    "Mason":         (30.73,  -99.23,    4_274),
    "Matagorda":     (28.79,  -96.01,   36_702),
    "Maverick":      (28.74, -100.31,   57_887),
    "McCulloch":     (31.20,  -99.34,    7_984),
    "McLennan":      (31.55,  -97.17,  262_065),
    "McMullen":      (28.35,  -98.57,      707),
    "Medina":        (29.35,  -99.11,   50_607),
    "Menard":        (30.88,  -99.82,    2_148),
    "Midland":       (32.00, -102.08,  169_895),
    "Milam":         (30.79,  -96.97,   24_823),
    "Mills":         (31.49,  -98.60,    4_873),
    "Mitchell":      (32.31, -100.92,    8_545),
    "Montague":      (33.67,  -97.73,   19_546),
    "Montgomery":    (30.30,  -95.50,  620_443),
    "Moore":         (35.84, -101.89,   21_904),
    "Morris":        (33.11,  -94.71,   12_388),
    "Motley":        (34.07, -100.79,    1_156),
    "Nacogdoches":   (31.62,  -94.65,   64_785),
    "Navarro":       (32.05,  -96.47,   50_125),
    "Newton":        (30.77,  -93.73,   13_488),
    "Nolan":         (32.31, -100.40,   14_669),
    "Nueces":        (27.73,  -97.59,  342_510),
    "Ochiltree":     (36.28, -100.81,    9_836),
    "Oldham":        (35.40, -102.60,    1_911),
    "Orange":        (30.13,  -93.86,   84_047),
    "Palo Pinto":    (32.74,  -98.30,   28_409),
    "Panola":        (32.15,  -94.31,   23_440),
    "Parker":        (32.77,  -97.81,  148_222),
    "Parmer":        (34.53, -102.78,    9_605),
    "Pecos":         (30.79, -102.72,   15_823),
    "Polk":          (30.82,  -94.83,   51_353),
    "Potter":        (35.40, -101.88,  117_415),
    "Presidio":      (29.79, -104.35,    6_131),
    "Rains":         (32.87,  -95.79,   12_514),
    "Randall":       (34.96, -101.89,  140_977),
    "Reagan":        (31.37, -101.52,    3_367),
    "Real":          (29.83,  -99.83,    3_389),
    "Red River":     (33.63,  -94.99,   12_023),
    "Reeves":        (31.32, -103.69,   15_976),
    "Refugio":       (28.33,  -97.16,    7_236),
    "Roberts":       (35.84, -100.81,      885),
    "Robertson":     (31.02,  -96.51,   16_953),
    "Rockwall":      (32.92,  -96.41,  107_741),
    "Runnels":       (31.83,  -99.97,   10_264),
    "Rusk":          (32.11,  -94.77,   53_595),
    "Sabine":        (31.35,  -93.87,   10_542),
    "San Augustine": (31.39,  -94.17,    8_490),
    "San Jacinto":   (30.57,  -95.10,   29_773),
    "San Patricio":  (27.97,  -97.52,   67_138),
    "San Saba":      (31.17,  -98.72,    6_055),
    "Schleicher":    (30.90, -100.54,    2_793),
    "Scurry":        (32.74, -100.91,   16_703),
    "Shackelford":   (32.74,  -99.35,    3_282),
    "Shelby":        (31.79,  -94.14,   25_048),
    "Sherman":       (36.28, -101.89,    3_034),
    "Smith":         (32.38,  -95.27,  232_751),
    "Somervell":     (32.22,  -97.77,    9_128),
    "Starr":         (26.56,  -98.77,   64_633),
    "Stephens":      (32.73,  -98.82,    9_366),
    "Sterling":      (31.83, -101.05,    1_291),
    "Stonewall":     (33.18, -100.25,    1_285),
    "Sutton":        (30.51, -100.53,    3_786),
    "Swisher":       (34.53, -101.74,    7_236),
    "Tarrant":       (32.77,  -97.29, 2_110_640),
    "Taylor":        (32.31,  -99.89,  138_034),
    "Terrell":       (30.22, -102.08,      775),
    "Terry":         (33.18, -102.35,   12_004),
    "Throckmorton":  (33.18,  -99.21,    1_517),
    "Titus":         (33.21,  -94.96,   32_750),
    "Tom Green":     (31.40, -100.45,  119_664),
    "Travis":        (30.33,  -97.77, 1_290_188),
    "Trinity":       (31.09,  -95.37,   14_585),
    "Tyler":         (30.77,  -94.35,   21_672),
    "Upshur":        (32.73,  -94.96,   41_782),
    "Upton":         (31.37, -102.05,    3_657),
    "Uvalde":        (29.36,  -99.78,   25_926),
    "Val Verde":     (29.89, -101.15,   48_879),
    "Van Zandt":     (32.56,  -95.83,   56_590),
    "Victoria":      (28.80,  -96.98,   92_084),
    "Walker":        (30.74,  -95.57,   72_791),
    "Waller":        (30.00,  -95.99,   55_246),
    "Ward":          (31.51, -103.10,   11_998),
    "Washington":    (30.21,  -96.39,   34_796),
    "Webb":          (27.74,  -99.51,  276_652),
    "Wharton":       (29.31,  -96.21,   41_551),
    "Wheeler":       (35.40, -100.27,    5_056),
    "Wichita":       (33.99,  -98.71,  131_818),
    "Wilbarger":     (34.09,  -99.25,   12_769),
    "Willacy":       (26.47,  -97.82,   20_880),
    "Williamson":    (30.65,  -97.60,  609_017),
    "Wilson":        (29.18,  -98.07,   51_584),
    "Winkler":       (31.85, -103.06,    7_802),
    "Wise":          (33.21,  -97.65,   77_028),
    "Wood":          (32.78,  -95.38,   45_539),
    "Yoakum":        (33.18, -102.82,    8_713),
    "Young":         (33.17,  -98.68,   17_806),
    "Zapata":        (27.07,  -99.17,   14_179),
    "Zavala":        (28.86,  -99.76,   12_166),
}

# EIA technology keyword → "STORAGE" — used in Stage 3 county+tech search.
# All rows in the EIA-860 storage schedule are battery/BESS by definition,
# so we accept any technology string.
EIA_STOR_TECH_KEYWORDS: list[str] = []   # empty → accept all


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Load input files
# ---------------------------------------------------------------------------
print("Loading input files...")

mora = pd.read_csv(MORA_CSV, dtype=str)
sp   = pd.read_csv(SP_CSV,   dtype=str)
v6   = pd.read_csv(V6_CSV,   dtype=str)
eia  = pd.read_csv(EIA_CSV)

# EIA-860 Schedule 3.4 — Energy Storage (operable units, Texas only)
# Prefer pre-converted CSV (no openpyxl needed); fall back to Excel.
if EIA_STOR_CSV.exists():
    eia_stor_raw = pd.read_csv(EIA_STOR_CSV)
else:
    eia_stor_raw = pd.read_excel(EIA_STOR_XLSX, sheet_name="Operable", header=1)
eia_stor_tx  = eia_stor_raw[eia_stor_raw["State"] == "TX"].copy()
print(f"  EIA-860 storage (TX, operable): {len(eia_stor_tx):,} units")

# Build two lookup tables from the EIA-860 storage schedule:
#   1. plant_code (int) → nameplate_mwh (first numeric row per plant_code)
#   2. plant_name_norm (lowercase, stripped) → nameplate_mwh (for fuzzy match)
eia_stor_tx["_pc"] = pd.to_numeric(eia_stor_tx["Plant Code"], errors="coerce")
eia_stor_tx["_mwh"] = pd.to_numeric(
    eia_stor_tx["Nameplate Energy Capacity (MWh)"], errors="coerce"
)
# Per-plant aggregation: some plants have multiple generator rows; sum MWh per plant.
# (MORA tracks units that may span multiple EIA generator IDs at the same plant.)
eia_stor_tx_pc = (
    eia_stor_tx[eia_stor_tx["_pc"].notna() & eia_stor_tx["_mwh"].notna()]
    .groupby("_pc")["_mwh"].sum()
    .to_dict()
)   # plant_code (int) → total_mwh (float)

eia_stor_tx["_name_norm"] = (
    eia_stor_tx["Plant Name"].fillna("").str.lower().str.strip()
)
eia_stor_tx_name = (
    eia_stor_tx[(eia_stor_tx["_name_norm"] != "") & eia_stor_tx["_mwh"].notna()]
    .groupby("_name_norm")["_mwh"].sum()
    .to_dict()
)   # plant_name_norm → total_mwh (float)

print(f"  EIA-860 storage plant-code index: {len(eia_stor_tx_pc):,} plants")
print(f"  EIA-860 storage plant-name index: {len(eia_stor_tx_name):,} plant names")

# ---------------------------------------------------------------------------
# Parse NODES from grid_visualizer.html
# ---------------------------------------------------------------------------
print("Parsing NODES from grid_visualizer.html...")
html = HTML_FILE.read_text(encoding="utf-8")
m = re.search(r"const NODES\s*=\s*(\[.*?\]);", html, re.DOTALL)
if not m:
    raise RuntimeError("Could not find NODES array in grid_visualizer.html")
nodes = json.loads(m.group(1))

# Load the connectivity-filtered bus set (written by build_osm_branch_table.py).
# Snap must only target buses that survived the largest-component filter.
OSM_BUS_CSV = SCED_DIR / "osm_bus.csv"
if not OSM_BUS_CSV.exists():
    raise FileNotFoundError(
        f"{OSM_BUS_CSV} not found. Run build_osm_bus_table.py and "
        "build_osm_branch_table.py first."
    )
connected_bus_ids = set(pd.read_csv(OSM_BUS_CSV)["Bus ID"].tolist())

# osm_id string → Bus ID (substation nodes only, connected buses only)
osm_str_to_bid = {
    str(n["id"]): n["i"]
    for n in nodes
    if not n.get("split") and n.get("id") and n["i"] in connected_bus_ids
}

# Substation nodes with position for geo-snap (connected buses only)
sub_node_positions = [
    (n["i"], float(n["lat"]), float(n["lon"]))
    for n in nodes
    if not n.get("split") and n["i"] in connected_bus_ids
]

print(f"  OSM substation nodes (connected): {len(sub_node_positions):,}")

# ---------------------------------------------------------------------------
# Build grid index over OSM substation nodes  (used by snap_to_osm)
# ---------------------------------------------------------------------------
CELL = 0.05   # ~5.5 km; enough resolution for 10 km snap radius

osm_grid = defaultdict(list)
for bid, lat, lon in sub_node_positions:
    osm_grid[(int(lat / CELL), int(lon / CELL))].append((bid, lat, lon))


def snap_to_osm(lat: float, lon: float, max_km: float = 10.0):
    """Return Bus ID of nearest OSM substation node within max_km, or None."""
    ci, cj = int(lat / CELL), int(lon / CELL)
    best_bid  = None
    best_dist = max_km + 1.0
    r = max(1, int(max_km / (CELL * 111)) + 1)
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            for bid, nlat, nlon in osm_grid.get((ci + di, cj + dj), []):
                d = haversine_km(lat, lon, nlat, nlon)
                if d < best_dist:
                    best_dist = d
                    best_bid  = bid
    return best_bid


# ---------------------------------------------------------------------------
# Pre-snap EIA-860 Texas generator plants to nearest OSM substation
# (same pre-snap cache used by build_gen_table.py)
# ---------------------------------------------------------------------------
print("Pre-snapping EIA-860 TX generator plants to OSM substations...")

eia_tx = eia[eia["state"] == "TX"].copy()
plant_locs = (
    eia_tx.groupby("plant_code")[["lat", "lon", "technology"]]
    .first()
    .reset_index()
)

# plant_code → (lat, lon, technology_str, osm_bus_id_or_None)
eia_plant_info: dict[int, tuple] = {}
n_eia_snapped = 0
for _, row in plant_locs.iterrows():
    pc   = int(row["plant_code"])
    plat = float(row["lat"])
    plon = float(row["lon"])
    tech = str(row.get("technology", "")).lower()
    bid  = snap_to_osm(plat, plon, max_km=10.0)
    eia_plant_info[pc] = (plat, plon, tech, bid)
    if bid is not None:
        n_eia_snapped += 1

print(f"  EIA TX plants: {len(eia_plant_info):,}  "
      f"snapped within 10 km: {n_eia_snapped:,}")

# List of (plant_code, lat, lon, tech_str, bus_id_or_None) for Stage 3 search.
eia_plant_list = [
    (pc, info[0], info[1], info[2], info[3])
    for pc, info in eia_plant_info.items()
]

# ---------------------------------------------------------------------------
# Also pre-snap EIA-860 storage plants (TX, 3_4 schedule) to OSM
# ---------------------------------------------------------------------------
print("Pre-snapping EIA-860 TX storage plants to OSM substations...")

# The 3_4 schedule does not include lat/lon; we use the generator plant_code
# to look up coordinates from the main eia860_generators.csv where available.
# If a plant_code from the storage schedule exists in eia_plant_info, we already
# have its lat/lon.  Otherwise we skip.
eia_stor_snapped: dict[int, int] = {}   # plant_code → bus_id
for pc_float, row_grp in eia_stor_tx[eia_stor_tx["_pc"].notna()].groupby("_pc"):
    pc = int(pc_float)
    info = eia_plant_info.get(pc)
    if info and info[3] is not None:
        eia_stor_snapped[pc] = info[3]

print(f"  EIA storage plants with OSM snap: {len(eia_stor_snapped):,}")

# ---------------------------------------------------------------------------
# Build Stage 1+2 lookups from V6
# ---------------------------------------------------------------------------

# ercot_substation name → bus_id (via osm_id → NODES)  — Stage 1
ercot_to_bid_osm: dict[str, int] = {}
for _, row in v6.iterrows():
    ercot      = str(row.get("ercot_substation", "")).strip()
    osm_id_str = str(row.get("osm_id", "")).strip()
    if not ercot or osm_id_str in ("", "nan"):
        continue
    bid = osm_str_to_bid.get(osm_id_str)
    if bid is not None:
        ercot_to_bid_osm[ercot] = bid

# ercot_substation name → eia_plant_code (rows with eia_plant_code set) — Stage 2
ercot_to_eia_pc: dict[str, int] = {}
for _, row in v6.iterrows():
    ercot  = str(row.get("ercot_substation", "")).strip()
    eia_pc = str(row.get("eia_plant_code", "")).strip()
    if not ercot or eia_pc in ("", "nan"):
        continue
    try:
        ercot_to_eia_pc[ercot] = int(float(eia_pc))
    except (ValueError, TypeError):
        pass

print(f"  Stage 1 (V6 osm_id map):      {len(ercot_to_bid_osm):,} ERCOT substations")
print(f"  Stage 2 (V6 eia_plant_code):  {len(ercot_to_eia_pc):,} ERCOT substations")

# SP: RESOURCE_NODE → SUBSTATION name
sp_rn_valid  = sp[sp["RESOURCE_NODE"].notna() & (sp["RESOURCE_NODE"] != "")].copy()
sp_rn_to_sub = (
    sp_rn_valid
    .drop_duplicates("RESOURCE_NODE", keep="first")
    .set_index("RESOURCE_NODE")["SUBSTATION"]
    .to_dict()
)

# ---------------------------------------------------------------------------
# Filter MORA to storage-only rows
# ---------------------------------------------------------------------------
mora_stor = mora[mora["fuel"] == "STORAGE"].copy()
mora_stor["_mw"] = pd.to_numeric(mora_stor["installed_mw"], errors="coerce")
mora_stor = mora_stor[mora_stor["_mw"].notna() & (mora_stor["_mw"] > 0)].copy()
mora_stor = mora_stor.reset_index(drop=True)
print(f"  MORA STORAGE units: {len(mora_stor):,}")


# ---------------------------------------------------------------------------
# resolve_bus_id — identical 4-stage pipeline to build_gen_table.py
# Storage units connect at substations just like generators.
# ---------------------------------------------------------------------------

def extract_prefixes(code: str) -> list[str]:
    """Return all underscore-split prefix candidates from unit_code."""
    parts = code.split("_")
    return ["_".join(parts[:i]) for i in range(len(parts), 0, -1)]


def eia_county_snap(county: str, max_county_km: float = 150.0):
    """
    Stage 3: find EIA-860 storage plants near county centroid, snap to OSM.

    All plants in the EIA-860 storage schedule (3_4) are BESS/batteries, so
    there is no technology filter.  We use the generator lat/lon from the main
    EIA-860 plant index (eia_plant_list) but restrict the search to plant_codes
    that also appear in the storage schedule.

    Falls through (returns None) if no EIA storage plant snaps within 10 km of
    an OSM substation.
    """
    if county not in TEXAS_COUNTY_POP:
        return None
    clat, clon, _ = TEXAS_COUNTY_POP[county]

    best_bid  = None
    best_dist = max_county_km + 1.0

    for pc, plat, plon, tech, bid in eia_plant_list:
        if bid is None:
            continue
        # Only consider plants that appear in the EIA-860 storage schedule
        if pc not in eia_stor_snapped:
            continue
        d = haversine_km(clat, clon, plat, plon)
        if d < best_dist:
            best_dist = d
            best_bid  = bid

    return best_bid


def resolve_bus_id(unit_code, mora_county):
    """
    Return (bus_id, method_tag) for a BESS row.

    Tries the same 4-stage pipeline as build_gen_table.py:
      Stage 1: unit_code candidates → V6 osm_id → Bus ID
      Stage 2: unit_code candidates → V6 eia_plant_code → EIA lat/lon → OSM snap
      Stage 3: county + storage type → nearest EIA storage plant → OSM snap
      Stage 4: county centroid → nearest OSM substation (last resort)
    """
    code   = str(unit_code).strip() if pd.notna(unit_code) else ""
    county = str(mora_county).strip().title() if pd.notna(mora_county) else ""

    # Build ERCOT substation name candidates from unit_code
    candidates = []
    if code:
        rn_sub = sp_rn_to_sub.get(code)
        if rn_sub:
            candidates.append(str(rn_sub).strip())
        candidates.extend(extract_prefixes(code))

    # Stage 1: candidate ERCOT substation → V6 osm_id → Bus ID
    for cand in candidates:
        bid = ercot_to_bid_osm.get(cand)
        if bid is not None:
            return bid, "stage1_v6_osm"

    # Stage 2: candidate ERCOT substation → V6 eia_plant_code → EIA lat/lon → OSM snap
    for cand in candidates:
        pc = ercot_to_eia_pc.get(cand)
        if pc is None:
            continue
        info = eia_plant_info.get(pc)
        if info is None:
            continue
        plat, plon, _, bid = info
        if bid is not None:
            return bid, f"stage2_eia_v6:{cand}"
        # EIA plant exists but no OSM within 10 km — try a wider snap (20 km)
        bid = snap_to_osm(plat, plon, max_km=20.0)
        if bid is not None:
            return bid, f"stage2_eia_v6_wide:{cand}"

    # Stage 3: county → nearest EIA storage plant → OSM snap
    bid = eia_county_snap(county)
    if bid is not None:
        return bid, f"stage3_eia_county:{county}"

    # Stage 4: county centroid → nearest OSM substation (last resort)
    if county in TEXAS_COUNTY_POP:
        clat, clon, _ = TEXAS_COUNTY_POP[county]
        bid = snap_to_osm(clat, clon, max_km=50.0)
        if bid is not None:
            return bid, f"stage4_county_centroid:{county}"

    return None, "unmatched"


# ---------------------------------------------------------------------------
# Build EIA-860 energy capacity lookup keyed on unit_name and unit_code
# ---------------------------------------------------------------------------

def lookup_eia_energy_mwh(unit_code: str, unit_name: str,
                          candidates: list[str]) -> float | None:
    """
    Try to find an EIA-860 energy capacity (MWh) for this MORA storage unit.

    Lookup order:
      1. V6 eia_plant_code from unit_code candidates → eia_stor_tx_pc dict
      2. Normalised plant-name fuzzy match in eia_stor_tx_name dict
         (try unit_name, then each candidate prefix)
    Returns the MWh float, or None if not found.
    """
    # 1. Plant-code bridge via V6
    for cand in candidates:
        pc = ercot_to_eia_pc.get(cand)
        if pc is not None:
            mwh = eia_stor_tx_pc.get(pc)
            if mwh is not None and mwh > 0:
                return float(mwh)

    # 2. Plant-name normalised string match
    for name in ([unit_name] + candidates):
        if not name:
            continue
        norm = name.lower().strip()
        mwh = eia_stor_tx_name.get(norm)
        if mwh is not None and mwh > 0:
            return float(mwh)

    return None


# ---------------------------------------------------------------------------
# Build storage.csv rows
# ---------------------------------------------------------------------------
print("Building storage.csv rows...")

stor_rows  = []
stage_counts  = defaultdict(int)
eia_mwh_count = 0
fallback_count = 0
unmatched_list = []

for _, row in mora_stor.iterrows():
    unit_code   = str(row.get("unit_code", "")).strip()
    unit_name   = str(row.get("unit_name",  "")).strip()
    mora_county = row.get("county", "")
    zone        = str(row.get("zone", "")).strip().upper()
    installed   = float(row["_mw"])

    # Sanitise UID: unit_code if present, else unit_name; truncate to 48 chars
    raw_uid = unit_code if unit_code and unit_code not in ("nan", "") else unit_name
    stor_uid = raw_uid.replace(" ", "_").replace("/", "_")[:48]

    # Build candidate list (same logic as resolve_bus_id)
    candidates = []
    if unit_code:
        rn_sub = sp_rn_to_sub.get(unit_code)
        if rn_sub:
            candidates.append(str(rn_sub).strip())
        candidates.extend(extract_prefixes(unit_code))

    # --- Stage 1–4 bus assignment ---
    bus_id, method = resolve_bus_id(unit_code, mora_county)

    if bus_id is None:
        unmatched_list.append((stor_uid, mora_county, zone))
        continue

    stage_counts[method.split(":")[0]] += 1

    # --- Energy capacity (MWh) ---
    mwh = lookup_eia_energy_mwh(unit_code, unit_name, candidates)
    if mwh is not None and mwh > 0:
        eia_mwh_count += 1
        mwh_source = "eia860"
    else:
        # Fallback: duration-based estimate from installed MW
        duration = E2P_LARGE if installed >= MW_THRESHOLD_LARGE else E2P_SMALL
        mwh = round(installed * duration, 2)
        fallback_count += 1
        mwh_source = f"fallback_{duration:.0f}h"

    initial_soc = round(mwh * INITIAL_SOC_FRAC, 4)

    stor_rows.append({
        "STORAGE UID":          stor_uid,
        "Bus ID":               bus_id,
        "Discharge Rate MW":    round(installed, 2),
        "Charge Rate MW":       round(installed, 2),
        "Energy Capacity MWh":  round(mwh, 2),
        "Initial SOC MWh":      initial_soc,
        "Charge Efficiency":    BESS_EFFICIENCY,
        "Discharge Efficiency": BESS_EFFICIENCY,
        # Extra diagnostic columns (not read by Vatic; removed if you prefer)
        "_zone":       zone,
        "_mwh_source": mwh_source,
    })

# Deduplicate STORAGE UIDs (same logic as build_gen_table.py gen UID dedup)
uid_count = defaultdict(int)
for r in stor_rows:
    uid_count[r["STORAGE UID"]] += 1

uid_seen = defaultdict(int)
for r in stor_rows:
    uid = r["STORAGE UID"]
    if uid_count[uid] > 1:
        uid_seen[uid] += 1
        r["STORAGE UID"] = f"{uid}_{uid_seen[uid]}"

# ---------------------------------------------------------------------------
# Write storage.csv
# ---------------------------------------------------------------------------
print("Writing outputs...")

stor_df = pd.DataFrame(stor_rows, columns=[
    "STORAGE UID",
    "Bus ID",
    "Discharge Rate MW",
    "Charge Rate MW",
    "Energy Capacity MWh",
    "Initial SOC MWh",
    "Charge Efficiency",
    "Discharge Efficiency",
    # diagnostic columns preserved for audit
    "_zone",
    "_mwh_source",
])
stor_df.to_csv(SRC_DIR / "storage.csv", index=False)
print(f"  Wrote storage.csv  ({len(stor_df):,} rows)")

# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------
n_total     = len(mora_stor)
n_matched   = len(stor_rows)
n_unmatched = len(unmatched_list)

total_mw  = sum(r["Discharge Rate MW"]    for r in stor_rows)
total_mwh = sum(r["Energy Capacity MWh"] for r in stor_rows)

print()
print("Summary:")
print(f"  MORA STORAGE units:      {n_total:,}")
print(f"  Matched (wrote rows):    {n_matched:,}  ({n_matched/n_total*100:.1f}%)")
print(f"  Unmatched (excluded):    {n_unmatched:,}")
print(f"  Total MW (discharge):    {total_mw:,.1f} MW")
print(f"  Total MWh capacity:      {total_mwh:,.1f} MWh")
print(f"  EIA-860 MWh source:      {eia_mwh_count:,} units")
print(f"  Fallback MWh estimate:   {fallback_count:,} units")
print()
print("  By assignment stage:")
for stage, cnt in sorted(stage_counts.items()):
    print(f"    {stage:35s}: {cnt:4d}")

# Zone breakdown
zone_mw  = defaultdict(float)
zone_mwh = defaultdict(float)
zone_cnt = defaultdict(int)
for r in stor_rows:
    z = r["_zone"] or "UNKNOWN"
    zone_mw[z]  += r["Discharge Rate MW"]
    zone_mwh[z] += r["Energy Capacity MWh"]
    zone_cnt[z] += 1

print()
print("  By zone:")
print(f"    {'Zone':10s}  {'Units':>6s}  {'MW':>10s}  {'MWh':>12s}")
for z in sorted(zone_cnt):
    print(f"    {z:10s}  {zone_cnt[z]:6d}  {zone_mw[z]:10,.1f}  {zone_mwh[z]:12,.1f}")
print(f"    {'TOTAL':10s}  {n_matched:6d}  {total_mw:10,.1f}  {total_mwh:12,.1f}")

if unmatched_list:
    print()
    print("  Unmatched units (uid, county, zone):")
    for uid, county, zone in unmatched_list[:20]:
        print(f"    {str(uid):40s}  {str(county):20s}  {zone}")
    if len(unmatched_list) > 20:
        print(f"    ... and {len(unmatched_list)-20} more")
