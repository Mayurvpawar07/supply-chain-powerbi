"""Generate a SYNTHETIC supply chain star schema (no real company data).

Usage: python data/generate_data.py --products 1500 --po-lines 400000
Output: data/out/*.csv  (gitignored)
"""
import argparse, pathlib
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--products", type=int, default=1500)
ap.add_argument("--po-lines", type=int, default=400_000)
ap.add_argument("--seed", type=int, default=42)
a = ap.parse_args()
rng = np.random.default_rng(a.seed)
out = pathlib.Path(__file__).parent / "out"; out.mkdir(exist_ok=True)

# dim_date
d = pd.DataFrame({"date": pd.date_range("2023-01-01", "2026-12-31")})
d["date_key"] = d.date.dt.strftime("%Y%m%d").astype(int)
d["year"] = d.date.dt.year; d["quarter"] = "Q" + d.date.dt.quarter.astype(str)
d["month_num"] = d.date.dt.month; d["month"] = d.date.dt.strftime("%b")
d["year_month"] = d.date.dt.strftime("%Y-%m")
d["week_of_year"] = d.date.dt.isocalendar().week.astype(int)
d.to_csv(out / "dim_date.csv", index=False)
keys = d.date_key.values

# dim_product
n_prod = a.products
cats = ["Coils", "Fans & Motors", "Sheet Metal", "Controls", "Filters", "Fasteners", "Insulation"]
p = pd.DataFrame({"product_key": range(1, n_prod + 1)})
p["sku"] = "SKU-" + p.product_key.astype(str).str.zfill(5)
p["category"] = rng.choice(cats, n_prod)
p["unit_cost"] = np.round(rng.lognormal(3, 1, n_prod), 2)
rank = p.unit_cost.mul(rng.uniform(0.5, 2, n_prod)).rank(pct=True)
p["abc_class"] = np.where(rank > 0.8, "A", np.where(rank > 0.5, "B", "C"))
p.to_csv(out / "dim_product.csv", index=False)

# dim_supplier
n_sup = 80
s = pd.DataFrame({"supplier_key": range(1, n_sup + 1)})
s["supplier_name"] = "Supplier " + s.supplier_key.astype(str).str.zfill(3)
s["country"] = rng.choice(["Canada", "USA", "China", "Germany", "Mexico"], n_sup, p=[.35, .3, .2, .1, .05])
s["std_lead_time_days"] = rng.integers(5, 75, n_sup)
s.to_csv(out / "dim_supplier.csv", index=False)

# dim_location
loc = pd.DataFrame({"location_key": range(1, 7),
    "location_name": ["Plant East", "Plant West", "DC Central", "DC North", "DC South", "Cross-dock"],
    "location_type": ["Plant", "Plant", "DC", "DC", "DC", "Cross-dock"]})
loc.to_csv(out / "dim_location.csv", index=False)

# fact_po_lines
# Supplier reliability varies: a few chronic problem suppliers, China slightly worse,
# and delivery performance improves modestly over time.
sup_late = np.clip(rng.beta(2, 6, n_sup) * 0.8, 0.03, 0.6)
sup_short = np.clip(rng.beta(1.5, 10, n_sup), 0.02, 0.35)
bad = rng.choice(n_sup, 6, replace=False)
sup_late[bad] = rng.uniform(0.5, 0.7, 6); sup_short[bad] = rng.uniform(0.25, 0.4, 6)
sup_late = np.clip(sup_late + np.where(s.country.values == "China", 0.05, 0), 0, 0.8)
n = a.po_lines
f = pd.DataFrame({"po_line_id": np.arange(1, n + 1)})
f["po_id"] = (f.po_line_id // 4) + 100000
f["product_key"] = rng.integers(1, n_prod + 1, n)
f["supplier_key"] = rng.integers(1, n_sup + 1, n)
f["location_key"] = rng.integers(1, 7, n)
pool = d.date.values[(d.date >= "2023-01-01") & (d.date <= "2026-09-30")]
od = np.sort(rng.choice(pool, n)); od = od[rng.permutation(n)]
t = (pd.to_datetime(od) - pd.Timestamp("2023-01-01")).days.values / 1370.0
lead = s.set_index("supplier_key").std_lead_time_days.reindex(f.supplier_key).values
promised = pd.to_datetime(od) + pd.to_timedelta(lead, unit="D")
late = rng.random(n) < sup_late[f.supplier_key.values - 1] * (1.2 - 0.4 * t)
slip = np.where(late, rng.choice([1, 3, 7, 14, 21], n), -rng.integers(0, 3, n))
received = promised + pd.to_timedelta(slip, unit="D")
f["order_date_key"] = pd.to_datetime(od).strftime("%Y%m%d").astype(int)
f["promised_date_key"] = promised.strftime("%Y%m%d").astype(int)
f["received_date_key"] = received.strftime("%Y%m%d").astype(int)
f["qty_ordered"] = rng.integers(1, 61, n)
short = rng.random(n) < sup_short[f.supplier_key.values - 1]
f["qty_received"] = np.where(short, (f.qty_ordered * rng.uniform(.5, .95, n)).astype(int), f.qty_ordered)
f["unit_cost"] = p.set_index("product_key").unit_cost.reindex(f.product_key).values
f["is_on_time"] = (f.received_date_key <= f.promised_date_key).astype(int)
f["is_in_full"] = (f.qty_received >= f.qty_ordered).astype(int)
f.to_csv(out / "fact_po_lines.csv", index=False)

# fact_inventory_daily: WEEKLY snapshot for every product x location (name kept for simplicity).
# Snapshot data is semi-additive: sum across products/locations, but take the LAST date over time.
weeks = pd.date_range("2023-01-01", "2026-10-25", freq="W-SUN").strftime("%Y%m%d").astype(int).values
n_loc = 6
base = rng.integers(5, 250, (n_prod, n_loc))
inv = pd.DataFrame({
    "date_key": np.repeat(weeks, n_prod * n_loc),
    "product_key": np.tile(np.repeat(np.arange(1, n_prod + 1), n_loc), len(weeks)),
    "location_key": np.tile(np.arange(1, n_loc + 1), len(weeks) * n_prod)})
b = np.tile(base.ravel(), len(weeks))
inv["on_hand_qty"] = (b * rng.uniform(0.6, 1.4, len(inv))).astype(int)
uc = p.set_index("product_key").unit_cost.reindex(inv.product_key).values
inv["on_hand_value"] = np.round(inv.on_hand_qty * uc, 2)
inv.to_csv(out / "fact_inventory_daily.csv", index=False)
print("wrote", [x.name for x in out.glob("*.csv")])
