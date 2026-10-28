-- ============================================================================
-- Advanced SQL analysis on the synthetic supply chain star schema
-- Tables: dim_date, dim_product, dim_supplier, dim_location,
--         fact_po_lines, fact_inventory_daily (weekly snapshots)
--
-- Written in ANSI-style SQL that runs on Snowflake and SQLite (used by
-- tools/test_sql.py to check every query against an independent pandas
-- calculation). Each query starts with "-- name:" so the test script can find it.
--
-- Patterns used: CTEs, JOINs, conditional aggregation, RANK / NTILE,
-- running totals, LAG, rolling windows (ROWS BETWEEN), gaps-and-islands,
-- semi-additive snapshot logic, and guards for missing months.
-- All data is synthetic; findings are illustrative.
-- ============================================================================


-- name: q1_monthly_otif_rolling_yoy
-- Business question: is OTIF improving, and is the improvement real or noise?
-- Monthly OTIF %, a rolling 3-month OTIF % (smooths noise), and the year-over-year
-- change in percentage points. Month is the PO order month.
WITH po_month AS (
    SELECT
        d.year_month,
        d.year * 12 + d.month_num AS month_idx,          -- consecutive integer per month
        COUNT(*)                  AS po_lines,
        SUM(CASE WHEN f.is_on_time = 1 AND f.is_in_full = 1 THEN 1 ELSE 0 END) AS otif_lines
    FROM fact_po_lines AS f
    JOIN dim_date      AS d ON d.date_key = f.order_date_key
    GROUP BY d.year_month, d.year, d.month_num
),
windowed AS (
    SELECT
        year_month,
        month_idx,
        po_lines,
        otif_lines,
        -- rolling 3 months: this month plus the 2 before it
        SUM(otif_lines) OVER (ORDER BY month_idx ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS otif_3m,
        SUM(po_lines)   OVER (ORDER BY month_idx ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS lines_3m,
        COUNT(*)        OVER (ORDER BY month_idx ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS months_in_window,
        -- same month last year, with a guard in case a month is missing
        LAG(otif_lines, 12) OVER (ORDER BY month_idx) AS otif_py,
        LAG(po_lines, 12)   OVER (ORDER BY month_idx) AS lines_py,
        LAG(month_idx, 12)  OVER (ORDER BY month_idx) AS month_idx_py
    FROM po_month
)
SELECT
    year_month,
    po_lines,
    ROUND(100.0 * otif_lines / po_lines, 2)                         AS otif_pct,
    CASE WHEN months_in_window = 3
         THEN ROUND(100.0 * otif_3m / lines_3m, 2) END              AS otif_pct_rolling_3m,
    CASE WHEN month_idx - month_idx_py = 12
         THEN ROUND(100.0 * otif_lines / po_lines
                    - 100.0 * otif_py / lines_py, 2) END            AS otif_yoy_pts
FROM windowed
ORDER BY month_idx;


-- name: q2_supplier_scorecard
-- Business question: which suppliers are worst, relative to their peers, and how
-- concentrated is spend? Suppliers need at least 100 PO lines to be ranked.
-- Ranks OTIF within country, splits suppliers into quartiles, compares each supplier
-- to its country average, and adds a cumulative spend share (Pareto, A/B/C by spend).
WITH supplier_stats AS (
    SELECT
        s.supplier_key,
        s.supplier_name,
        s.country,
        COUNT(*)                                                                  AS po_lines,
        SUM(CASE WHEN f.is_on_time = 1 AND f.is_in_full = 1 THEN 1 ELSE 0 END)    AS otif_lines,
        SUM(f.qty_received * f.unit_cost)                                         AS spend
    FROM fact_po_lines AS f
    JOIN dim_supplier  AS s ON s.supplier_key = f.supplier_key
    GROUP BY s.supplier_key, s.supplier_name, s.country
    HAVING COUNT(*) >= 100
),
scored AS (
    SELECT
        supplier_key, supplier_name, country, po_lines, spend,
        1.0 * otif_lines / po_lines AS otif_rate
    FROM supplier_stats
),
ranked AS (
    SELECT
        scored.*,
        RANK()   OVER (PARTITION BY country ORDER BY otif_rate ASC)  AS worst_rank_in_country,
        NTILE(4) OVER (ORDER BY otif_rate ASC)                       AS otif_quartile,   -- 1 = worst 25%
        AVG(otif_rate) OVER (PARTITION BY country)                   AS country_avg_otif,
        SUM(spend) OVER (ORDER BY spend DESC, supplier_key
                         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_spend,
        SUM(spend) OVER ()                                           AS total_spend
    FROM scored
)
SELECT
    supplier_name,
    country,
    po_lines,
    ROUND(spend, 0)                                           AS spend,
    ROUND(100.0 * otif_rate, 2)                               AS otif_pct,
    worst_rank_in_country,
    otif_quartile,
    ROUND(100.0 * (otif_rate - country_avg_otif), 2)          AS pts_vs_country_avg,
    ROUND(100.0 * cum_spend / total_spend, 2)                 AS cum_spend_pct,
    CASE WHEN 1.0 * (cum_spend - spend) / total_spend < 0.80 THEN 'A'
         WHEN 1.0 * (cum_spend - spend) / total_spend < 0.95 THEN 'B'
         ELSE 'C' END                                         AS spend_class
FROM ranked
ORDER BY otif_rate ASC, supplier_name;


-- name: q3_chronic_underperformance_streaks
-- Business question: which suppliers have been below the OTIF target for several
-- months IN A ROW (a chronic problem, not a one-off bad month)?
-- Gaps-and-islands: for the flagged months only, month_idx minus ROW_NUMBER is
-- constant within a run of consecutive months, so grouping by it finds each streak.
-- Target 50% (about 15 points below the synthetic network average of ~65%); a supplier-month needs at least 10 PO lines; streak of 3+ months.
WITH supplier_month AS (
    SELECT
        f.supplier_key,
        d.year_month,
        d.year * 12 + d.month_num AS month_idx,
        COUNT(*)                  AS po_lines,
        1.0 * SUM(CASE WHEN f.is_on_time = 1 AND f.is_in_full = 1 THEN 1 ELSE 0 END) / COUNT(*) AS otif_rate
    FROM fact_po_lines AS f
    JOIN dim_date      AS d ON d.date_key = f.order_date_key
    GROUP BY f.supplier_key, d.year_month, d.year, d.month_num
    HAVING COUNT(*) >= 10
),
below_target AS (
    SELECT supplier_key, year_month, month_idx, otif_rate
    FROM supplier_month
    WHERE otif_rate < 0.50
),
islands AS (
    SELECT
        supplier_key,
        year_month,
        month_idx,
        otif_rate,
        month_idx - ROW_NUMBER() OVER (PARTITION BY supplier_key ORDER BY month_idx) AS island_id
    FROM below_target
),
streaks AS (
    SELECT
        supplier_key,
        island_id,
        COUNT(*)        AS streak_months,
        MIN(year_month) AS streak_start,      -- 'YYYY-MM' strings sort correctly
        MAX(year_month) AS streak_end,
        AVG(otif_rate)  AS avg_otif_in_streak
    FROM islands
    GROUP BY supplier_key, island_id
    HAVING COUNT(*) >= 3
)
SELECT
    s.supplier_name,
    s.country,
    t.streak_months,
    t.streak_start,
    t.streak_end,
    ROUND(100.0 * t.avg_otif_in_streak, 2) AS avg_otif_pct,
    RANK() OVER (ORDER BY t.streak_months DESC, t.avg_otif_in_streak ASC) AS severity_rank
FROM streaks AS t
JOIN dim_supplier AS s ON s.supplier_key = t.supplier_key
ORDER BY severity_rank, s.supplier_name, streak_start;


-- name: q4_month_end_inventory_mom_yoy
-- Business question: how is inventory value trending, and what share is A-class?
-- Inventory is a weekly SNAPSHOT (semi-additive): add across products and locations,
-- but never across time. So take each month's LAST snapshot only, then compare it with
-- the prior month and the same month last year. Mirrors the DAX [Inventory Value] measure.
WITH snapshot_dates AS (
    SELECT DISTINCT i.date_key
    FROM fact_inventory_daily AS i
),
last_snapshot AS (
    SELECT
        sd.date_key,
        d.year_month,
        d.year * 12 + d.month_num AS month_idx,
        ROW_NUMBER() OVER (PARTITION BY d.year_month ORDER BY sd.date_key DESC) AS rn
    FROM snapshot_dates AS sd
    JOIN dim_date       AS d ON d.date_key = sd.date_key
),
month_end AS (
    SELECT
        ls.year_month,
        ls.month_idx,
        SUM(i.on_hand_value) AS inventory_value,
        SUM(CASE WHEN p.abc_class = 'A' THEN i.on_hand_value ELSE 0 END) AS a_class_value
    FROM last_snapshot        AS ls
    JOIN fact_inventory_daily AS i ON i.date_key = ls.date_key
    JOIN dim_product          AS p ON p.product_key = i.product_key
    WHERE ls.rn = 1
    GROUP BY ls.year_month, ls.month_idx
),
with_lags AS (
    SELECT
        year_month,
        month_idx,
        inventory_value,
        a_class_value,
        LAG(inventory_value, 1)  OVER (ORDER BY month_idx) AS value_prev_month,
        LAG(month_idx, 1)        OVER (ORDER BY month_idx) AS idx_prev_month,
        LAG(inventory_value, 12) OVER (ORDER BY month_idx) AS value_prev_year,
        LAG(month_idx, 12)       OVER (ORDER BY month_idx) AS idx_prev_year
    FROM month_end
)
SELECT
    year_month,
    ROUND(inventory_value, 0)                                              AS inventory_value,
    ROUND(100.0 * a_class_value / inventory_value, 2)                      AS a_class_share_pct,
    CASE WHEN month_idx - idx_prev_month = 1
         THEN ROUND(100.0 * (inventory_value / value_prev_month - 1), 2) END AS mom_pct,
    CASE WHEN month_idx - idx_prev_year = 12
         THEN ROUND(100.0 * (inventory_value / value_prev_year - 1), 2) END  AS yoy_pct
FROM with_lags
ORDER BY month_idx;
