# SQL Validation Benchmark

A reproducible benchmark that measures how well **this library**
(`llm-sql-validator`) catches the failure modes of machine-generated SQL,
compared against the two alternatives teams commonly reach for: a
parse/`EXPLAIN`-only check and a style linter.

It exists to answer, with numbers, the central claim behind the five-tier
design: that layering catches defect classes no single mechanism can.

## What it does

The script generates a labeled corpus of 1,800 machine-generated queries
(1,500 with an injected defect, 300 clean) against a declared four-table schema,
then runs three validators over it:

1. **Parse / `EXPLAIN` only** (baseline) — parses the query (via `sqlglot`) and
   checks only that it is well-formed and references resolvable objects. Blind to
   policy and safety by construction.
2. **Style linter (analog, baseline)** — flags stylistic issues only.
3. **The five-tier pipeline** — this library's `ValidationPipeline`, configured
   with the same schema and business rules the corpus is generated against.

## Defect classes

- `clean` — valid, policy-compliant read query (must pass)
- `hallucinated_schema` — references a column/table that does not exist
- `missing_filter` — omits a business-required tenant filter
- `forbidden_pii` — selects a restricted personal-data column unmasked
- `unsafe_operation` — a destructive or cartesian statement in a read context
- `wrong_join_grain` — syntactically valid, schema-correct, policy-compliant,
  read-only, but computes an inflated aggregate across a one-to-many join (an
  *intent* error, included to mark the boundary of static validation)

## Results (seed = 42)

| Validator | Precision | Recall | F1 | False-Positive Rate |
|---|---|---|---|---|
| Parse / `EXPLAIN` only | 1.000 | 0.200 | 0.333 | 0.000 |
| Style linter | 1.000 | 0.102 | 0.185 | 0.000 |
| Five-tier pipeline | 1.000 | 0.747 | 0.855 | 0.000 |

Detection by defect class, and the tier that caught each:

| Defect class | Parse-only | Linter | Five-tier | Caught at tier |
|---|---|---|---|---|
| hallucinated_schema | 1.000 | 0.283 | 0.733 | SCHEMA |
| missing_filter | 0.000 | 0.000 | 1.000 | BUSINESS_RULES |
| forbidden_pii | 0.000 | 0.000 | 1.000 | BUSINESS_RULES |
| unsafe_operation | 0.000 | 0.227 | 1.000 | SAFETY |
| wrong_join_grain | 0.000 | 0.000 | 0.000 | not caught (passes) |

**Reading the results honestly.** The pipeline catches every defect class it has
a tier for, each at the responsible tier. Two results are reported exactly as
measured, including where the library falls short:

- **`hallucinated_schema` = 0.733.** The schema tier catches most nonexistent-object
  references but currently passes a *qualified misspelled column* (for example
  `o.customre_id`) whose alias resolves to a real table. This is a known
  limitation worth improving; the benchmark surfaces it rather than hiding it.
- **`wrong_join_grain` = 0.000.** The library has no grain-checking tier and does
  not claim one. Whether such a query is "wrong" depends on intent no static
  validator can see, so these queries must be surfaced to a human reviewer. This
  is the deliberate boundary of the tool, not a bug.

Even so, layering raises detection from the parser's 20% floor to ~75% overall
with zero false positives — coverage no single mechanism reaches.

## Reproduce

From the repository root, with the library installed (`pip install -e .`):

```bash
pip install sqlglot numpy
python benchmarks/sql_validation/run_sql_validation_experiment.py
```

Outputs are written to `benchmarks/sql_validation/results/`:

- `sql_validation_metrics.json` — full metrics, per-defect-class detection,
  confusion-matrix counts, and the tier at which each class was caught.
- `sql_validation_results_table.md` — the tables above.

All numbers come from a single seeded run (seed = 42) and are fully reproducible.
The corpus, schema, and defects are synthetic; no proprietary data is used.
