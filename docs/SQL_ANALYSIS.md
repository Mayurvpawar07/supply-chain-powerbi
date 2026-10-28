# SQL analysis (CTEs and window functions)

`sql/analysis.sql` holds four analytical queries on the same synthetic star schema the Power BI report uses.
The SQL is ANSI-style, so the same text runs on Snowflake. `tools/test_sql.py` loads the generated CSVs into
an in-memory SQLite database and checks every query against an independent pandas calculation (22 checks).

| Query | Business question | Techniques |
|---|---|---|
| `q1_monthly_otif_rolling_yoy` | Is OTIF improving, or is it noise? | CTEs, conditional aggregation, rolling 3-month `ROWS BETWEEN`, `LAG(…, 12)` for YoY, missing-month guard |
| `q2_supplier_scorecard` | Which suppliers are worst versus their peers, and how concentrated is spend? | `RANK` and `AVG` over `PARTITION BY country`, `NTILE(4)`, running total for a spend Pareto (A/B/C) |
| `q3_chronic_underperformance_streaks` | Which suppliers have missed target for 3+ months in a row? | Gaps-and-islands (`month_idx - ROW_NUMBER()`), `HAVING`, `RANK` |
| `q4_month_end_inventory_mom_yoy` | How is inventory value trending, and what share is A-class? | Semi-additive snapshot logic (last snapshot per month via `ROW_NUMBER`), `LAG` for MoM and YoY |

## Design notes
- **Snapshots are never summed across time.** Q4 picks each month's last weekly snapshot, the SQL equivalent of the DAX `[Inventory Value]` measure.
- **Gaps are guarded.** `LAG(…, 12)` only counts as year-over-year when the month index really is 12 apart; otherwise the result is NULL, not a wrong comparison.
- **Small samples are excluded.** Supplier ranking needs 100+ PO lines; a supplier-month needs 10+.
- **Portable division.** Percentages use `100.0 * x / y`, and no integer-division tricks, because Snowflake and SQLite divide integers differently.

## Run it
```
pip install pandas numpy
python data/generate_data.py --products 300 --po-lines 60000
python tools/test_sql.py
```
To run on Snowflake, load the generated CSVs into tables with the same names and run each query from `sql/analysis.sql`.

## Limitations
Synthetic data, so findings (for example, the chronically late suppliers) are illustrative. The tests prove the SQL logic, not real-world conclusions. The queries have been tested on SQLite only; Snowflake execution is expected to work but is not yet verified.
