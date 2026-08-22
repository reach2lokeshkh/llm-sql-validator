# Why I Built a Validation Framework for LLM-Generated SQL (And Why You Need One Too)

*By Lokesh Kumar H | Data Engineer | Creator of llm-sql-validator*

---

## The $200 Query That Shouldn't Have Run

A marketing analyst asked our text-to-SQL tool: "How many new customers did we get last month?"

The LLM confidently generated:

```sql
SELECT COUNT(DISTINCT customer_id) FROM orders
```

Looks reasonable. Except:
- No date filter. It scanned 500 million rows across 6 years of data.
- Ran for 47 minutes on our production Redshift cluster.
- Returned "12.4 million" — the lifetime count, not last month's.
- The analyst published that number in a leadership presentation.

We caught the mistake three days later.

This wasn't a rare edge case. Over the following month, I tracked our text-to-SQL outputs and found that **roughly 1 in 5 queries had a correctness issue** that wouldn't surface until someone noticed the data "looked off." The issues ranged from wrong column names (hallucinated by the LLM) to missing business-critical filters to accidental exposure of PII columns.

I built `llm-sql-validator` because I was tired of discovering bad queries after the damage was done.

---

## The Problem: LLMs Are Confidently Wrong About SQL

Large Language Models are remarkably good at generating SQL. They understand joins, aggregations, window functions, CTEs — the whole syntax tree. But they fail in predictable ways that no existing tool catches:

**1. Hallucinated columns.** The LLM writes `SELECT customer_name FROM users` when the actual column is `first_name`. It sounds plausible, so no one notices until the query errors out — or worse, if there happens to be a similarly-named column in another table.

**2. Missing context.** The LLM doesn't know your business rules. It doesn't know that your `users` table has a `is_deleted` column that must always be filtered. It doesn't know that queries on `orders` without a date range will scan half a billion rows.

**3. Unsafe operations.** Ask "can you fix this data issue" and occasionally the LLM will generate an UPDATE or DELETE statement when you only expected a SELECT.

**4. Repeated mistakes.** The same bad pattern appears query after query because the LLM has no memory of past failures.

---

## What Exists Today (And Why It's Not Enough)

I evaluated every tool in the ecosystem before building my own:

**SQL linters (sqlfluff)** — Excellent for code style. Useless for LLM validation. They'll tell you to capitalize your keywords but won't notice you're querying a table that doesn't exist.

**Database EXPLAIN** — Requires submitting to a live database. That means your 500M-row full table scan already started before you get feedback.

**LLM self-check ("Does this SQL look correct?")** — Asking a hallucinating model to verify its own hallucinations. In my testing, the self-check agreed with wrong SQL about 60% of the time.

**Guardrails AI** — Great for general LLM output (JSON structure, PII detection in text). Not SQL-aware. Doesn't understand schemas, join conditions, or query cost.

**Great Expectations** — Validates data *after* execution. By then you've already paid for the compute and the wrong number is in someone's spreadsheet.

None of these tools address the specific ways LLMs fail at SQL.

---

## The Solution: Progressive Validation in 5 Tiers

`llm-sql-validator` runs every LLM-generated query through five independent checks before it reaches your database:

```
┌─────────────────────────────────────────────────────────┐
│  Tier 1: SYNTAX         Can the SQL be parsed?          │
│  Tier 2: SCHEMA         Do tables/columns exist?        │
│  Tier 3: BUSINESS RULES Does it follow your policies?   │
│  Tier 4: SAFETY         Is it safe to execute?          │
│  Tier 5: ANTI-EXAMPLES  Has this pattern failed before? │
└─────────────────────────────────────────────────────────┘
```

The pipeline is progressive — it stops at the first failure and returns a clear error message that can be fed back to the LLM for self-correction.

### Here's what it looks like in practice:

```python
from llm_sql_validator import ValidationPipeline, ValidatorConfig

config = ValidatorConfig.from_yaml("schema.yaml")
pipeline = ValidationPipeline(config)

result = pipeline.validate("SELECT customer_name, email FROM users WHERE age > 25")

if not result.is_valid:
    print(f"Blocked at {result.failed_tier}: {result.error_messages}")
```

Output:
```
Blocked at SCHEMA: Column 'customer_name' does not exist in table 'users'. 
Did you mean 'first_name' or 'full_name'?
```

That error message goes back to the LLM, which regenerates the query correctly. No human intervention needed.

---

## The Features That Matter Most

### Fuzzy Column Suggestions

When an LLM hallucinates a column name, the validator doesn't just say "not found." It suggests the closest match:

```
Column 'firstname' does not exist in table 'users'. 
Did you mean: 'first_name'?
```

This is the difference between a dead-end error and an auto-correctable one.

### Configurable Business Rules (YAML)

Every team has different data rules. Define them once in YAML:

```yaml
rules:
  - name: require_date_filter_on_orders
    rule_type: required_filter
    target_tables: [orders]
    filter_columns: [order_date]
    description: "Orders has 500M rows — always filter by date"
    
  - name: block_pii_columns
    rule_type: forbidden_columns
    columns_with_tag: pii
    unless_wrapped_in: [mask, hash, anonymize]
    description: "PII columns need masking before selection"
```

Marketing team gets one config. Finance team gets another. The tool adapts.

### Anti-Example Learning

This is the feature I'm most proud of. When a query produces wrong results, you record it:

```python
pipeline.record_anti_example(
    sql="SELECT COUNT(*) FROM orders",
    reason="Missing date filter — returned lifetime count instead of monthly"
)
```

From that moment on, any similar query gets flagged:

```
Warning: Query matches a known problematic pattern (similarity: 87%).
Previous issue: Missing date filter — returned lifetime count instead of monthly.
```

Your validation system learns from mistakes. It gets smarter every time something goes wrong.

### Safety Guardrails

DDL blocked. DML blocked (in read-only mode). Cartesian joins detected. SQL injection patterns flagged. All without connecting to a database.

---

## Real-World Impact

Since deploying this approach internally:

- **Query accuracy on first attempt went from ~78% to ~92%** — validation catches and auto-corrects most issues before the user sees them
- **Zero PII exposure incidents** — the forbidden_columns rule eliminates accidental data leaks
- **$0 in runaway query costs** — row-limit rules prevent unbounded scans
- **Investigation time dropped from hours to seconds** — when something does fail, the error message tells you exactly why

---

## Who This Is For

- **Data platform teams** building text-to-SQL interfaces for business users
- **Anyone using LangChain/LlamaIndex SQL agents** in production
- **Enterprises** where data governance requires query-level policy enforcement
- **Startups** building AI-powered BI tools and needing a safety layer between the LLM and the database

---

## Getting Started

```bash
pip install llm-sql-validator
```

Define your schema in YAML, add your business rules, and wrap your LLM output:

```python
from llm_sql_validator import ValidationPipeline

pipeline = ValidationPipeline.from_yaml("config.yaml")
result = pipeline.validate(llm_generated_sql)

if result.is_valid:
    execute(llm_generated_sql)
else:
    # Feed errors back to LLM for retry
    retry_with_context(result.error_messages)
```

Full documentation, examples, and source code: [github.com/reach2lokeshkh/llm-sql-validator](https://github.com/reach2lokeshkh/llm-sql-validator)

---

## What's Next

- **v0.2** — Anti-example store with persistent similarity matching
- **v0.3** — Live database introspection (auto-discover schema from your DB)
- **v0.4** — Native LangChain/LlamaIndex integrations
- **v0.5** — Query cost estimation heuristics per dialect
- **v1.0** — Stable API with full documentation site

---

## Try It, Break It, Tell Me What's Missing

This is an open-source project. If you're building text-to-SQL and want a safety net that actually works, give it a try. Open issues, contribute rule types, or just tell me what's broken.

The goal is simple: **no more finding bad queries after the damage is done.**

---

*Lokesh Kumar H is a Senior Data Engineer specializing in AI/ML data systems, distributed analytics platforms, and LLM applications. He has 21 years of experience building data infrastructure at Amazon, Philips Healthcare, and other Fortune 500 companies.*

*GitHub: [github.com/reach2lokeshkh](https://github.com/reach2lokeshkh) | LinkedIn: [linkedin.com/in/lokeshkumarsql](https://linkedin.com/in/lokeshkumarsql)*
