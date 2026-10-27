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
| Inventory Value vs PY (SLOW) | 35 | 3 | repeated expressions |
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
| | | | |

## What I learned
_2-4 sentences: what the Storage vs Formula engine split showed, which change mattered most._
