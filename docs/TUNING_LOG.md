# Performance tuning log

Method: Power BI Desktop > Optimize > Performance analyzer > Start recording > Refresh visuals > Copy query.
Paste DAX queries into DAX Studio > Server Timings, clear cache between runs, run each 3 times, record the median.
Use VertiPaq Analyzer (DAX Studio > Advanced > View Metrics) for model size.

**Rule:** write only numbers you measured. Never edit results to look better.

## Environment
- Rows: fact_inventory_daily = 1,800,000 , fact_po_lines = 400,000
- Power BI Desktop version: 2.159.883.0 64-bit (October, 2026)  Machine: Yoga 7 14IRL8 16 GB RAM

## Baseline (BEFORE)
| Visual / measure | DAX duration (ms) | Storage engine queries | Notes |
|---|---|---|---|
| Inventory Value (SLOW) by category | 295 | 3 | SUMX + RELATED |
| OTIF % (SLOW) by month | 13 | 3 | FILTER over fact table |
| Inventory Value vs PY (SLOW) | 35 | 3 | calls SLOW measure twice (current and PY) |
Model size (VertiPaq): 20.56 MB. Top 3 columns by size: on_hand_value, product_key, po_line_id

Evidence: docs/perf/baseline.json, docs/img/baseline-timings.png

## Changes (one commit each)
1. Pre-compute `on_hand_value`; measure becomes `SUM`.
2. Pre-compute `is_on_time`/`is_in_full` flags; `CALCULATE` with boolean filters.
3. Use variables for repeated sub-expressions.
4. Reduce cardinality: remove unused columns; drop/split high-cardinality columns; set correct data types; integer keys.
5. (Optional) Aggregation table or incremental refresh settings for the inventory fact.

## Results (AFTER)
| Visual / measure | Before (ms) | After (ms) | Change |
|---|---|---|---|
| Inventory Value by category | 295 | 117 | Pre-computed on_hand_value; SUM with a date-column filter replaces SUMX + RELATED over FILTER |
| OTIF % by month | 13 | 3 | Boolean CALCULATE filters on pre-computed flags; no meaningful difference expected at 400K rows |
| Inventory Value vs PY | 35 | 32 | VARs and the fast base measure replace two calls to the SLOW measure - no meaningful change |
Method: DAX Studio Server Timings, cache cleared before each run, median of 5 runs.
Model size (VertiPaq): 20.56 MB -> 16.66 MB (-19%) after removing unused columns (po_line_id, on_hand_qty). Largest columns: on_hand_value, product_key, date_key.

## What I learned
- **Inventory Value was the one real bottleneck.** `Inventory Value (SLOW)` took 295 ms
  because it filtered and iterated the 1.8M-row snapshot table row by row (SUMX + RELATED).
  Pre-computing `on_hand_value` at load time and using a single SUM with a date-column
  filter cut it to 117 ms (about 60% faster).
- **Not every change moved the needle.** `OTIF %` went from 13 ms to 3 ms and
  `Inventory Value vs PY` from 35 ms to 32 ms. At these sizes (400K and 1.8M rows) both
  are already fast, and differences this small are close to measurement noise, so I
  don't claim them as wins. I kept the cleaner patterns (boolean filters, variables)
  for readability and for larger data.
- **The remaining 117 ms is worth investigating.** My next step would be checking
  the Storage Engine vs Formula Engine split in Server Timings to see whether the time
  is in the scan or in the semi-additive "latest snapshot" logic, and whether an
  aggregation table would help.
- **Removing unused columns cut model size by 19%** (20.56 MB -> 16.66 MB) with no
  change to any visual. The largest remaining column is `on_hand_value`, a
  high-cardinality decimal.
- **Trade-off:** pre-computing moves cost from query time to refresh time, and the stored
  value has to be rebuilt if unit costs change.
