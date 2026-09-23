# Measured Multi-Tier Validation of Machine-Generated SQL

**Corpus:** 1,800 machine-generated queries (1500 with an injected defect, 300 clean) against a declared four-table schema. **Dialect:** postgres. **Seed:** 42

The layered validator under test is the author's real open-source library `llm-sql-validator`, imported and called through its public validation pipeline — not a re-implementation. The parse-only and style-linter columns are baselines representing the common alternatives.

| Validator | Precision | Recall | F1 | False-Positive Rate |
|-----------|-----------|--------|-----|---------------------|
| Parse / EXPLAIN only | 1.0 | 0.2 | 0.333 | 0.0 |
| Style linter | 1.0 | 0.102 | 0.185 | 0.0 |
| Five-tier validator (llm-sql-validator) | 1.0 | 0.8 | 0.889 | 0.0 |

## Detection rate by defect class

| Validator | hallucinated_schema | missing_filter | forbidden_pii | unsafe_operation | wrong_join_grain |
|-----------|---|---|---|---|---|
| Parse / EXPLAIN only | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Style linter | 0.283 | 0.0 | 0.0 | 0.227 | 0.0 |
| Five-tier validator (llm-sql-validator) | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |

## Which tier of the real library caught each defect class

| Defect class | Caught at tier |
|--------------|----------------|
| hallucinated_schema | SCHEMA |
| missing_filter | BUSINESS_RULES |
| forbidden_pii | BUSINESS_RULES |
| unsafe_operation | SAFETY |
| wrong_join_grain | not caught (passes) |

**Key finding:** A parse/EXPLAIN-style check catches malformed and schema-invalid queries but is blind by construction to policy and safety defects. A style linter catches essentially none of the correctness defects. The real five-tier library catches every defect class for which it has a tier — schema errors at the schema tier, missing filters and restricted-column access at the business-rules tier, and destructive or cartesian statements at the safety tier — while leaving clean queries (including legitimate child-grain aggregates) to pass. Its one honest non-detection is the semantic grain error: a query that is syntactically valid, schema-correct, policy-compliant, and read-only but computes an inflated aggregate across a one-to-many join. The library has no grain-checking tier and does not claim one, so it passes these — which is exactly the class that must be handed to a human reviewer, because whether such a query is 'wrong' depends on intent no static validator can see. Layering raises detection from the parser's floor to near-complete coverage of the specifiable defect classes, which no single mechanism achieves.

*All values measured from a single seeded run (seed=42) against the real `llm-sql-validator` library; fully reproducible.*