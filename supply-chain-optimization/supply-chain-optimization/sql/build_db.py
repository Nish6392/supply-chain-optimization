"""
build_db.py
Loads the CSVs in ../data/ into a SQLite database (scm_network.db) using
the schema in schema.sql, so analysis_queries.sql can be run directly.
"""
import sqlite3
import pandas as pd
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "scm_network.db")
DATA = os.path.join(BASE, "..", "data")

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
with open(os.path.join(BASE, "schema.sql")) as f:
    conn.executescript(f.read())

tables = {
    "plants": "plants.csv",
    "terminals": "terminals.csv",
    "demand_regions": "demand_regions.csv",
    "historical_demand": "historical_demand.csv",
    "lane_costs_plant_terminal": "lane_costs_plant_terminal.csv",
    "lane_costs_terminal_region": "lane_costs_terminal_region.csv",
}

for table, csv_file in tables.items():
    df = pd.read_csv(os.path.join(DATA, csv_file))
    df.to_sql(table, conn, if_exists="append", index=False)
    print(f"Loaded {len(df):>4} rows into {table}")

conn.commit()
conn.close()
print(f"\nDatabase built at {DB_PATH}")
