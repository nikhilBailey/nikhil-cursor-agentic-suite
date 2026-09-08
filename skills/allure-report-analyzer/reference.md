# Allure data formats reference

## Two formats

| Format | Produced by | Use for analysis |
|--------|-------------|------------------|
| **allure-results** | Test runner (`pytest --alluredir`, etc.) | Preferred — raw `*-result.json` files |
| **Allure HTML report** | `allure generate` / CI publish step | Fallback — `data/` and `widgets/` JSON inside the report |

The ingest script tries `*-result.json` first, then HTML report `data/test-cases/` and `data/suites.json` / `data/packages.json`.

## allure-results layout

```
allure-results/
├── <uuid>-result.json      # One file per test invocation
├── <uuid>-container.json
├── <uuid>-attachment.*
└── ...
```

Key fields in `*-result.json`:

| Field | Purpose |
|-------|---------|
| `historyId` | Stable identity across retries (preferred key) |
| `fullName` | Fully qualified test name |
| `name` | Display name (may include param text) |
| `parameters` | `[{ "name": "...", "value": "..." }]` — each param set is a separate test |
| `status` | `passed`, `failed`, `broken`, `skipped`, `unknown` |
| `statusDetails.message` | Failure message |
| `labels` | suite, epic, feature, parentSuite, etc. |

## Generated HTML report layout

```
allure-report/
├── index.html
├── data/
│   ├── test-cases/
│   │   └── <uid>.json
│   ├── suites.json
│   ├── packages.json
│   └── ...
└── widgets/
    ├── summary.json
    ├── suites.json
    └── ...
```

`data/test-cases/*.json` mirrors result shape with `uid` instead of `uuid`.

## Test identity (compare script)

Never key by `fullName` alone — parametrized tests share one `fullName`.

Identity order:

1. `historyId` when present → `history:<id>`
2. Else `(fullName, canonical parameters)` — parameters sorted by name, JSON-serialized

When the same identity appears multiple times (retries), keep the **last non-hidden** result.

## GitHub Actions artifacts

Artifact names vary by project. The download script ranks:

1. Names containing `allure-results`
2. Names containing `allure`
3. Everything else

Use `gh run view <id> --repo <owner/repo> --json artifacts` to list available names.

## Analysis directory

Default: `~/.local/share/allure-analysis` (override with `ALLURE_ANALYSIS_DIR`).

Typical layout after a run:

```
allure-analysis/
├── target-results/ingested.json
├── baseline-results/ingested.json
├── baseline-meta.json          # when baseline was inferred
├── comparison-report.json
├── pr-diff.patch               # optional
└── analysis-report.md
```

## Status semantics

| Status | Meaning |
|--------|---------|
| `passed` | Test succeeded |
| `failed` | Assertion or test logic failure |
| `broken` | Fixture/setup/harness failure (often infra) |
| `skipped` | Not executed |

For suite health, `failed` + `broken` are "red". High `broken` relative to `failed` often indicates harness/fixture collapse.
