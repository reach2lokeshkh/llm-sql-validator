# llm-sql-validator

**A progressive, 5-tier validation framework for LLM-generated SQL queries.**

Stop shipping broken SQL to production. `llm-sql-validator` catches errors that LLMs make — before they hit your database.

[![PyPI version](https://img.shields.io/pypi/v/llm-sql-validator.svg)](https://pypi.org/project/llm-sql-validator/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/reach2lokeshkh/llm-sql-validator/actions/workflows/ci.yml/badge.svg)](https://github.com/reach2lokeshkh/llm-sql-validator/actions/workflows/ci.yml)

---

## The Problem

LLMs generate SQL that *looks* correct but frequently:
- References tables/columns that don't exist
- Produces cartesian joins on large tables (query runs for hours, costs $$)
- Violates business rules (e.g., queries PII columns without filters, ignores soft-delete flags)
- Returns unsafe operations (DROP, DELETE, TRUNCATE) when only SELECT was expected
- Uses wrong aggregation logic that returns subtly incorrect numbers

Most teams catch these in production — after the dashboard is wrong or the query times out.

## The Solution

`llm-sql-validator` runs every LLM-generated query through a **5-tier progressive validation pipeline** before execution:

```
┌─────────────────────────────────────────────────────────┐
│  Tier 1: SYNTAX         Parse & validate SQL grammar    │
│  Tier 2: SCHEMA         Verify tables/columns exist     │
│  Tier 3: BUSINESS RULES Enforce domain-specific policy  │
│  Tier 4: SAFETY         Block dangerous operations      │
│  Tier 5: OUTPUT         Validate result characteristics │
└─────────────────────────────────────────────────────────┘
```

Each tier is independent, configurable, and fails fast — so you get clear error messages about *what's wrong and why* rather than cryptic database errors.

---

## Quick Start

### Installation

```bash
pip install llm-sql-validator
```

### Basic Usage (5 lines)

```python
from llm_sql_validator import ValidationPipeline, ValidatorConfig

# Define your schema
config = ValidatorConfig.from_yaml("schema.yaml")

# Create the pipeline
pipeline = ValidationPipeline(config)

# Validate any LLM-generated SQL
result = pipeline.validate("SELECT customer_name, email FROM users WHERE age > 25")

if result.is_valid:
    print("Safe to execute!")
else:
    print(f"Blocked at tier {result.failed_tier}: {result.errors}")
```

### Output

```
Blocked at tier SCHEMA: Column 'customer_name' does not exist in table 'users'. 
Did you mean 'first_name' or 'full_name'?
```

---

## Features

### Tier 1: Syntax Validation
- SQL grammar parsing using [sqlglot](https://github.com/tobymao/sqlglot)
- Dialect-aware (PostgreSQL, Redshift, BigQuery, Snowflake, MySQL, SQLite)
- Clear error messages with position information

### Tier 2: Schema Validation
- Verify all referenced tables, columns, and schemas exist
- Type compatibility checking for comparisons and functions
- Fuzzy column name suggestions on mismatch ("Did you mean...?")
- Support for schema definition via YAML, JSON, or live database introspection

### Tier 3: Business Rules Engine
- YAML-configurable rules per team, domain, or use case
- Built-in rule types:
  - **Required filters** (e.g., "queries on `orders` must include a date range")
  - **Forbidden columns** (e.g., "never expose `ssn` or `credit_card` without masking")
  - **Mandatory joins** (e.g., "always join with `access_control` table")
  - **Row limit enforcement** (e.g., "SELECT without LIMIT on tables > 1B rows must have WHERE")
  - **Aggregation guards** (e.g., "COUNT(DISTINCT) on high-cardinality columns requires approval")
- Custom rule plugins via simple Python interface

### Tier 4: Safety Validation
- Block DDL operations (CREATE, DROP, ALTER, TRUNCATE)
- Block DML mutations (INSERT, UPDATE, DELETE) when read-only mode is configured
- Detect cartesian joins and unbounded cross joins
- Flag queries with estimated cost above configurable thresholds
- Prevent SQL injection patterns in parameterized LLM outputs

### Tier 5: Output Validation
- Validate expected column count and types in result set
- Check for NULL-heaviness indicators
- Detect suspiciously small or large result sets based on historical patterns
- Anti-example detection: flag queries that match previously-failed patterns

---

## Configuration

### Schema Definition (YAML)

```yaml
# schema.yaml
dialect: redshift
schemas:
  public:
    users:
      columns:
        id: { type: integer, primary_key: true }
        first_name: { type: varchar }
        last_name: { type: varchar }
        email: { type: varchar, pii: true }
        created_at: { type: timestamp }
        is_deleted: { type: boolean, soft_delete: true }
    orders:
      columns:
        id: { type: integer, primary_key: true }
        user_id: { type: integer, foreign_key: users.id }
        amount: { type: decimal }
        order_date: { type: date }
        status: { type: varchar }
      row_estimate: 500_000_000
```

### Business Rules (YAML)

```yaml
# rules.yaml
rules:
  - name: require_date_filter_on_orders
    description: "Queries on orders table must include a date range filter"
    target_tables: [orders]
    rule_type: required_filter
    filter_columns: [order_date]
    
  - name: block_pii_without_masking
    description: "PII columns cannot be selected without masking function"
    rule_type: forbidden_columns
    columns_with_tag: pii
    unless_wrapped_in: [mask, hash, anonymize]
    
  - name: enforce_soft_delete
    description: "Always filter out soft-deleted records"
    target_tables: [users]
    rule_type: required_filter
    filter_expression: "is_deleted = false"
    
  - name: limit_on_large_tables
    description: "Queries on tables with >100M rows must have LIMIT or WHERE"
    rule_type: row_limit
    row_threshold: 100_000_000
    max_limit: 10000
```

---

## Advanced Usage

### Custom Validator Plugin

```python
from llm_sql_validator import ValidationPipeline, ValidatorConfig
from llm_sql_validator.validators import BaseValidator
from llm_sql_validator.result import ValidationResult, ValidationStatus

class CostEstimateValidator(BaseValidator):
    """Block queries with estimated cost above threshold."""
    
    tier = "SAFETY"
    
    def validate(self, sql: str, context: dict) -> ValidationResult:
        estimated_rows = self.estimate_scan_rows(sql)
        if estimated_rows > self.config.max_scan_rows:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                tier=self.tier,
                errors=[f"Query would scan ~{estimated_rows:,} rows (limit: {self.config.max_scan_rows:,})"],
                suggestion="Add a WHERE clause to reduce scan scope",
            )
        return ValidationResult(status=ValidationStatus.PASSED, tier=self.tier)

# Register custom validator
config = ValidatorConfig.from_yaml("schema.yaml")
pipeline = ValidationPipeline(config)
pipeline.register_validator(CostEstimateValidator(max_scan_rows=10_000_000))
```

### Anti-Example Detection (Feedback Learning)

```python
from llm_sql_validator import ValidationPipeline

pipeline = ValidationPipeline.from_yaml("schema.yaml")

# Record a query that produced wrong results
pipeline.record_anti_example(
    sql="SELECT COUNT(*) FROM orders",  # Missing date filter, returned stale count
    reason="Missing required date range — returned lifetime count instead of daily",
)

# Future similar queries get flagged
result = pipeline.validate("SELECT SUM(amount) FROM orders")
# => Warning: Similar pattern to known anti-example. Consider adding date filter.
```

### Integration with LangChain

```python
from langchain_community.utilities import SQLDatabase
from llm_sql_validator import ValidationPipeline

pipeline = ValidationPipeline.from_yaml("schema.yaml")

def validated_query(llm_output: str) -> str:
    """Validate before executing."""
    result = pipeline.validate(llm_output)
    if not result.is_valid:
        raise ValueError(f"Query failed validation: {result.errors}")
    return llm_output

# Use as a chain step
chain = llm | validated_query | db.run
```

---

## Supported SQL Dialects

| Dialect | Status |
|---------|--------|
| PostgreSQL | Fully supported |
| Amazon Redshift | Fully supported |
| Google BigQuery | Fully supported |
| Snowflake | Fully supported |
| MySQL | Fully supported |
| SQLite | Fully supported |
| DuckDB | Fully supported |
| Trino/Presto | Beta |

---

## Why Not Just Use...

| Approach | Problem |
|----------|---------|
| Database EXPLAIN | Only catches syntax/schema — misses business rules, safety, anti-examples |
| LLM self-check | Hallucinations can't reliably detect hallucinations |
| Unit tests on queries | Only works for known queries, not dynamic LLM output |
| SQL linters (sqlfluff) | Designed for human-written SQL style, not LLM correctness |
| **llm-sql-validator** | Purpose-built for the LLM-generated SQL failure modes |

---

## Roadmap

- [ ] v0.1 — Core 5-tier pipeline, YAML config, basic rules engine
- [ ] v0.2 — Anti-example store with similarity matching
- [ ] v0.3 — Live database introspection for schema validation
- [ ] v0.4 — LangChain / LlamaIndex native integrations
- [ ] v0.5 — Cost estimation heuristics per dialect
- [ ] v1.0 — Stable API, full documentation site

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas where help is most needed:
- Additional SQL dialect support
- New business rule types
- Integration examples (Vanna.ai, Dataherald, custom agents)
- Documentation and tutorials

---

## Citation

If you use this library in academic work or internal tooling, please cite:

```bibtex
@software{llm_sql_validator,
  author = {Lokesh Kumar H},
  title = {llm-sql-validator: Progressive Validation Framework for LLM-Generated SQL},
  year = {2026},
  url = {https://github.com/reach2lokeshkh/llm-sql-validator}
}
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
