# Setup, step by step (Windows; Power BI Desktop is Windows-only)

1. **Generate data**: `pip install pandas numpy`, then `python data/generate_data.py`. CSVs land in `data/out/`.
2. **Enable PBIP**: Power BI Desktop > File > Options > Preview features > "Power BI Project (.pbip) save option" (wording may vary by version). Restart Desktop.
3. **Build the model**: Get Data > Folder/CSV for the 6 files. In Power Query: set types, disable load for nothing extra, remove unused columns. In Model view: relationships dim -> fact on the `*_key` columns (single direction), mark `dim_date` as date table, hide key columns on facts, add the measures from `dax/measures.dax`.
4. **Apply the theme**: View > Themes > Browse for themes > `theme/portfolio-theme.json`.
5. **Design the pages** per `docs/DESIGN_SPEC.md`.
6. **Save as PBIP** into `report/` (File > Save as > Power BI Project). This writes the report and semantic model as text files that diff cleanly in Git.
7. **Git**: `git init`, `git add .`, commit, create a GitHub repo, push. Confirm `.pbix`, `cache.abf` and `localSettings.json` are NOT tracked (`python tools/validate.py`).
8. **Tune** per `docs/TUNING_LOG.md`, commit before and after as separate commits so the history shows the change.
9. **Publish**: export page screenshots to `docs/img/`, fill in the README results. Optionally publish to the web only if the data is synthetic (it is) and your tenant allows it.
