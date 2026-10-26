# CI/CD for this report

## What is automated here (works on any GitHub account)
- `validate.yml` runs on every push/PR: theme JSON checks, required measures present, no `.pbix`/cache files tracked, data generator smoke test.

## Branching
`main` = published state. Work on feature branches, open a PR, CI must pass, squash-merge.

## Promotion to the Power BI Service (optional, depends on your license)
Options, from simplest:
1. Manual publish from Desktop (no CI/CD; fine for the portfolio).
2. Fabric/Power BI workspace Git integration (connect a workspace to the repo's `report/` folder). Typically needs a Fabric/Premium-capable workspace; check what your account allows.
3. Deployment pipelines (Dev -> Test -> Prod) with deployment rules for data source parameters; also capacity-dependent.

Document which option you actually used. If you only did 1 and CI validation, say exactly that in the README.
