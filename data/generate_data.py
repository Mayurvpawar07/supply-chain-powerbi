"""Generate a SYNTHETIC supply chain star schema (no real company data).

Usage: python data/generate_data.py --inventory-rows 3000000
Output: data/out/*.csv  (gitignored)
"""
import argparse, pathlib
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--inventory-rows", type=int, default=3_000_000)
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
n_prod = 1500
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
n = a.po_lines
f = pd.DataFrame({"po_line_id": np.arange(1, n + 1)})
f["po_id"] = (f.po_line_id // 4) + 100000
f["product_key"] = rng.integers(1, n_prod + 1, n)
f["supplier_key"] = rng.integers(1, n_sup + 1, n)
f["location_key"] = rng.integers(1, 7, n)
od = rng.choice(d.date.values[(d.date >= "2023-01-01") & (d.date <= "2026-09-30")], n)
lead = s.set_index("supplier_key").std_lead_time_days.reindex(f.supplier_key).values
promised = pd.to_datetime(od) + pd.to_timedelta(lead, unit="D")
slip = rng.choice([0, 0, 0, 1, 3, 7, 14], n) * (rng.random(n) < 0.35)
received = promised + pd.to_timedelta(slip - rng.integers(0, 3, n), unit="D")
f["order_date_key"] = pd.to_datetime(od).strftime("%Y%m%d").astype(int)
f["promised_date_key"] = promised.strftime("%Y%m%d").astype(int)
f["received_date_key"] = received.strftime("%Y%m%d").astype(int)
f["qty_ordered"] = rng.integers(10, 2000, n)
f["qty_received"] = np.where(rng.random(n) < 0.88, f.qty_ordered, (f.qty_ordered * rng.uniform(.5, .99, n)).astype(int))
f["unit_cost"] = p.set_index("product_key").unit_cost.reindex(f.product_key).values
f["is_on_time"] = (f.received_date_key <= f.promised_date_key).astype(int)
f["is_in_full"] = (f.qty_received >= f.qty_ordered).astype(int)
f.to_csv(out / "fact_po_lines.csv", index=False)

# fact_inventory_daily (large table for the tuning exercise)
m = a.inventory_rows
inv = pd.DataFrame({"date_key": rng.choice(keys[:1370], m),
                    "product_key": rng.integers(1, n_prod + 1, m),
                    "location_key": rng.integers(1, 7, m),
                    "on_hand_qty": rng.integers(0, 5000, m)})
uc = p.set_index("product_key").unit_cost.reindex(inv.product_key).values
inv["on_hand_value"] = np.round(inv.on_hand_qty * uc, 2)
inv.to_csv(out / "fact_inventory_daily.csv", index=False)
print("wrote", [x.name for x in out.glob("*.csv")])
