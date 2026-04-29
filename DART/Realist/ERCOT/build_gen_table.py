#!/usr/bin/env python3
"""
Step 3 (OSM-native) — Build gen.csv and init_state.csv from MORA April 2026.

Bus assignment (4 stages, in order):

  Stage 1 — V6 osm_id bridge (exact):
    unit_code → SP RESOURCE_NODE → SP SUBSTATION name
    → V6 ercot_substation (with osm_id set) → NODES array → OSM Bus ID
    Also tried with unit_code underscore-prefix candidates.

  Stage 2 — V6 eia_plant_code bridge:
    Same candidate ERCOT substation name lookup in V6, but this time
    using rows where eia_plant_code is set (osm_id may or may not be set).
    eia_plant_code → EIA-860 plant lat/lon → nearest OSM substation node.
    Snap radius: 10 km.

  Stage 3 — County + fuel → EIA plant → OSM snap:
    For generators with no V6 link at all, find EIA-860 plants in the
    same Texas county with matching technology.  Use the nearest such
    EIA plant's lat/lon → nearest OSM substation node.
    Snap radius: 10 km.  Falls through if no EIA plant snaps within 10 km.

  Stage 4 — County centroid → nearest OSM substation (last resort):
    Uses MORA county centroid (Census 2020) and snaps to nearest OSM
    substation node within 50 km.

Fuel/cost constants and output format are unchanged from the PSSE-based version.

EIA-860 data: Birchfield/data/processed/eia860_generators.csv
  (pre-processed from EIA-860 Form 3_1_Generator.xlsx; all TX rows have lat/lon)

Outputs:
  sced_inputs/SourceData/gen.csv
  sced_inputs/SourceData/init_state.csv
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

MORA_CSV  = DATA / "MORA_April2026_unit_capacities.csv"
SP_CSV    = DATA / "SP_List_EB_Mapping" / "Settlement_Points_01292026_104938.csv"
V6_CSV    = DATA / "matching_results" / "texas_matched_substations_v6.csv"

# ---------------------------------------------------------------------------
# Fuel constants (unchanged)
# ---------------------------------------------------------------------------
FUEL_MAP = {
    "NUCLEAR": ("Nuclear", "N", "Nuclear"),
    "COAL":    ("Coal",    "C", "Coal"),
    "GAS-CC":  ("Gas",     "G", "Gas-CC"),
    "GAS-GT":  ("Gas",     "G", "Gas-GT"),
    "GAS-ST":  ("Gas",     "G", "Gas-ST"),
    "GAS-IC":  ("Gas",     "G", "Gas-IC"),
    "WIND-O":  ("Wind",    "W", "Wind"),
    "WIND-C":  ("Wind",    "W", "Wind"),
    "WIND-P":  ("Wind",    "W", "Wind"),
    "SOLAR":   ("Solar",   "S", "Solar"),
    "HYDRO":   ("Gas",     "G", "Hydro"),
    "BIOMASS": ("Gas",     "G", "Biomass"),
    "DIESEL":  ("Gas",     "G", "Diesel"),
    "OTHER":   ("Gas",     "G", "Other"),
}

PMIN_FRAC = {
    "NUCLEAR": 0.90, "COAL": 0.40, "GAS-CC": 0.30, "GAS-GT": 0.10,
    "GAS-ST":  0.30, "GAS-IC": 0.10, "HYDRO": 0.10, "BIOMASS": 0.20,
    "DIESEL":  0.10, "OTHER": 0.10,
    "WIND-O":  0.0,  "WIND-C": 0.0, "WIND-P": 0.0, "SOLAR": 0.0,
}

FLAT_COST = {
    "NUCLEAR": 8.0,  "COAL": 25.0,  "GAS-CC": 28.0, "GAS-GT": 42.0,
    "GAS-ST":  35.0, "GAS-IC": 45.0,
    "WIND-O":  0.01, "WIND-C": 0.01, "WIND-P": 0.01, "SOLAR": 0.01,
    "HYDRO":   1.0,  "BIOMASS": 40.0, "DIESEL": 60.0, "OTHER": 35.0,
}

RAMP_FRAC = {
    "NUCLEAR": 0.005, "COAL": 0.010, "GAS-CC": 0.020, "GAS-GT": 0.080,
    "GAS-ST":  0.020, "GAS-IC": 0.080,
    "WIND-O":  1.0,   "WIND-C": 1.0,  "WIND-P": 1.0,   "SOLAR": 1.0,
    "HYDRO":   0.050, "BIOMASS": 0.020, "DIESEL": 0.080, "OTHER": 0.020,
}

MIN_TIME = {
    "NUCLEAR": 168, "COAL": 8, "GAS-CC": 4, "GAS-GT": 1,
    "GAS-ST":  4,   "GAS-IC": 1,
    "WIND-O":  0,   "WIND-C": 0, "WIND-P": 0, "SOLAR": 0,
    "HYDRO":   1,   "BIOMASS": 4, "DIESEL": 1, "OTHER": 2,
}

# EIA technology keyword → MORA fuel types it applies to
# Used in Stage 3 to filter EIA plants by technology when searching by county.
EIA_TECH_KEYWORDS = {
    "NUCLEAR": ["nuclear"],
    "COAL":    ["coal"],
    "GAS-CC":  ["combined"],
    "GAS-GT":  ["combustion turbine", "gas turbine"],
    "GAS-ST":  ["steam turbine"],
    "GAS-IC":  ["internal combustion"],
    "WIND-O":  ["wind"], "WIND-C": ["wind"], "WIND-P": ["wind"],
    "SOLAR":   ["solar", "photovoltaic"],
    "HYDRO":   ["hydro"],
    "BIOMASS": ["biomass", "landfill", "wood"],
    "DIESEL":  ["petroleum", "diesel"],
}

# County centroids (lat, lon, Census 2020 pop) — Stage 4 last-resort fallback
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


def is_renewable(mora_fuel):
    return mora_fuel in ("WIND-O", "WIND-C", "WIND-P", "SOLAR")


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
print("Loading input files...")

mora = pd.read_csv(MORA_CSV, dtype=str)
sp   = pd.read_csv(SP_CSV,   dtype=str)
v6   = pd.read_csv(V6_CSV,   dtype=str)
eia  = pd.read_csv(EIA_CSV)

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
SNAP_SEARCH = 3   # cells to search in each direction (~16.5 km radius)

osm_grid = defaultdict(list)
for bid, lat, lon in sub_node_positions:
    osm_grid[(int(lat / CELL), int(lon / CELL))].append((bid, lat, lon))


def snap_to_osm(lat, lon, max_km=10.0):
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
# Pre-snap EIA-860 Texas plants to nearest OSM substation
# ---------------------------------------------------------------------------
print("Pre-snapping EIA-860 TX plants to OSM substations...")

eia_tx = eia[eia["state"] == "TX"].copy()
plant_locs = (
    eia_tx.groupby("plant_code")[["lat", "lon", "technology"]]
    .first()
    .reset_index()
)

# plant_code → (lat, lon, technology_str, osm_bus_id_or_None)
eia_plant_info = {}
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
      f"snapped within 10 km: {n_eia_snapped:,} "
      f"({n_eia_snapped/len(eia_plant_info)*100:.0f}%)")

# Also build a list of (plant_code, lat, lon, tech) for Stage 3 county+tech search
eia_plant_list = [
    (pc, info[0], info[1], info[2], info[3])
    for pc, info in eia_plant_info.items()
]   # (plant_code, lat, lon, tech_str, bus_id_or_None)

# ---------------------------------------------------------------------------
# Build Stage 1+2 lookups from V6
# ---------------------------------------------------------------------------

# ercot_substation name → bus_id (via osm_id → NODES)  — Stage 1
ercot_to_bid_osm = {}
for _, row in v6.iterrows():
    ercot      = str(row.get("ercot_substation", "")).strip()
    osm_id_str = str(row.get("osm_id", "")).strip()
    if not ercot or osm_id_str in ("", "nan"):
        continue
    bid = osm_str_to_bid.get(osm_id_str)
    if bid is not None:
        ercot_to_bid_osm[ercot] = bid

# ercot_substation name → eia_plant_code (rows with eia_plant_code set) — Stage 2
ercot_to_eia_pc = {}
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
sp_rn_valid = sp[sp["RESOURCE_NODE"].notna() & (sp["RESOURCE_NODE"] != "")].copy()
sp_rn_to_sub = (
    sp_rn_valid
    .drop_duplicates("RESOURCE_NODE", keep="first")
    .set_index("RESOURCE_NODE")["SUBSTATION"]
    .to_dict()
)

# ---------------------------------------------------------------------------
# Filter MORA
# ---------------------------------------------------------------------------
mora_ns = mora[~mora["section"].str.contains("Storage", case=False, na=False)].copy()
mora_ns = mora_ns[mora_ns["fuel"] != "STORAGE"].copy()
mora_ns["_mw"] = pd.to_numeric(mora_ns["installed_mw"], errors="coerce")
mora_ns = mora_ns[mora_ns["_mw"].notna() & (mora_ns["_mw"] > 0)].copy()
mora_ns = mora_ns.reset_index(drop=True)
print(f"  MORA non-storage units: {len(mora_ns):,}")


# ---------------------------------------------------------------------------
# resolve_bus_id — 4-stage assignment
# ---------------------------------------------------------------------------

def extract_prefixes(code):
    parts = code.split("_")
    return ["_".join(parts[:i]) for i in range(len(parts), 0, -1)]


def tech_matches(eia_tech_str, mora_fuel):
    """True if EIA technology string matches MORA fuel type."""
    keywords = EIA_TECH_KEYWORDS.get(mora_fuel)
    if keywords is None:
        return True   # "OTHER" — accept any technology
    t = eia_tech_str.lower()
    return any(kw in t for kw in keywords)


def eia_county_snap(county, mora_fuel, max_county_km=150.0):
    """
    Stage 3: find EIA plants near county centroid with matching technology,
    snap each to nearest OSM substation, return the closest successful snap.
    Falls through (returns None) if no EIA plant snaps within 10 km of OSM.

    Returns (bus_id, eia_lat, eia_lon) or (None, None, None).
    """
    if county not in TEXAS_COUNTY_POP:
        return None, None, None
    clat, clon, _ = TEXAS_COUNTY_POP[county]

    best_bid  = None
    best_dist = max_county_km + 1.0
    best_lat, best_lon = None, None

    for pc, plat, plon, tech, bid in eia_plant_list:
        if bid is None:
            continue
        if not tech_matches(tech, mora_fuel):
            continue
        d = haversine_km(clat, clon, plat, plon)
        if d < best_dist:
            best_dist = d
            best_bid  = bid
            best_lat, best_lon = plat, plon

    return best_bid, best_lat, best_lon


# County name normalization: MORA uses ALL-CAPS which .title() mangles for
# McCamelCase names, spaced-out letters, and ampersand-separated multi-counties.
_COUNTY_ALIASES = {
    "Mcculloch": "McCulloch", "Mclennan": "McLennan", "Dewitt": "DeWitt",
    "Mcmullen": "McMullen",  "Mccamey": "McCamey",
}

def _normalize_county(raw):
    """Normalize MORA county string to TEXAS_COUNTY_POP key."""
    if pd.isna(raw) or not str(raw).strip():
        return ""
    s = str(raw).strip()
    # Collapse spaced-out letters: "F O R T B E N D" → "FORT BEND"
    if len(s) > 4 and all(len(w) <= 1 for w in s.split()):
        s = re.sub(r'(?<=\w)\s(?=\w)', '', s)
    # Handle ampersand-separated multi-county: use first county
    if "&" in s:
        s = s.split("&")[0].strip()
    s = s.title()
    return _COUNTY_ALIASES.get(s, s)


_last_eia_coords = [None]  # mutable container for stage 3 EIA plant coords

def resolve_bus_id(unit_code, mora_county, mora_fuel):
    code = str(unit_code).strip() if pd.notna(unit_code) else ""
    county = _normalize_county(mora_county)

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

    # Stage 3: county + fuel type → nearest matching EIA plant → OSM snap
    bid, _s3_lat, _s3_lon = eia_county_snap(county, mora_fuel)
    if bid is not None:
        _last_eia_coords[0] = (_s3_lat, _s3_lon)
        return bid, f"stage3_eia_county:{county}"

    # Stage 4: county centroid → nearest OSM substation (last resort)
    if county in TEXAS_COUNTY_POP:
        clat, clon, _ = TEXAS_COUNTY_POP[county]
        bid = snap_to_osm(clat, clon, max_km=50.0)
        if bid is not None:
            return bid, f"stage4_county_centroid:{county}"

    return None, "unmatched"


# ---------------------------------------------------------------------------
# Build gen.csv rows
# ---------------------------------------------------------------------------
print("Building gen.csv rows...")

gen_rows  = []
init_rows = []

stage_counts = defaultdict(int)
fuel_unmatched = defaultdict(int)

for _, row in mora_ns.iterrows():
    mora_fuel   = str(row.get("fuel", "OTHER")).strip()
    unit_code   = str(row.get("unit_code", "")).strip()
    unit_name   = str(row.get("unit_name", "")).strip()
    mora_county = row.get("county", "")
    installed   = float(row["_mw"])

    raw_uid = unit_code if unit_code and unit_code not in ("nan", "") else unit_name
    gen_uid = raw_uid.replace(" ", "_").replace("/", "_")[:48]

    bus_id, method = resolve_bus_id(unit_code, mora_county, mora_fuel)

    if bus_id is None:
        fuel_unmatched[mora_fuel] += 1
        continue

    stage_counts[method.split(":")[0]] += 1

    # Record source coordinates for visualizer snap-line overlay
    src_lat, src_lon = None, None
    if method.startswith("stage1"):
        # Stage 1: V6 osm_id direct match — source is the ERCOT substation (= bus location)
        pass  # no separate source coord; snap distance ≈ 0
    elif method.startswith("stage2"):
        # Stage 2: EIA plant lat/lon
        cand = method.split(":", 1)[1] if ":" in method else ""
        pc = ercot_to_eia_pc.get(cand)
        if pc and pc in eia_plant_info:
            src_lat, src_lon = eia_plant_info[pc][0], eia_plant_info[pc][1]
    elif method.startswith("stage3"):
        # Stage 3: EIA plant lat/lon (matched via county+fuel search)
        if _last_eia_coords[0] is not None:
            src_lat, src_lon = _last_eia_coords[0]
            _last_eia_coords[0] = None
    elif method.startswith("stage4"):
        # Stage 4: county centroid snap (no better source available)
        county_key = method.split(":", 1)[1] if ":" in method else ""
        if county_key in TEXAS_COUNTY_POP:
            src_lat, src_lon = TEXAS_COUNTY_POP[county_key][0], TEXAS_COUNTY_POP[county_key][1]

    mora_fuel_key = mora_fuel if mora_fuel in FUEL_MAP else "OTHER"
    vatic_fuel, unit_type, unit_group = FUEL_MAP[mora_fuel_key]

    if is_renewable(mora_fuel_key):
        pmax = round(installed, 2)
        pmin = 0.0
    else:
        pmax = round(installed, 2)
        pmin = round(installed * PMIN_FRAC.get(mora_fuel_key, 0.10), 2)

    pmin = min(pmin, pmax)
    if pmax <= 0:
        continue

    ramp_rate = max(RAMP_FRAC.get(mora_fuel_key, 0.02) * pmax, 1.0)
    min_time  = MIN_TIME.get(mora_fuel_key, 2)
    flat_cost = FLAT_COST.get(mora_fuel_key, 35.0)

    gen_rows.append({
        "GEN UID":               gen_uid,
        "Bus ID":                bus_id,
        "Unit Group":            unit_group,
        "Unit Type":             unit_type,
        "Fuel":                  vatic_fuel,
        "PMin MW":               pmin,
        "PMax MW":               pmax,
        "Min Down Time Hr":      min_time,
        "Min Up Time Hr":        min_time,
        "Ramp Rate MW/Min":      round(ramp_rate, 4),
        "Start Time Cold Hr":    min_time,
        "Start Time Warm Hr":    min_time,
        "Start Time Hot Hr":     min_time,
        "Start Heat Cold MBTU":  0.0,
        "Start Heat Warm MBTU":  0.0,
        "Start Heat Hot MBTU":   0.0,
        "Fuel Price $/MMBTU":    0.0,
        "Fixed Cost($/hr)":      0.0,
        "MW Break 1":            pmin,
        "MWh Price 1":           flat_cost,
        "_src_lat":              src_lat,
        "_src_lon":              src_lon,
        "_stage":                method,
    })

    if mora_fuel_key == "NUCLEAR":
        unit_on_t0, power_t0 = 1000, pmin
    elif is_renewable(mora_fuel_key):
        unit_on_t0, power_t0 = 1, pmax
    else:
        unit_on_t0, power_t0 = 24, pmin

    init_rows.append({
        "GEN":              gen_uid,
        "UnitOnT0State":    unit_on_t0,
        "PowerGeneratedT0": power_t0,
    })

# Deduplicate GEN UIDs
uid_count = defaultdict(int)
for r in gen_rows:
    uid_count[r["GEN UID"]] += 1

uid_seen = defaultdict(int)
for r in gen_rows:
    uid = r["GEN UID"]
    if uid_count[uid] > 1:
        uid_seen[uid] += 1
        r["GEN UID"] = f"{uid}_{uid_seen[uid]}"

uid_seen2 = defaultdict(int)
for r in init_rows:
    uid = r["GEN"]
    if uid_count[uid] > 1:
        uid_seen2[uid] += 1
        r["GEN"] = f"{uid}_{uid_seen2[uid]}"

# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------
print("Writing outputs...")

_all_cols = [
    "GEN UID", "Bus ID", "Unit Group", "Unit Type", "Fuel",
    "PMin MW", "PMax MW", "Min Down Time Hr", "Min Up Time Hr",
    "Ramp Rate MW/Min",
    "Start Time Cold Hr", "Start Time Warm Hr", "Start Time Hot Hr",
    "Start Heat Cold MBTU", "Start Heat Warm MBTU", "Start Heat Hot MBTU",
    "Fuel Price $/MMBTU", "Fixed Cost($/hr)",
    "MW Break 1", "MWh Price 1",
    "_src_lat", "_src_lon", "_stage",
]
_full_df = pd.DataFrame(gen_rows, columns=_all_cols)

# gen.csv: Vatic columns only (no internal fields)
gen_df = _full_df.drop(columns=["_src_lat", "_src_lon", "_stage"])
gen_df.to_csv(SRC_DIR / "gen.csv", index=False)

# gen_matching.csv: GEN UID, Bus ID, Fuel, PMax, source lat/lon, stage
# Used by visualizer to draw snap lines from source location to SCED bus.
match_df = _full_df[["GEN UID", "Bus ID", "Fuel", "PMax MW",
                      "_src_lat", "_src_lon", "_stage"]].copy()
match_df.columns = ["GEN UID", "Bus ID", "Fuel", "PMax MW",
                     "Source Lat", "Source Lon", "Stage"]
match_df.to_csv(SRC_DIR / "gen_matching.csv", index=False)

init_df = pd.DataFrame(init_rows, columns=["GEN", "UnitOnT0State", "PowerGeneratedT0"])
init_df.to_csv(SRC_DIR / "init_state.csv", index=False)

print(f"  Wrote gen.csv          ({len(gen_df):,} rows)")
print(f"  Wrote gen_matching.csv ({len(match_df):,} rows)")
print(f"  Wrote init_state.csv   ({len(init_df):,} rows)")

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
n_total    = len(mora_ns)
n_matched  = len(gen_rows)
n_unmatched = sum(fuel_unmatched.values())

print()
print("Summary:")
print(f"  MORA non-storage units:  {n_total:,}")
print(f"  Matched:                 {n_matched:,}  ({n_matched/n_total*100:.1f}%)")
print(f"  Unmatched (excluded):    {n_unmatched:,}")
print()
print("  By assignment stage:")
for stage, cnt in sorted(stage_counts.items()):
    print(f"    {stage:35s}: {cnt:4d}")
print()
matched_fuel = defaultdict(int)
for r in gen_rows:
    matched_fuel[r["Unit Group"]] += 1
print("  Fuel breakdown (matched):")
for fg, cnt in sorted(matched_fuel.items(), key=lambda x: -x[1]):
    print(f"    {fg:15s}: {cnt:4d}")
if fuel_unmatched:
    print()
    print("  Unmatched by MORA fuel:")
    for fg, cnt in sorted(fuel_unmatched.items(), key=lambda x: -x[1]):
        if cnt > 0:
            print(f"    {fg:15s}: {cnt:4d}")
