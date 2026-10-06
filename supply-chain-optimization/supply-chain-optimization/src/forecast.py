"""
forecast.py
-----------
Basic machine learning for demand: scikit-learn Linear Regression per market.

Features (all simple, hand-made):
    t          - month index (captures a linear trend)
    sin, cos   - month-of-year as a circle (captures the seasonal summer peak)

Why this is useful for the project:
  * The next-month forecast becomes the planning demand for the network model.
  * The forecast's RESIDUAL std (what the model can't explain) is the "real"
    demand uncertainty, so safety stock is no longer inflated by seasonality.

Real-data notes:
  * history = EIA national gasoline demand 2017-01..2022-03 x each state's real share.
  * COVID months (2020-03..2020-12) are an external shock, not normal behaviour, so they are
    EXCLUDED from model fitting (they are still plotted).
Model check: a time-ordered train/test split (test = last 12 months) vs a naive "predict the
training mean" baseline.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


COVID_MONTHS = [f"2020-{m:02d}" for m in range(3, 13)]


def make_features(months):
    """months: Series/list like '2025-12' -> DataFrame of features."""
    dt = pd.to_datetime(pd.Series(list(months)) + "-01")
    t = (dt.dt.year - 2017) * 12 + dt.dt.month          # 1, 2, 3, ... (from 2017-01)
    ang = 2 * np.pi * dt.dt.month / 12
    return pd.DataFrame({"t": t.values, "sin_m": np.sin(ang).values, "cos_m": np.cos(ang).values})


def next_month(last_month):
    return (pd.to_datetime(last_month + "-01") + pd.DateOffset(months=1)).strftime("%Y-%m")


def forecast_all(hist, test_months=12, exclude=COVID_MONTHS):
    """Fit one model per region. Returns (forecast_df, metrics_df, fitted_df)."""
    last = hist.month.max()
    nxt = next_month(last)
    fc_rows, met_rows, fit_rows = [], [], []

    for r, g in hist.groupby("region_id"):
        g = g.sort_values("month").reset_index(drop=True)
        X, y = make_features(g.month), g.avg_daily_demand_units.values
        keep = ~g.month.isin(exclude).values                 # rows allowed into model fitting

        # ---- 1. honest evaluation: train on early months, test on the latest ones
        ktr = keep[:-test_months]
        Xtr, Xte = X.iloc[:-test_months][ktr], X.iloc[-test_months:]
        ytr, yte = y[:-test_months][ktr], y[-test_months:]
        m_eval = LinearRegression().fit(Xtr, ytr)
        pred = m_eval.predict(Xte)
        naive = np.full_like(yte, ytr.mean(), dtype=float)
        met_rows.append({
            "region_id": r,
            "MAE_model": mean_absolute_error(yte, pred),
            "MAE_naive_mean": mean_absolute_error(yte, naive),
            "RMSE_model": np.sqrt(mean_squared_error(yte, pred)),
            "RMSE_naive_mean": np.sqrt(mean_squared_error(yte, naive)),
        })

        # ---- 2. final model on ALL data -> next-month forecast + residual spread
        model = LinearRegression().fit(X[keep], y[keep])
        fitted = model.predict(X)
        resid = (y - fitted)[keep]
        dof = max(keep.sum() - (X.shape[1] + 1), 1)      # n - number of fitted parameters
        resid_std = float(np.sqrt((resid ** 2).sum() / dof))
        fc = float(model.predict(make_features([nxt]))[0])
        fc_rows.append({"region_id": r, "forecast_month": nxt, "forecast_daily_demand": fc,
                        "resid_std": resid_std, "hist_std": float(y[keep].std(ddof=1))})
        fit_rows.append(pd.DataFrame({"region_id": r, "month": g.month, "actual": y, "fitted": fitted}))

    return pd.DataFrame(fc_rows), pd.DataFrame(met_rows), pd.concat(fit_rows, ignore_index=True)
