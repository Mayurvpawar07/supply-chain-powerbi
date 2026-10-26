# Design spec

**Audience:** Supply chain / procurement leadership. **Question each page answers in 5 seconds** is written in the title.

## Grid and style
- Canvas 1280x720, 16:9. 24px outer margin, 16px gutters, everything snapped to a 8px grid (View > Gridlines + Snap to grid).
- One theme file, max 2 accent colors per page; red/green only for good/bad status.
- KPI cards top row (4 max), trend + breakdown middle, detail table bottom. Left-to-right, top-to-bottom = summary to detail.
- Consistent titles: sentence case, 12pt; axis titles off when the chart title says it.
- Tooltip pages for KPI cards; drill-through from supplier to PO lines. Bookmarks for a "reset filters" button.
- Accessibility: alt text on every visual, tab order set, contrast >= 4.5:1, don't rely on color alone.

## Pages
1. **Overview: "Are suppliers delivering on time and in full?"** KPI cards: OTIF %, On-Time %, In-Full %, Spend. Line: OTIF % by month. Bar: OTIF % by supplier country. Slicers: year, location.
2. **Supplier performance: "Which suppliers drive late/short deliveries?"** Ranked bar (OTIF % by supplier, top/bottom 10), scatter (spend vs OTIF %), drill-through to PO lines table.
3. **Inventory: "Where is working capital sitting?"** Cards: Inventory Value, vs PY %. Stacked column by category and ABC class, matrix by location x category.
4. **About / data notes:** synthetic data disclosure, model diagram screenshot, metric definitions.

## Checklist before publishing
- [ ] No visual overlaps, aligned to grid  - [ ] Alt text set  - [ ] Mobile layout optional  - [ ] Performance Analyzer run on every page
