"""
optimize_network.py
-------------------
End-to-end pipeline using only: pandas, numpy, scikit-learn, matplotlib (+ stdlib sqlite3).

  1. Forecast next-month demand for every market       (scikit-learn regression)
  2. Solve the min-cost distribution plan               (min_cost_flow.py, pure Python)
  3. Compare against a naive "nearest node" baseline
  4. Safety stock / reorder point per terminal          ((Q,R) model, using forecast error)
  5. Save CSV/JSON results and write them into SQLite

Run from inside src/:   python optimize_network.py
"""
import os, json, sqlite3
import numpy as np
import pandas as pd

from forecast import forecast_all
from min_cost_flow import solve_network

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "..", "data")
RESULTS = os.path.join(BASE, "..", "results")
DB_PATH = os.path.join(BASE, "..", "sql", "scm_network.db")
os.makedirs(RESULTS, exist_ok=True)

# ------------------------------------------------------------ 1. load
plants = pd.read_csv(f"{DATA}/plants.csv")
terminals = pd.read_csv(f"{DATA}/terminals.csv")
regions = pd.read_csv(f"{DATA}/demand_regions.csv")
hist = pd.read_csv(f"{DATA}/historical_demand.csv")
lane_pt = pd.read_csv(f"{DATA}/lane_costs_plant_terminal.csv")
lane_tr = pd.read_csv(f"{DATA}/lane_costs_terminal_region.csv")
P, T, R = plants.plant_id.tolist(), terminals.terminal_id.tolist(), regions.region_id.tolist()

# ------------------------------------------------------------ 2. forecast demand (ML)
fc, metrics, fitted = forecast_all(hist, test_months=12)
fc.to_csv(f"{RESULTS}/demand_forecast.csv", index=False)
metrics.to_csv(f"{RESULTS}/forecast_metrics.csv", index=False)
fitted.to_csv(f"{RESULTS}/forecast_fitted.csv", index=False)
demand = dict(zip(fc.region_id, fc.forecast_daily_demand))
planning_month = fc.forecast_month.iloc[0]
print(f"Forecast MAE  model: {metrics.MAE_model.mean():.1f}   naive-mean: {metrics.MAE_naive_mean.mean():.1f}  (bbl/day, avg over markets)")
print(f"Planning month: {planning_month}   total forecast demand: {sum(demand.values()):,.1f} bbl/day")

# ------------------------------------------------------------ 3. optimise
ok, opt_cost, df_pt, df_tr = solve_network(plants, terminals, regions, lane_pt, lane_tr, demand)
if not ok:
    raise RuntimeError("Demand cannot be met with the current capacities.")
df_pt = df_pt.round({"flow_units": 2, "lane_cost": 2})
df_tr = df_tr.round({"flow_units": 2, "lane_cost": 2})
df_pt.to_csv(f"{RESULTS}/optimal_flows_plant_terminal.csv", index=False)
df_tr.to_csv(f"{RESULTS}/optimal_flows_terminal_region.csv", index=False)
print(f"Optimized transport cost: ${opt_cost:,.2f}/day")

# ------------------------------------------------------------ 4. naive baseline
def naive_baseline_cost(demand):
    cap_t = dict(zip(terminals.terminal_id, terminals.throughput_cap_units_per_day))
    cap_p = dict(zip(plants.plant_id, plants.capacity_units_per_day))
    c_tr = lane_tr.set_index(["terminal_id", "region_id"]).cost_per_unit.to_dict()
    c_pt = lane_pt.set_index(["plant_id", "terminal_id"]).cost_per_unit.to_dict()
    total, inbound = 0.0, {t: 0.0 for t in T}
    for r in R:                                           # each market -> cheapest terminal with room
        need = demand[r]
        for t in sorted(T, key=lambda t: c_tr[(t, r)]):
            q = min(need, cap_t[t])
            if q <= 1e-9: continue
            total += q * c_tr[(t, r)]; inbound[t] += q; cap_t[t] -= q; need -= q
            if need <= 1e-9: break
    for t in T:                                           # each terminal <- cheapest refinery with room
        need = inbound[t]
        for p in sorted(P, key=lambda p: c_pt[(p, t)]):
            q = min(need, cap_p[p])
            if q <= 1e-9: continue
            total += q * c_pt[(p, t)]; cap_p[p] -= q; need -= q
            if need <= 1e-9: break
    return total

baseline_cost = naive_baseline_cost(demand)
savings = baseline_cost - opt_cost
print(f"Baseline cost: ${baseline_cost:,.2f}/day   savings: ${savings:,.2f}/day ({100*savings/baseline_cost:.1f}%)")

# ------------------------------------------------------------ 5. inventory policy
fc_i = fc.set_index("region_id")
reg_i = regions.set_index("region_id")
rows = []
for t in T:
    f = df_tr[df_tr.terminal_id == t]
    thr = f.flow_units.sum()
    if thr > 0:
        w = (f.flow_units / thr).values
        sd = float(np.sqrt(((fc_i.loc[f.region_id, "resid_std"].values * w) ** 2).sum()))
        lt = float((reg_i.loc[f.region_id, "lead_time_days"].values * w).sum())
        z = float((reg_i.loc[f.region_id, "service_level_z"].values * w).sum())
    else:
        sd, lt, z = 0.0, float(regions.lead_time_days.mean()), 1.65
    ss = z * sd * np.sqrt(lt)
    rop = thr * lt + ss
    inv = float(terminals.loc[terminals.terminal_id == t, "current_inventory_units"].iloc[0])
    pos = "BELOW_ROP" if inv < rop else ("AT_RISK" if inv < 1.15 * rop else "ABOVE_ROP")
    rows.append([t, round(thr, 1), round(sd, 1), round(lt, 2), round(ss, 1), round(rop, 1), inv, pos])
df_inv = pd.DataFrame(rows, columns=["terminal_id", "avg_daily_throughput", "demand_std_daily", "lead_time_days",
                                     "safety_stock_units", "reorder_point_units", "current_inventory_units",
                                     "inventory_position"])
df_inv.to_csv(f"{RESULTS}/inventory_recommendations.csv", index=False)

# ------------------------------------------------------------ 6. KPIs
hold = terminals.set_index("terminal_id").holding_cost_per_unit_per_day
kpi = {
    "planning_month": planning_month,
    "total_daily_demand_units": round(sum(demand.values()), 1),
    "optimized_transport_cost_per_day": round(opt_cost, 2),
    "baseline_transport_cost_per_day": round(baseline_cost, 2),
    "daily_savings": round(savings, 2),
    "savings_pct": round(100 * savings / baseline_cost, 2),
    "annualized_savings": round(savings * 365, 0),
    "total_daily_holding_cost_current_inventory": round(float((df_inv.set_index("terminal_id").current_inventory_units * hold).sum()), 2),
    "terminals_below_or_at_risk_of_rop": int((df_inv.inventory_position != "ABOVE_ROP").sum()),
    "avg_terminal_utilization_pct": round(100 * df_tr.flow_units.sum() / terminals.throughput_cap_units_per_day.sum(), 1),
    "forecast_MAE_model": round(float(metrics.MAE_model.mean()), 2),
    "forecast_MAE_naive_mean": round(float(metrics.MAE_naive_mean.mean()), 2),
}
with open(f"{RESULTS}/kpi_summary.json", "w") as fh:
    json.dump(kpi, fh, indent=2)
for k, v in kpi.items():
    print(f"  {k}: {v}")

# ------------------------------------------------------------ 7. SQLite write-back (stdlib only)
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    for tbl, df in [("optimal_flows_plant_terminal", df_pt), ("optimal_flows_terminal_region", df_tr),
                    ("inventory_recommendations", df_inv)]:
        conn.execute(f"DELETE FROM {tbl}")
        df.to_sql(tbl, conn, if_exists="append", index=False)
    conn.commit(); conn.close()
    print("Results also written into", DB_PATH)
