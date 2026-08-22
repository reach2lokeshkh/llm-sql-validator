# Use Cases for llm-sql-validator

---

## 1. Self-Service Business Intelligence (Text-to-SQL Chatbots)

**Scenario:** A company deploys a chatbot where marketing managers, finance analysts, and content strategists ask data questions in plain English. An LLM converts their questions to SQL and runs them against the data warehouse.

**Without validation:**
- Analyst asks "How many customers bought last month?" → LLM forgets the date filter → returns lifetime count (12M instead of 80K) → wrong number ends up in a board presentation

**With llm-sql-validator:**
- Business rules tier catches the missing date filter
- Returns: "Query on orders table requires order_date filter" 
- Error is fed back to the LLM → regenerates with correct date range → accurate answer

**Industries:** Retail, e-commerce, media/entertainment, SaaS, financial services

---

## 2. Enterprise Data Governance & Compliance

**Scenario:** A healthcare company allows analysts to query patient data via an AI assistant, but HIPAA requires that PII (Social Security numbers, medical record IDs) is never exposed in raw form.

**Without validation:**
- Analyst asks "Show me patient details for Dr. Smith's clinic" → LLM selects SSN, date_of_birth, diagnosis columns in plain text → compliance violation

**With llm-sql-validator:**
- Business rules tier blocks PII columns unless wrapped in `mask()` or `hash()`
- Returns: "Column 'ssn' cannot be accessed directly. Wrap with masking function: mask, hash, anonymize"
- LLM regenerates with `mask(ssn)` → compliant result

**Industries:** Healthcare, banking, insurance, government, any GDPR/HIPAA-regulated org

---

## 3. Cost Control on Cloud Data Warehouses

**Scenario:** A data team runs on Snowflake/Redshift/BigQuery where compute is billed per query. Non-technical users generating queries through an AI tool accidentally trigger full table scans on billion-row tables.

**Without validation:**
- User asks "What are our top products?" → LLM generates `SELECT * FROM order_items` → scans 2 billion rows → $300 query cost → 45-minute execution time

**With llm-sql-validator:**
- Business rules tier enforces: "Tables with >100M rows require WHERE or LIMIT"
- Safety tier flags: "Query would scan ~2B rows without bounds"
- Error fed back → LLM adds `WHERE order_date > CURRENT_DATE - 30 LIMIT 1000`

**Industries:** Any company on pay-per-query cloud platforms (especially BigQuery, Snowflake)

---

## 4. AI-Powered Customer-Facing Analytics Products

**Scenario:** A SaaS company offers embedded analytics where end-users type questions about their own data. The product uses an LLM to generate SQL behind the scenes.

**Without validation:**
- User asks "Delete my old records" → LLM generates `DELETE FROM user_data WHERE created_at < '2023-01-01'` → production data destroyed
- User asks something ambiguous → LLM produces a UNION injection pattern → potential security breach

**With llm-sql-validator:**
- Safety tier blocks all DML (INSERT/UPDATE/DELETE) in read-only mode
- Safety tier detects SQL injection patterns
- Only SELECT queries pass through to execution

**Industries:** SaaS platforms, embedded analytics (Metabase alternatives), customer portals

---

## 5. Financial Reporting & Royalty Calculations

**Scenario:** A media company uses AI to generate financial queries for revenue reporting, royalty payments to content partners, and pricing analysis. Accuracy is contractually required.

**Without validation:**
- LLM generates a pricing query that references a lookup table frozen since 2021 → all calculated royalties are off by 15% → contract disputes with studio partners

**With llm-sql-validator:**
- Schema validator catches references to deprecated tables/columns
- Anti-example detection flags queries matching known problematic patterns
- Business rules enforce required joins with current reference data

**Industries:** Media/entertainment, music streaming, publishing, any business with royalty/licensing agreements

---

## 6. Internal Developer Productivity Tools

**Scenario:** An engineering team builds an internal tool where developers can ask data questions in Slack or a web UI. The tool generates and runs SQL against internal databases.

**Without validation:**
- Junior developer asks "Show me all user passwords for debugging" → LLM happily generates a query exposing credentials
- Developer asks "Clean up test data" → LLM generates TRUNCATE on a shared table

**With llm-sql-validator:**
- Forbidden columns rule blocks sensitive columns (passwords, tokens, keys)
- Safety tier blocks DDL/DML
- Team-specific configs limit what each team can query

**Industries:** Tech companies, development teams, platform engineering

---

## 7. Multi-Tenant AI Data Platforms

**Scenario:** A platform serves multiple client teams, each with their own schema, rules, and access levels. All use the same text-to-SQL interface.

**Without validation:**
- Marketing team's query accidentally references Finance's restricted revenue tables → data leak across teams

**With llm-sql-validator:**
- Each team loads their own YAML config (schema + rules)
- Schema validator only recognises tables the team has access to
- Business rules differ per team (marketing needs campaign filters; finance needs audit trails)

**Industries:** Large enterprises with multiple business units, data mesh architectures

---

## 8. Education & Training Platforms

**Scenario:** A coding education platform lets students practice SQL by typing questions and seeing AI-generated queries. The platform needs to ensure generated SQL is safe and educational.

**Without validation:**
- Student asks something that triggers a destructive query on the shared database
- AI generates overly complex SQL that's technically correct but pedagogically confusing

**With llm-sql-validator:**
- Safety tier prevents any destructive operations
- Business rules can enforce query complexity limits (max joins, max subquery depth)
- Schema validation ensures only the student's practice tables are referenced

**Industries:** EdTech, coding bootcamps, university database courses

---

## 9. Automated Report Generation

**Scenario:** A system generates weekly/monthly reports by converting report specifications into SQL queries via an LLM. Reports are generated at scale (hundreds per week) without human review.

**Without validation:**
- One bad query in a batch of 200 reports goes unnoticed → wrong metrics in executive dashboards for a week

**With llm-sql-validator:**
- Every generated query is validated before execution
- Anti-examples accumulate over time, catching recurring patterns
- Batch validation reports show which queries passed/failed before any execution

**Industries:** Consulting firms, analytics agencies, enterprise BI teams

---

## 10. LLM Agent Pipelines (Autonomous Workflows)

**Scenario:** An AI agent autonomously queries databases as part of a multi-step workflow (e.g., "Analyse last quarter's performance, identify underperforming segments, draft recommendations"). The agent generates and executes multiple queries without human oversight.

**Without validation:**
- Agent generates 15 queries in sequence → one has a cartesian join → hangs the cluster → downstream steps fail → entire workflow is corrupted

**With llm-sql-validator:**
- Each query is validated inline before execution
- Cartesian join detection stops the problematic query instantly
- Agent receives clear error → retries with corrected join condition → workflow continues

**Industries:** Any team using LangChain agents, CrewAI, AutoGen, or custom AI workflows

---

## Summary Table

| Use Case | Primary Tiers Used | Key Benefit |
|----------|-------------------|-------------|
| Self-service BI | Schema, Business Rules | Accurate answers to business users |
| Compliance/Governance | Business Rules (PII) | Regulatory compliance |
| Cost control | Business Rules (row limits), Safety | Prevent expensive queries |
| Customer-facing products | Safety, Schema | Security + correctness |
| Financial reporting | Schema, Anti-Examples | Contractual accuracy |
| Developer tools | Safety, Business Rules | Prevent accidental damage |
| Multi-tenant platforms | Schema, Business Rules | Team-level isolation |
| Education | Safety, Business Rules | Safe learning environment |
| Automated reporting | All 5 tiers | Batch reliability |
| Agent pipelines | Safety, Schema | Autonomous workflow resilience |
