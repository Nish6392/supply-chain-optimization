-- ============================================================
-- analysis_queries.sql
-- Analytical queries for the Inventory & Supply Chain
-- Optimization project. Run against scm_network.db (SQLite).
-- ============================================================

-- 1. Network capacity check: total plant capacity vs total terminal throughput
SELECT
    (SELECT SUM(capacity_units_per_day) FROM plants)               AS total_plant_capacity,
    (SELECT SUM(throughput_cap_units_per_day) FROM terminals)      AS total_terminal_throughput,
    (SELECT SUM(avg_daily_demand_units)
       FROM historical_demand
      WHERE month = (SELECT MAX(month) FROM historical_demand))    AS latest_month_total_demand;

-- 2. Demand trend by region: month-over-month average daily demand, last 6 months
SELECT region_id, month, avg_daily_demand_units
FROM historical_demand
WHERE month >= (SELECT strftime('%Y-%m', date((SELECT MAX(month) FROM historical_demand) || '-01', '-5 months')))
ORDER BY region_id, month;

-- 3. Demand statistics per region (mean, stdev, coefficient of variation) — feeds safety-stock calc
SELECT
    region_id,
    ROUND(AVG(avg_daily_demand_units), 1)                                   AS mean_daily_demand,
    ROUND(
        SQRT(AVG(avg_daily_demand_units * avg_daily_demand_units)
             - AVG(avg_daily_demand_units) * AVG(avg_daily_demand_units)), 1
    )                                                                        AS stdev_daily_demand
FROM historical_demand
GROUP BY region_id
ORDER BY mean_daily_demand DESC;

-- 4. Cheapest terminal-to-region lane per demand region (candidate primary source)
SELECT r.region_id, r.region_name, lt.terminal_id, t.terminal_name, lt.cost_per_unit
FROM lane_costs_terminal_region lt
JOIN demand_regions r ON r.region_id = lt.region_id
JOIN terminals t       ON t.terminal_id = lt.terminal_id
WHERE lt.cost_per_unit = (
    SELECT MIN(lt2.cost_per_unit)
    FROM lane_costs_terminal_region lt2
    WHERE lt2.region_id = lt.region_id
)
ORDER BY r.region_id;

-- 5. Post-optimization: total network cost breakdown (run AFTER optimize_network.py populates
--    optimal_flows_* tables)
SELECT
    (SELECT ROUND(SUM(lane_cost), 2) FROM optimal_flows_plant_terminal)   AS total_inbound_transport_cost,
    (SELECT ROUND(SUM(lane_cost), 2) FROM optimal_flows_terminal_region)  AS total_outbound_transport_cost,
    (SELECT ROUND(SUM(lane_cost), 2) FROM optimal_flows_plant_terminal) +
    (SELECT ROUND(SUM(lane_cost), 2) FROM optimal_flows_terminal_region) AS total_transport_cost;

-- 6. Terminal utilization after optimization (inbound flow vs throughput capacity)
SELECT
    t.terminal_id,
    t.terminal_name,
    t.throughput_cap_units_per_day,
    ROUND(COALESCE(SUM(f.flow_units), 0), 1)                              AS optimized_inbound_flow,
    ROUND(100.0 * COALESCE(SUM(f.flow_units), 0) / t.throughput_cap_units_per_day, 1) AS utilization_pct
FROM terminals t
LEFT JOIN optimal_flows_plant_terminal f ON f.terminal_id = t.terminal_id
GROUP BY t.terminal_id
ORDER BY utilization_pct DESC;

-- 7. Terminals below reorder point (replenishment risk list)
SELECT terminal_id, current_inventory_units, reorder_point_units, safety_stock_units, inventory_position
FROM inventory_recommendations
WHERE inventory_position IN ('BELOW_ROP', 'AT_RISK')
ORDER BY (current_inventory_units - reorder_point_units) ASC;

-- 8. Top 10 most expensive active lanes in the optimized solution (cost-reduction targets)
SELECT plant_id AS origin, terminal_id AS destination, flow_units, cost_per_unit, lane_cost
FROM optimal_flows_plant_terminal
WHERE flow_units > 0
UNION ALL
SELECT terminal_id AS origin, region_id AS destination, flow_units, cost_per_unit, lane_cost
FROM optimal_flows_terminal_region
WHERE flow_units > 0
ORDER BY lane_cost DESC
LIMIT 10;

-- 9. Real-data check: each market's share of U.S. gasoline (EIA psrall.csv) and its latest demand
SELECT r.state, r.us_share_pct, h.avg_daily_demand_units AS latest_bbl_per_day
FROM demand_regions r
JOIN historical_demand h ON h.region_id = r.region_id
WHERE h.month = (SELECT MAX(month) FROM historical_demand)
ORDER BY r.us_share_pct DESC;
