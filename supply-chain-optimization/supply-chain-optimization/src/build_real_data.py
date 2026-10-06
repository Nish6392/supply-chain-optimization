"""
build_real_data.py
------------------
Builds every file in ../data/ from EIA data:

  data/raw/eia_total_gasoline_national_monthly.csv
        <- sheet "Data 1" of PET_CONS_PRIM_DCU_NUS_M.xls (EIA, U.S. total motor gasoline
           prime-supplier sales, thousand gallons/day, monthly 1983-01 .. 2022-03)
  data/raw/psrall.csv
        <- EIA Prime Supplier Report, state-level motor gasoline, Feb/Mar/YTD 2022
           (thousand gallons per MONTH)

How the real data is used
  * Demand markets = 15 U.S. states. Each state's share of U.S. gasoline = its YTD-2022 volume
    / U.S. YTD-2022 volume (real, from psrall.csv).
  * historical_demand.csv = real national monthly series (2017-01..2022-03, converted to
    barrels/day) x the state's real share.  (EIA gives only 2-3 months of state data, so the
    state history borrows the national shape - stated openly in the README.)
  * Units: 1 thousand gallons = 1000/42 = 23.81 barrels, so all 'units' are now barrels/day.

Still ASSUMPTIONS (EIA files contain no such data): city coordinates for each node, plant/terminal
capacities (scaled to the real demand level), production and holding
costs, lead times, lane rates ($/bbl-mile).
"""
import os
import numpy as np
import pandas as pd
from math import radians, sin, cos, asin, sqrt

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "..", "data")
RAW = os.path.join(DATA, "raw")
BBL_PER_KGAL = 1000 / 42
HIST_START = "2017-01"

# ------------------------------------------------------------ real data
nat = pd.read_csv(f"{RAW}/eia_total_gasoline_national_monthly.csv")
nat["bbl_per_day"] = nat.us_total_gasoline_kgal_per_day * BBL_PER_KGAL
nat = nat[nat.month >= HIST_START].reset_index(drop=True)

ps = pd.read_csv(f"{RAW}/psrall.csv")
gas = ps[ps.Product == "Motor Gasoline"].set_index("Area")
us_ytd = float(gas.loc["United States", "YTD_2022"])

# ------------------------------------------------------------ network nodes
# (state, node city, lat, lon, lead time days)  -> state demand is real, node city is representative
markets = [
    ("Texas", "Austin, TX", 30.2672, -97.7431, 1.5), ("Oklahoma", "Oklahoma City, OK", 35.4676, -97.5164, 2.0),
    ("Louisiana", "New Orleans, LA", 29.9511, -90.0715, 1.5), ("Mississippi", "Jackson, MS", 32.2988, -90.1848, 2.0),
    ("Alabama", "Birmingham, AL", 33.5186, -86.8104, 2.0), ("North Carolina", "Charlotte, NC", 35.2271, -80.8431, 2.5),
    ("Kentucky", "Louisville, KY", 38.2527, -85.7585, 2.0), ("Indiana", "Indianapolis, IN", 39.7684, -86.1581, 2.0),
    ("Missouri", "St. Louis, MO", 38.6270, -90.1994, 2.0), ("Nebraska", "Omaha, NE", 41.2565, -95.9345, 2.5),
    ("Minnesota", "Minneapolis, MN", 44.9778, -93.2650, 2.5), ("Arizona", "Phoenix, AZ", 33.4484, -112.0740, 3.0),
    ("New Mexico", "Albuquerque, NM", 35.0844, -106.6504, 2.5), ("Arkansas", "Little Rock, AR", 34.7465, -92.2896, 2.0),
    ("Kansas", "Wichita, KS", 37.6872, -97.3301, 2.0),
]
rows = []
for i, (st, city, la, lo, lt) in enumerate(markets, 1):
    share = float(gas.loc[st, "YTD_2022"]) / us_ytd
    rows.append([f"D{i}", f"{st} Market", city, la, lo, lt, 1.65, st, round(100 * share, 3)])
regions = pd.DataFrame(rows, columns=["region_id", "region_name", "location", "lat", "lon", "lead_time_days",
                                      "service_level_z", "state", "us_share_pct"])

# demand level -> used to scale capacities/inventory (same headroom as the original project)
ORIG_DEMAND = 4051.5
latest_total = nat.bbl_per_day.iloc[-1] * regions.us_share_pct.sum() / 100
K = latest_total / ORIG_DEMAND

plants = pd.DataFrame([
    ("P1", "Baytown Refinery", "Baytown, TX", 29.7355, -94.9774, 5600, 38.20),
    ("P2", "Beaumont Refinery", "Beaumont, TX", 30.0802, -94.1266, 4200, 38.90),
    ("P3", "Baton Rouge Refinery", "Baton Rouge, LA", 30.4515, -91.1871, 3800, 39.40),
    ("P4", "Joliet Refinery", "Joliet, IL", 41.5250, -88.0817, 2600, 41.10),
], columns=["plant_id", "plant_name", "location", "lat", "lon", "capacity_units_per_day", "prod_cost_per_unit"])
plants["capacity_units_per_day"] = (plants.capacity_units_per_day * K).round(0)

terminals = pd.DataFrame([
    ("T1", "Houston Terminal", "Houston, TX", 29.7604, -95.3698, 2600, 0.09, 9800),
    ("T2", "Dallas Terminal", "Dallas, TX", 32.7767, -96.7970, 2100, 0.10, 6200),
    ("T3", "Memphis Terminal", "Memphis, TN", 35.1495, -90.0490, 1700, 0.10, 350),
    ("T4", "Atlanta Terminal", "Atlanta, GA", 33.7490, -84.3880, 2300, 0.11, 7400),
    ("T5", "Chicago Terminal", "Chicago, IL", 41.8781, -87.6298, 2400, 0.12, 8600),
    ("T6", "Denver Terminal", "Denver, CO", 39.7392, -104.9903, 1500, 0.11, 890),
    ("T7", "Kansas City Terminal", "Kansas City, MO", 39.0997, -94.5786, 1600, 0.10, 4900),
    ("T8", "Nashville Terminal", "Nashville, TN", 36.1627, -86.7816, 1500, 0.10, 4100),
], columns=["terminal_id", "terminal_name", "location", "lat", "lon", "throughput_cap_units_per_day",
            "holding_cost_per_unit_per_day", "current_inventory_units"])
terminals["throughput_cap_units_per_day"] = (terminals.throughput_cap_units_per_day * K).round(0)
terminals["current_inventory_units"] = (terminals.current_inventory_units * K).round(0)


def miles(a, b, c, d):
    a, b, c, d = map(radians, (a, b, c, d))
    h = sin((c - a) / 2) ** 2 + cos(a) * cos(c) * sin((d - b) / 2) ** 2
    return 2 * 3958.8 * asin(sqrt(h))


PIPE, TRUCK, FEE = 0.0028, 0.0065, 0.35       # $/bbl-mile pipeline, $/bbl-mile truck, $/bbl handling
lane_pt = pd.DataFrame([[p.plant_id, t.terminal_id, round(miles(p.lat, p.lon, t.lat, t.lon), 1),
                         round(FEE + PIPE * miles(p.lat, p.lon, t.lat, t.lon), 4)]
                        for p in plants.itertuples() for t in terminals.itertuples()],
                       columns=["plant_id", "terminal_id", "distance_miles", "cost_per_unit"])
lane_tr = pd.DataFrame([[t.terminal_id, r.region_id, round(miles(t.lat, t.lon, r.lat, r.lon), 1),
                         round(FEE + TRUCK * miles(t.lat, t.lon, r.lat, r.lon), 4)]
                        for t in terminals.itertuples() for r in regions.itertuples()],
                       columns=["terminal_id", "region_id", "distance_miles", "cost_per_unit"])

# state history = real national monthly barrels/day x real state share
hist = pd.DataFrame([[r.region_id, m, round(v * r.us_share_pct / 100, 1)]
                     for r in regions.itertuples() for m, v in zip(nat.month, nat.bbl_per_day)],
                    columns=["region_id", "month", "avg_daily_demand_units"])

for name, df in [("plants", plants), ("terminals", terminals), ("demand_regions", regions),
                 ("historical_demand", hist), ("lane_costs_plant_terminal", lane_pt),
                 ("lane_costs_terminal_region", lane_tr)]:
    df.to_csv(f"{DATA}/{name}.csv", index=False)

print(f"Real data loaded: national months {nat.month.iloc[0]}..{nat.month.iloc[-1]}, "
      f"{len(regions)} state markets = {regions.us_share_pct.sum():.1f}% of U.S. gasoline")
print(f"Mar-2022 demand of the 15 markets: {latest_total:,.0f} bbl/day  (capacity scale x{K:.1f})")
print(f"Plant capacity {plants.capacity_units_per_day.sum():,.0f}  |  terminal throughput "
      f"{terminals.throughput_cap_units_per_day.sum():,.0f} bbl/day")
