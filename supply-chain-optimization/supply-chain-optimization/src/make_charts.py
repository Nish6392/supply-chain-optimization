"""
make_charts.py - matplotlib-only replacement for the Streamlit/Plotly dashboard.
Reads ../results and ../data, writes PNGs to ../charts (incl. one combined dashboard.png).
Run AFTER optimize_network.py.
"""
import os, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                     # remove this line if you want plt.show() windows
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))
DATA, RES, OUT = (os.path.join(BASE, "..", d) for d in ("data", "results", "charts"))
os.makedirs(OUT, exist_ok=True)

plants, terminals, regions = (pd.read_csv(f"{DATA}/{f}.csv") for f in ("plants", "terminals", "demand_regions"))
hist = pd.read_csv(f"{DATA}/historical_demand.csv")
fpt = pd.read_csv(f"{RES}/optimal_flows_plant_terminal.csv")
ftr = pd.read_csv(f"{RES}/optimal_flows_terminal_region.csv")
inv = pd.read_csv(f"{RES}/inventory_recommendations.csv")
fit = pd.read_csv(f"{RES}/forecast_fitted.csv")
fc = pd.read_csv(f"{RES}/demand_forecast.csv")
kpi = json.load(open(f"{RES}/kpi_summary.json"))

NAVY, TEAL, ORANGE, RED, GREY = "#1f3a5f", "#1a9e8f", "#f28e2b", "#d64545", "#9aa5b1"
RISK = {"BELOW_ROP": RED, "AT_RISK": ORANGE, "ABOVE_ROP": TEAL}
tname = terminals.set_index("terminal_id").terminal_name.str.replace(" Terminal", "")


def network_map(ax):
    """Lat/lon scatter with lines; line width = flow. (No map library needed.)"""
    p, t, r = (d.set_index(k) for d, k in ((plants, "plant_id"), (terminals, "terminal_id"), (regions, "region_id")))
    wmax = max(fpt.flow_units.max(), ftr.flow_units.max())
    for _, f in fpt.iterrows():
        ax.plot([p.lon[f.plant_id], t.lon[f.terminal_id]], [p.lat[f.plant_id], t.lat[f.terminal_id]],
                color=NAVY, lw=0.5 + 7 * f.flow_units / wmax, alpha=0.6, zorder=1)
    for _, f in ftr.iterrows():
        ax.plot([t.lon[f.terminal_id], r.lon[f.region_id]], [t.lat[f.terminal_id], r.lat[f.region_id]],
                color=TEAL, lw=0.5 + 7 * f.flow_units / wmax, alpha=0.6, zorder=1)
    ax.scatter(plants.lon, plants.lat, marker="s", s=140, c=NAVY, label="Refinery", zorder=3)
    pos = inv.set_index("terminal_id").loc[terminals.terminal_id, "inventory_position"]
    ax.scatter(terminals.lon, terminals.lat, s=110, c=[RISK[x] for x in pos], edgecolor="white", label="Terminal", zorder=3)
    ax.scatter(regions.lon, regions.lat, s=25, c=GREY, label="Market", zorder=2)
    for _, x in terminals.iterrows():
        ax.annotate(tname[x.terminal_id], (x.lon, x.lat), fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.set_title("Network flows (line width = bbl/day; terminal colour = stock risk)")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude"); ax.legend(loc="lower right", fontsize=7)


def cost_bars(ax):
    v = [kpi["baseline_transport_cost_per_day"], kpi["optimized_transport_cost_per_day"]]
    b = ax.bar(["Baseline\n(nearest node)", "Optimized"], v, color=[GREY, TEAL])
    ax.bar_label(b, labels=[f"${x:,.0f}" for x in v], padding=3)
    ax.set_ylim(0, max(v) * 1.15); ax.set_ylabel("$ / day")
    ax.set_title(f"Transport cost - saves {kpi['savings_pct']:.1f}% (${kpi['annualized_savings']:,.0f}/yr)")


def inventory_chart(ax):
    x = np.arange(len(inv)); names = [tname[t] for t in inv.terminal_id]
    ax.bar(x, inv.current_inventory_units, color=[RISK[p] for p in inv.inventory_position], label="On hand")
    ax.plot(x, inv.reorder_point_units, "kD--", label="Reorder point")
    ax.scatter(x, inv.safety_stock_units, c=ORANGE, zorder=3, label="Safety stock")
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("barrels"); ax.set_title("Inventory vs. reorder point"); ax.legend(fontsize=7)


def forecast_chart(ax, region="D1"):
    g = fit[fit.region_id == region]; f = fc[fc.region_id == region].iloc[0]
    ax.plot(g.month, g.actual, "o-", color=NAVY, label="Actual", ms=3)
    ax.plot(g.month, g.fitted, "--", color=ORANGE, label="Model fit")
    ax.scatter([f.forecast_month], [f.forecast_daily_demand], c=RED, s=60, zorder=3, label="Forecast")
    ax.set_xticks(list(g.month)[::3] + [f.forecast_month]); ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.set_title(f"Demand forecast - {regions.set_index('region_id').region_name[region]}")
    ax.set_ylabel("bbl/day"); ax.legend(fontsize=7)


def top_lanes(ax):
    a = fpt.assign(lane=fpt.plant_id + " > " + fpt.terminal_id.map(tname))
    b = ftr.assign(lane=ftr.terminal_id.map(tname) + " > " + ftr.region_id)
    top = pd.concat([a, b]).nlargest(10, "lane_cost").sort_values("lane_cost")
    ax.barh(top.lane, top.lane_cost, color=NAVY); ax.set_xlabel("$ / day"); ax.set_title("Top 10 lanes by daily cost")


charts = {"network_map": (network_map, (9, 6)), "cost_comparison": (cost_bars, (5, 4)),
          "inventory_vs_rop": (inventory_chart, (7, 4.5)), "demand_forecast": (forecast_chart, (7, 4)),
          "top_lanes": (top_lanes, (7, 4.5))}
for name, (fn, size) in charts.items():                    # individual PNGs
    fig, ax = plt.subplots(figsize=size); fn(ax); fig.tight_layout()
    fig.savefig(f"{OUT}/{name}.png", dpi=130); plt.close(fig)

# combined one-page dashboard
fig = plt.figure(figsize=(16, 10))
gs = fig.add_gridspec(2, 3, height_ratios=[1, 1])
network_map(fig.add_subplot(gs[0, :2])); cost_bars(fig.add_subplot(gs[0, 2]))
inventory_chart(fig.add_subplot(gs[1, 0])); forecast_chart(fig.add_subplot(gs[1, 1])); top_lanes(fig.add_subplot(gs[1, 2]))
fig.suptitle(f"Inventory & Supply Chain Optimization - planning month {kpi['planning_month']}  |  "
             f"demand {kpi['total_daily_demand_units']:,.0f} bbl/day  |  "
             f"{kpi['terminals_below_or_at_risk_of_rop']} terminals at risk", fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.96]); fig.savefig(f"{OUT}/dashboard.png", dpi=110); plt.close(fig)
print("Charts saved to", OUT)
