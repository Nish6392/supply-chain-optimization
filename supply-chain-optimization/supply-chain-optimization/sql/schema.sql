-- ============================================================
-- schema.sql
-- Inventory & Supply Chain Optimization — refinery/distribution network
-- refinery -> terminal -> demand-region distribution network
-- ============================================================

DROP TABLE IF EXISTS plants;
CREATE TABLE plants (
    plant_id                TEXT PRIMARY KEY,
    plant_name              TEXT NOT NULL,
    location                TEXT NOT NULL,
    lat                     REAL NOT NULL,
    lon                     REAL NOT NULL,
    capacity_units_per_day  REAL NOT NULL,
    prod_cost_per_unit      REAL NOT NULL
);

DROP TABLE IF EXISTS terminals;
CREATE TABLE terminals (
    terminal_id                     TEXT PRIMARY KEY,
    terminal_name                   TEXT NOT NULL,
    location                        TEXT NOT NULL,
    lat                             REAL NOT NULL,
    lon                             REAL NOT NULL,
    throughput_cap_units_per_day    REAL NOT NULL,
    holding_cost_per_unit_per_day   REAL NOT NULL,
    current_inventory_units         REAL NOT NULL
);

DROP TABLE IF EXISTS demand_regions;
CREATE TABLE demand_regions (
    region_id           TEXT PRIMARY KEY,
    region_name         TEXT NOT NULL,
    location            TEXT NOT NULL,
    lat                 REAL NOT NULL,
    lon                 REAL NOT NULL,
    lead_time_days      REAL NOT NULL,
    service_level_z     REAL NOT NULL,
    state               TEXT NOT NULL,          -- real EIA state
    us_share_pct        REAL NOT NULL           -- state's % of U.S. gasoline (EIA YTD-2022)
);

DROP TABLE IF EXISTS historical_demand;
CREATE TABLE historical_demand (
    region_id                TEXT NOT NULL REFERENCES demand_regions(region_id),
    month                     TEXT NOT NULL,           -- 'YYYY-MM'
    avg_daily_demand_units    REAL NOT NULL,
    PRIMARY KEY (region_id, month)
);

DROP TABLE IF EXISTS lane_costs_plant_terminal;
CREATE TABLE lane_costs_plant_terminal (
    plant_id         TEXT NOT NULL REFERENCES plants(plant_id),
    terminal_id      TEXT NOT NULL REFERENCES terminals(terminal_id),
    distance_miles   REAL NOT NULL,
    cost_per_unit    REAL NOT NULL,
    PRIMARY KEY (plant_id, terminal_id)
);

DROP TABLE IF EXISTS lane_costs_terminal_region;
CREATE TABLE lane_costs_terminal_region (
    terminal_id      TEXT NOT NULL REFERENCES terminals(terminal_id),
    region_id        TEXT NOT NULL REFERENCES demand_regions(region_id),
    distance_miles   REAL NOT NULL,
    cost_per_unit    REAL NOT NULL,
    PRIMARY KEY (terminal_id, region_id)
);

-- Populated by the optimizer after each run
DROP TABLE IF EXISTS optimal_flows_plant_terminal;
CREATE TABLE optimal_flows_plant_terminal (
    plant_id         TEXT NOT NULL,
    terminal_id      TEXT NOT NULL,
    flow_units       REAL NOT NULL,
    cost_per_unit    REAL NOT NULL,
    lane_cost        REAL NOT NULL
);

DROP TABLE IF EXISTS optimal_flows_terminal_region;
CREATE TABLE optimal_flows_terminal_region (
    terminal_id      TEXT NOT NULL,
    region_id        TEXT NOT NULL,
    flow_units       REAL NOT NULL,
    cost_per_unit    REAL NOT NULL,
    lane_cost        REAL NOT NULL
);

DROP TABLE IF EXISTS inventory_recommendations;
CREATE TABLE inventory_recommendations (
    terminal_id                TEXT NOT NULL,
    avg_daily_throughput       REAL NOT NULL,
    demand_std_daily           REAL NOT NULL,
    lead_time_days             REAL NOT NULL,
    safety_stock_units         REAL NOT NULL,
    reorder_point_units        REAL NOT NULL,
    current_inventory_units    REAL NOT NULL,
    inventory_position         TEXT NOT NULL      -- 'ABOVE_ROP' / 'AT_RISK' / 'BELOW_ROP'
);
