"""CI checks: theme JSON valid, DAX file present, no forbidden Power BI artifacts committed."""
import json, pathlib, subprocess, sys
root = pathlib.Path(__file__).resolve().parent.parent
errs = []
theme = json.loads((root / "theme/portfolio-theme.json").read_text())
for k in ("name", "dataColors", "textClasses"):
    if k not in theme: errs.append(f"theme missing {k}")
if len(theme.get("dataColors", [])) < 6: errs.append("theme needs >= 6 data colors")
dax = (root / "dax/measures.dax").read_text()
for m in ("OTIF %", "Inventory Value"):
    if m not in dax: errs.append(f"measure missing: {m}")
try:
    tracked = subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines()
    bad = [t for t in tracked if t.endswith(".pbix") or t.endswith("cache.abf") or t.endswith("localSettings.json")]
    errs += [f"forbidden file tracked: {b}" for b in bad]
except Exception as e:
    print("git check skipped:", e)
if errs:
    print("\n".join(errs)); sys.exit(1)
print("OK")
