"""Run sql/analysis.sql on the generated CSVs (in-memory SQLite) and check every query
against an independent pandas calculation.

Usage: python data/generate_data.py --products 300 --po-lines 60000
       python tools/test_sql.py
The SQL is ANSI-style so the same text runs on Snowflake; this script proves the logic.
"""
import pathlib, re, sqlite3, sys
import numpy as np, pandas as pd

root = pathlib.Path(__file__).resolve().parent.parent
data = root / "data" / "out"
if not (data / "fact_po_lines.csv").exists():
    sys.exit("Generate data first: python data/generate_data.py --products 300 --po-lines 60000")

tables = {n: pd.read_csv(data / f"{n}.csv") for n in
          ["dim_date", "dim_product", "dim_supplier", "dim_location", "fact_po_lines", "fact_inventory_daily"]}
con = sqlite3.connect(":memory:")
for n, df in tables.items():
    df.to_sql(n, con, index=False)

text = (root / "sql" / "analysis.sql").read_text()
queries = {m.group(1): m.group(2) for m in
           re.finditer(r"-- name: (\w+)\n(.*?)(?=\n-- name: |\Z)", text, re.S)}

def run(name):
    return pd.read_sql_query(queries[name], con)

dd, po, sup = tables["dim_date"], tables["fact_po_lines"], tables["dim_supplier"]
inv, prod = tables["fact_inventory_daily"], tables["dim_product"]
po = po.assign(otif=((po.is_on_time == 1) & (po.is_in_full == 1)).astype(int))
dd = dd.assign(month_idx=dd.year * 12 + dd.month_num)
fails = []

def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" - {detail}" if detail and not ok else ""))
    if not ok: fails.append(name)

# ---- Q1: monthly OTIF, rolling 3m, YoY ------------------------------------
q1 = run("q1_monthly_otif_rolling_yoy")
m = (po.merge(dd[["date_key", "year_month", "month_idx"]], left_on="order_date_key", right_on="date_key")
       .groupby(["year_month", "month_idx"]).agg(lines=("otif", "size"), otif=("otif", "sum")).reset_index()
       .sort_values("month_idx").reset_index(drop=True))
m["otif_pct"] = (100 * m.otif / m.lines).round(2)
r3 = m[["otif", "lines"]].rolling(3).sum()
m["roll3"] = (100 * r3.otif / r3.lines).round(2)
yoy = 100 * m.otif / m.lines - 100 * m.otif.shift(12) / m.lines.shift(12)
m["yoy"] = yoy.round(2)
check("q1 row count", len(q1) == len(m), f"{len(q1)} vs {len(m)}")
check("q1 otif_pct", np.allclose(q1.otif_pct, m.otif_pct, atol=0.011))
check("q1 rolling 3m", np.allclose(q1.otif_pct_rolling_3m, m.roll3, equal_nan=True, atol=0.011))
check("q1 yoy pts", np.allclose(q1.otif_yoy_pts, m.yoy, equal_nan=True, atol=0.011))
check("q1 first 2 months have no rolling value", q1.otif_pct_rolling_3m.iloc[:2].isna().all())
check("q1 first 12 months have no yoy", q1.otif_yoy_pts.iloc[:12].isna().all())

# ---- Q2: supplier scorecard ----------------------------------------------
q2 = run("q2_supplier_scorecard")
g = (po.assign(spend=po.qty_received * po.unit_cost).groupby("supplier_key")
       .agg(lines=("otif", "size"), otif=("otif", "sum"), spend=("spend", "sum")).reset_index())
g = g[g.lines >= 100].merge(sup[["supplier_key", "supplier_name", "country"]], on="supplier_key")
g["rate"] = g.otif / g.lines
g["rank_in_country"] = g.groupby("country").rate.rank(method="min")
g = g.sort_values(["spend", "supplier_key"], ascending=[False, True])
g["cum_before"] = g.spend.cumsum() - g.spend
g["cls"] = np.where(g.cum_before / g.spend.sum() < 0.80, "A", np.where(g.cum_before / g.spend.sum() < 0.95, "B", "C"))
g["vs_avg"] = (100 * (g.rate - g.groupby("country").rate.transform("mean"))).round(2)
g = g.set_index("supplier_name")
q2i = q2.set_index("supplier_name")
check("q2 supplier count", len(q2i) == len(g), f"{len(q2i)} vs {len(g)}")
check("q2 otif_pct", np.allclose(q2i.otif_pct, (100 * g.rate).round(2).reindex(q2i.index), atol=0.011))
check("q2 rank within country", (q2i.worst_rank_in_country == g.rank_in_country.reindex(q2i.index)).all())
check("q2 pts vs country avg", np.allclose(q2i.pts_vs_country_avg, g.vs_avg.reindex(q2i.index), atol=0.011))
check("q2 spend class", (q2i.spend_class == g.cls.reindex(q2i.index)).all())
check("q2 quartiles 1-4", set(q2i.otif_quartile) <= {1, 2, 3, 4} and q2i.otif_quartile.nunique() == 4)
check("q2 cum_spend_pct max is 100", abs(q2.cum_spend_pct.max() - 100) < 0.01)

# ---- Q3: chronic streaks ---------------------------------------------------
q3 = run("q3_chronic_underperformance_streaks")
sm = (po.merge(dd[["date_key", "year_month", "month_idx"]], left_on="order_date_key", right_on="date_key")
        .groupby(["supplier_key", "year_month", "month_idx"]).agg(lines=("otif", "size"), otif=("otif", "sum")).reset_index())
sm = sm[sm.lines >= 10]
sm["rate"] = sm.otif / sm.lines
bad = sm[sm.rate < 0.50].sort_values(["supplier_key", "month_idx"])
rows = []
for k, grp in bad.groupby("supplier_key"):
    idx = grp.month_idx.tolist(); start = 0
    for i in range(1, len(idx) + 1):
        if i == len(idx) or idx[i] != idx[i - 1] + 1:
            run_len = i - start
            if run_len >= 3:
                seg = grp.iloc[start:i]
                rows.append((k, run_len, seg.year_month.min(), seg.year_month.max(), round(100 * seg.rate.mean(), 2)))
            start = i
exp = pd.DataFrame(rows, columns=["supplier_key", "streak_months", "start", "end", "avg"]).merge(
    sup[["supplier_key", "supplier_name"]], on="supplier_key")
check("q3 streak count", len(q3) == len(exp), f"{len(q3)} vs {len(exp)}")
got = sorted(zip(q3.supplier_name, q3.streak_months, q3.streak_start, q3.streak_end))
want = sorted(zip(exp.supplier_name, exp.streak_months, exp.start, exp.end))
check("q3 streak membership, length, dates", got == want)
check("q3 all streaks >= 3 months", (q3.streak_months >= 3).all())

# ---- Q4: month-end inventory ------------------------------------------------
q4 = run("q4_month_end_inventory_mom_yoy")
snap = inv.merge(dd[["date_key", "year_month", "month_idx"]], on="date_key").merge(prod[["product_key", "abc_class"]], on="product_key")
last = snap[snap.date_key == snap.groupby("year_month").date_key.transform("max")]
e = last.groupby(["year_month", "month_idx"]).apply(
    lambda x: pd.Series({"val": x.on_hand_value.sum(), "a": x.loc[x.abc_class == "A", "on_hand_value"].sum()}),
    include_groups=False).reset_index().sort_values("month_idx").reset_index(drop=True)
check("q4 row count", len(q4) == len(e))
check("q4 inventory value", np.allclose(q4.inventory_value, e.val.round(0), atol=1))
check("q4 A-class share", np.allclose(q4.a_class_share_pct, (100 * e.a / e.val).round(2), atol=0.011))
check("q4 MoM", np.allclose(q4.mom_pct, (100 * (e.val / e.val.shift(1) - 1)).round(2), equal_nan=True, atol=0.011))
check("q4 YoY", np.allclose(q4.yoy_pct, (100 * (e.val / e.val.shift(12) - 1)).round(2), equal_nan=True, atol=0.011))
# a month-end must be a single snapshot, never a sum across weeks
check("q4 not summed across weeks", q4.inventory_value.max() < 3 * e.val.max())

print("\nAll SQL checks passed" if not fails else f"\n{len(fails)} check(s) failed: {fails}")
sys.exit(1 if fails else 0)
